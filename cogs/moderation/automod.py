import re
import time
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands
from utils.colors import Colors
from utils.embeds import info_embed, success_embed
from utils.i18n import t

INVITE_REGEX = re.compile(r"discord(?:\.gg|app\.com/invite)/[a-zA-Z0-9-]+", re.IGNORECASE)
URL_REGEX = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.IGNORECASE)


def _extract_domain(url: str) -> str:
    if not url.lower().startswith(("http://", "https://")):
        url = "http://" + url
    netloc = urlparse(url).netloc.lower().split(":")[0]
    return netloc[4:] if netloc.startswith("www.") else netloc

ACTION_CHOICES = [
    app_commands.Choice(name="Avertir", value="warn"),
    app_commands.Choice(name="Muter 10 min", value="mute"),
    app_commands.Choice(name="Expulser", value="kick"),
    app_commands.Choice(name="Bannir", value="ban"),
]


class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._timestamps: dict[tuple, deque] = defaultdict(lambda: deque())
        self._contents: dict[tuple, deque] = defaultdict(lambda: deque(maxlen=10))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _should_bypass(self, member: discord.Member, bypass_roles: list) -> bool:
        if member.guild_permissions.manage_messages:
            return True
        return any(r.id in bypass_roles for r in member.roles)

    async def _apply_action(self, message: discord.Message, action: str, reason: str, lang: str):
        member = message.author
        guild = message.guild

        try:
            await message.delete()
        except discord.HTTPException:
            pass

        try:
            await member.send(t(lang, "automod.dm_notice", server=guild.name, reason=reason))
        except discord.Forbidden:
            pass

        if action == "warn":
            warn_id = await self.bot.db.add_warning(guild.id, member.id, self.bot.user.id, f"[AutoMod] {reason}")
            total = await self.bot.db.get_warning_count(guild.id, member.id)
            try:
                await message.channel.send(
                    embed=info_embed(t(lang, "automod.warn_msg", member=member.mention, total=total)),
                    delete_after=6
                )
            except discord.Forbidden:
                pass
            if logs := self.bot.get_cog("Logs"):
                embed = discord.Embed(title=t(lang, "automod.log_warn_title"), color=Colors.CAUTION)
                embed.add_field(name=t(lang, "automod.log_member"), value=f"> {member.mention} (`{member.id}`)", inline=True)
                embed.add_field(name=t(lang, "automod.log_reason"), value=f"> {reason}", inline=False)
                embed.set_footer(text=t(lang, "automod.warn_footer", id=warn_id))
                await logs.send_log(guild, embed)

        elif action == "mute":
            until = datetime.now(timezone.utc) + timedelta(minutes=10)
            try:
                await member.timeout(until, reason=f"[AutoMod] {reason}")
                await message.channel.send(
                    embed=info_embed(t(lang, "automod.mute_msg", member=member.mention)), delete_after=6
                )
            except discord.Forbidden:
                pass
            if logs := self.bot.get_cog("Logs"):
                embed = discord.Embed(title=t(lang, "automod.log_mute_title"), color=Colors.WARNING)
                embed.add_field(name=t(lang, "automod.log_member"), value=f"> {member.mention} (`{member.id}`)", inline=True)
                embed.add_field(name=t(lang, "automod.log_duration"), value=f"> {t(lang, 'automod.mute_duration_value')}", inline=True)
                embed.add_field(name=t(lang, "automod.log_reason"), value=f"> {reason}", inline=False)
                await logs.send_log(guild, embed)

        elif action == "kick":
            try:
                await member.kick(reason=f"[AutoMod] {reason}")
            except discord.Forbidden:
                pass
            if logs := self.bot.get_cog("Logs"):
                embed = discord.Embed(title=t(lang, "automod.log_kick_title"), color=Colors.ERROR)
                embed.add_field(name=t(lang, "automod.log_member"), value=f"> {member.mention} (`{member.id}`)", inline=True)
                embed.add_field(name=t(lang, "automod.log_reason"), value=f"> {reason}", inline=False)
                await logs.send_log(guild, embed)

        elif action == "ban":
            try:
                await member.ban(reason=f"[AutoMod] {reason}", delete_message_days=0)
            except discord.Forbidden:
                pass
            if logs := self.bot.get_cog("Logs"):
                embed = discord.Embed(title=t(lang, "automod.log_ban_title"), color=Colors.DANGER)
                embed.add_field(name=t(lang, "automod.log_member"), value=f"> {member.mention} (`{member.id}`)", inline=True)
                embed.add_field(name=t(lang, "automod.log_reason"), value=f"> {reason}", inline=False)
                await logs.send_log(guild, embed)

    # ── Listener ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if not isinstance(message.author, discord.Member):
            return

        config = await self.bot.db.get_automod_config(message.guild.id)
        if not config.get("enabled", True):
            return

        bypass_roles = config.get("bypass_roles") or []
        if self._should_bypass(message.author, bypass_roles):
            return
        if await self.bot.db.is_whitelisted(message.guild.id, message.author.id):
            return

        key = (message.guild.id, message.author.id)
        now = time.monotonic()
        lang = await self.bot.db.get_guild_lang(message.guild.id)

        # ── Anti-spam ────────────────────────────────────────────────────────
        if config.get("spam_enabled", True):
            threshold = config["spam_threshold"]
            window = config["spam_window"]
            self._timestamps[key].append(now)
            while self._timestamps[key] and now - self._timestamps[key][0] > window:
                self._timestamps[key].popleft()
            if len(self._timestamps[key]) >= threshold:
                self._timestamps[key].clear()
                await self._apply_action(message, config["spam_action"], t(lang, "automod.reason_spam"), lang)
                return

        # ── Anti-flood ───────────────────────────────────────────────────────
        if config.get("flood_enabled", True):
            flood_threshold = config["flood_threshold"]
            self._contents[key].append(message.content.lower().strip())
            recent = list(self._contents[key])
            if len(recent) >= flood_threshold and len(set(recent[-flood_threshold:])) == 1:
                self._contents[key].clear()
                await self._apply_action(message, config["flood_action"], t(lang, "automod.reason_flood"), lang)
                return

        # ── Anti-invites ──────────────────────────────────────────────────────
        if config.get("invite_enabled", False):
            if INVITE_REGEX.search(message.content):
                await self._apply_action(message, config["invite_action"], t(lang, "automod.reason_invite"), lang)
                return

        # ── Anti-liens ────────────────────────────────────────────────────────
        if config.get("link_enabled", False):
            urls = URL_REGEX.findall(message.content)
            if urls:
                whitelist = set(config.get("link_whitelist") or [])
                if any(_extract_domain(u) not in whitelist for u in urls):
                    await self._apply_action(message, config["link_action"], t(lang, "automod.reason_link"), lang)
                    return

        # ── Anti-caps ─────────────────────────────────────────────────────────
        if config.get("caps_enabled", False):
            content = message.content
            min_len = config["caps_min_length"]
            threshold = config["caps_threshold"]
            if len(content) >= min_len:
                letters = [c for c in content if c.isalpha()]
                if letters:
                    pct = sum(1 for c in letters if c.isupper()) / len(letters) * 100
                    if pct >= threshold:
                        await self._apply_action(message, config["caps_action"], t(lang, "automod.reason_caps", pct=f"{pct:.0f}"), lang)
                        return

        # ── Anti-mention ──────────────────────────────────────────────────────
        if config.get("mention_enabled", False):
            threshold = config["mention_threshold"]
            total_mentions = len(message.mentions) + len(message.role_mentions)
            if total_mentions >= threshold:
                await self._apply_action(
                    message, config["mention_action"],
                    t(lang, "automod.reason_mentions", count=total_mentions), lang
                )
                return

    # ── Slash commands ────────────────────────────────────────────────────────

    # ── Slash commands supprimées en faveur de /setup ────────────────────────

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
