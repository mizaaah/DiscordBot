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
                embed.add_field(name=t(lang, "automod.log_member"), value=f"{member.mention} (`{member.id}`)", inline=True)
                embed.add_field(name=t(lang, "automod.log_reason"), value=reason, inline=False)
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
                embed.add_field(name=t(lang, "automod.log_member"), value=f"{member.mention} (`{member.id}`)", inline=True)
                embed.add_field(name=t(lang, "automod.log_duration"), value=t(lang, "automod.mute_duration_value"), inline=True)
                embed.add_field(name=t(lang, "automod.log_reason"), value=reason, inline=False)
                await logs.send_log(guild, embed)

        elif action == "kick":
            try:
                await member.kick(reason=f"[AutoMod] {reason}")
            except discord.Forbidden:
                pass
            if logs := self.bot.get_cog("Logs"):
                embed = discord.Embed(title=t(lang, "automod.log_kick_title"), color=Colors.ERROR)
                embed.add_field(name=t(lang, "automod.log_member"), value=f"{member.mention} (`{member.id}`)", inline=True)
                embed.add_field(name=t(lang, "automod.log_reason"), value=reason, inline=False)
                await logs.send_log(guild, embed)

        elif action == "ban":
            try:
                await member.ban(reason=f"[AutoMod] {reason}", delete_message_days=0)
            except discord.Forbidden:
                pass
            if logs := self.bot.get_cog("Logs"):
                embed = discord.Embed(title=t(lang, "automod.log_ban_title"), color=Colors.DANGER)
                embed.add_field(name=t(lang, "automod.log_member"), value=f"{member.mention} (`{member.id}`)", inline=True)
                embed.add_field(name=t(lang, "automod.log_reason"), value=reason, inline=False)
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

    automod_group = app_commands.Group(name="automod", description="Configuration de l'auto-modération")

    @automod_group.command(name="status", description="Affiche la configuration de l'auto-modération")
    @app_commands.default_permissions(manage_guild=True)
    async def automod_status(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        config = await self.bot.db.get_automod_config(interaction.guild.id)

        def status(enabled: bool) -> str:
            return t(lang, "common.enabled") if enabled else t(lang, "common.disabled")

        embed = discord.Embed(
            title=t(lang, "automod.status_title"),
            color=Colors.INFO
        )
        embed.add_field(name=t(lang, "automod.global_status"), value=status(config["enabled"]), inline=False)
        embed.add_field(
            name=t(lang, "automod.spam_field"),
            value=t(lang, "automod.spam_value", status=status(config['spam_enabled']), threshold=config['spam_threshold'], window=config['spam_window'], action=config['spam_action']),
            inline=False
        )
        embed.add_field(
            name=t(lang, "automod.flood_field"),
            value=t(lang, "automod.flood_value", status=status(config['flood_enabled']), threshold=config['flood_threshold'], action=config['flood_action']),
            inline=False
        )
        embed.add_field(
            name=t(lang, "automod.invite_field"),
            value=t(lang, "automod.invite_value", status=status(config['invite_enabled']), action=config['invite_action']),
            inline=False
        )
        whitelist = config.get("link_whitelist") or []
        embed.add_field(
            name=t(lang, "automod.link_field"),
            value=t(lang, "automod.link_value", status=status(config['link_enabled']), action=config['link_action'], count=len(whitelist)),
            inline=False
        )
        embed.add_field(
            name=t(lang, "automod.caps_field"),
            value=t(lang, "automod.caps_value", status=status(config['caps_enabled']), threshold=config['caps_threshold'], min_length=config['caps_min_length'], action=config['caps_action']),
            inline=False
        )
        embed.add_field(
            name=t(lang, "automod.mentions_field"),
            value=t(lang, "automod.mentions_value", status=status(config['mention_enabled']), threshold=config['mention_threshold'], action=config['mention_action']),
            inline=False
        )
        bypass = config.get("bypass_roles") or []
        bypass_str = " ".join(f"<@&{r}>" for r in bypass) if bypass else t(lang, "automod.no_bypass_roles")
        embed.add_field(name=t(lang, "automod.bypass_roles_field"), value=bypass_str, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @automod_group.command(name="toggle", description="Active ou désactive l'AutoMod globalement")
    @app_commands.describe(activer="Activer ou désactiver")
    @app_commands.default_permissions(manage_guild=True)
    async def automod_toggle(self, interaction: discord.Interaction, activer: bool):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        await self.bot.db.update_automod_setting(interaction.guild.id, "enabled", activer)
        state = t(lang, "common.enabled") if activer else t(lang, "common.disabled")
        await interaction.response.send_message(embed=info_embed(t(lang, "automod.toggle_result", state=state)))

    @automod_group.command(name="spam", description="Configure la détection de spam")
    @app_commands.describe(
        activer="Activer/désactiver",
        seuil="Nombre de messages déclenchant le spam (défaut : 5)",
        fenetre="Fenêtre de temps en secondes (défaut : 5)",
        action="Action à effectuer"
    )
    @app_commands.choices(action=ACTION_CHOICES)
    @app_commands.default_permissions(manage_guild=True)
    async def automod_spam(self, interaction: discord.Interaction, activer: bool, seuil: int = 5, fenetre: int = 5, action: str = "mute"):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        db = self.bot.db
        gid = interaction.guild.id
        await db.update_automod_setting(gid, "spam_enabled", activer)
        await db.update_automod_setting(gid, "spam_threshold", seuil)
        await db.update_automod_setting(gid, "spam_window", fenetre)
        await db.update_automod_setting(gid, "spam_action", action)
        state = t(lang, "common.enabled") if activer else t(lang, "common.disabled")
        await interaction.response.send_message(
            embed=info_embed(t(lang, "automod.spam_result", state=state, threshold=seuil, window=fenetre, action=action))
        )

    @automod_group.command(name="flood", description="Configure la détection de flood (messages identiques)")
    @app_commands.describe(activer="Activer/désactiver", seuil="Nombre de répétitions (défaut : 3)", action="Action à effectuer")
    @app_commands.choices(action=ACTION_CHOICES)
    @app_commands.default_permissions(manage_guild=True)
    async def automod_flood(self, interaction: discord.Interaction, activer: bool, seuil: int = 3, action: str = "warn"):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        db = self.bot.db
        gid = interaction.guild.id
        await db.update_automod_setting(gid, "flood_enabled", activer)
        await db.update_automod_setting(gid, "flood_threshold", seuil)
        await db.update_automod_setting(gid, "flood_action", action)
        state = t(lang, "common.enabled") if activer else t(lang, "common.disabled")
        await interaction.response.send_message(
            embed=info_embed(t(lang, "automod.flood_result", state=state, threshold=seuil, action=action))
        )

    @automod_group.command(name="invites", description="Configure le filtre d'invitations Discord")
    @app_commands.describe(activer="Activer/désactiver", action="Action à effectuer")
    @app_commands.choices(action=ACTION_CHOICES)
    @app_commands.default_permissions(manage_guild=True)
    async def automod_invites(self, interaction: discord.Interaction, activer: bool, action: str = "warn"):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        db = self.bot.db
        gid = interaction.guild.id
        await db.update_automod_setting(gid, "invite_enabled", activer)
        await db.update_automod_setting(gid, "invite_action", action)
        state = t(lang, "common.enabled") if activer else t(lang, "common.disabled")
        await interaction.response.send_message(embed=info_embed(t(lang, "automod.invites_result", state=state, action=action)))

    @automod_group.command(name="links", description="Configure le filtre anti-liens (bloque toutes les URLs)")
    @app_commands.describe(activer="Activer/désactiver", action="Action à effectuer")
    @app_commands.choices(action=ACTION_CHOICES)
    @app_commands.default_permissions(manage_guild=True)
    async def automod_links(self, interaction: discord.Interaction, activer: bool, action: str = "warn"):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        db = self.bot.db
        gid = interaction.guild.id
        await db.update_automod_setting(gid, "link_enabled", activer)
        await db.update_automod_setting(gid, "link_action", action)
        state = t(lang, "common.enabled") if activer else t(lang, "common.disabled")
        await interaction.response.send_message(embed=info_embed(t(lang, "automod.links_result", state=state, action=action)))

    @automod_group.command(name="linkwhitelist", description="Ajoute ou retire un domaine autorisé par l'anti-liens")
    @app_commands.describe(domaine="Nom de domaine (ex: youtube.com)", action="Ajouter ou retirer")
    @app_commands.choices(action=[
        app_commands.Choice(name="Ajouter", value="add"),
        app_commands.Choice(name="Retirer", value="remove"),
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def automod_linkwhitelist(self, interaction: discord.Interaction, domaine: str, action: str):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        config = await self.bot.db.get_automod_config(interaction.guild.id)
        whitelist = list(config.get("link_whitelist") or [])
        domaine = domaine.lower().strip().removeprefix("www.")
        if action == "add":
            if domaine not in whitelist:
                whitelist.append(domaine)
            msg = success_embed(t(lang, "automod.whitelist_added", domain=domaine))
        else:
            whitelist = [d for d in whitelist if d != domaine]
            msg = success_embed(t(lang, "automod.whitelist_removed", domain=domaine))
        await self.bot.db.update_automod_setting(interaction.guild.id, "link_whitelist", whitelist)
        await interaction.response.send_message(embed=msg)

    @automod_group.command(name="caps", description="Configure le filtre anti-majuscules")
    @app_commands.describe(
        activer="Activer/désactiver",
        pourcentage="Seuil de majuscules en % pour déclencher (défaut : 70)",
        min_longueur="Longueur min du message pour vérifier (défaut : 10)",
        action="Action à effectuer"
    )
    @app_commands.choices(action=ACTION_CHOICES)
    @app_commands.default_permissions(manage_guild=True)
    async def automod_caps(self, interaction: discord.Interaction, activer: bool, pourcentage: int = 70, min_longueur: int = 10, action: str = "warn"):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        db = self.bot.db
        gid = interaction.guild.id
        await db.update_automod_setting(gid, "caps_enabled", activer)
        await db.update_automod_setting(gid, "caps_threshold", max(1, min(100, pourcentage)))
        await db.update_automod_setting(gid, "caps_min_length", min_longueur)
        await db.update_automod_setting(gid, "caps_action", action)
        state = t(lang, "common.enabled") if activer else t(lang, "common.disabled")
        await interaction.response.send_message(
            embed=info_embed(t(lang, "automod.caps_result", state=state, pct=pourcentage, min_length=min_longueur, action=action))
        )

    @automod_group.command(name="mentions", description="Configure le filtre anti-mentions massives")
    @app_commands.describe(activer="Activer/désactiver", seuil="Nombre max de mentions (défaut : 5)", action="Action à effectuer")
    @app_commands.choices(action=ACTION_CHOICES)
    @app_commands.default_permissions(manage_guild=True)
    async def automod_mentions(self, interaction: discord.Interaction, activer: bool, seuil: int = 5, action: str = "mute"):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        db = self.bot.db
        gid = interaction.guild.id
        await db.update_automod_setting(gid, "mention_enabled", activer)
        await db.update_automod_setting(gid, "mention_threshold", seuil)
        await db.update_automod_setting(gid, "mention_action", action)
        state = t(lang, "common.enabled") if activer else t(lang, "common.disabled")
        await interaction.response.send_message(
            embed=info_embed(t(lang, "automod.mentions_result", state=state, threshold=seuil, action=action))
        )

    @automod_group.command(name="bypass", description="Ajoute ou retire un rôle ignoré par l'AutoMod")
    @app_commands.describe(role="Le rôle", action="Ajouter ou retirer")
    @app_commands.choices(action=[
        app_commands.Choice(name="Ajouter", value="add"),
        app_commands.Choice(name="Retirer", value="remove"),
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def automod_bypass(self, interaction: discord.Interaction, role: discord.Role, action: str):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        config = await self.bot.db.get_automod_config(interaction.guild.id)
        bypass = list(config.get("bypass_roles") or [])
        if action == "add":
            if role.id not in bypass:
                bypass.append(role.id)
            msg = success_embed(t(lang, "automod.bypass_added", role=role.mention))
        else:
            bypass = [r for r in bypass if r != role.id]
            msg = success_embed(t(lang, "automod.bypass_removed", role=role.mention))
        await self.bot.db.update_automod_setting(interaction.guild.id, "bypass_roles", bypass)
        await interaction.response.send_message(embed=msg)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
