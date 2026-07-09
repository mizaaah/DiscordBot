import time
from collections import defaultdict
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from utils.colors import Colors
from utils.embeds import info_embed
from utils.i18n import t

ACTION_CHOICES = [
    app_commands.Choice(name="Expulser les raiders", value="kick"),
    app_commands.Choice(name="Bannir les raiders",   value="ban"),
    app_commands.Choice(name="Expulser + Lockdown",  value="lockdown"),
]


class AntiRaid(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # {guild_id: [(timestamp, member), ...]}
        self._join_events: dict[int, list] = defaultdict(list)

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _kick_or_ban(self, member: discord.Member, action: str, reason: str):
        try:
            if action == "ban":
                await member.ban(reason=f"[AntiRaid] {reason}", delete_message_days=0)
            else:
                await member.kick(reason=f"[AntiRaid] {reason}")
        except discord.Forbidden:
            pass

    async def _lockdown(self, guild: discord.Guild):
        await self.bot.db.update_antiraid_setting(guild.id, "lockdown_active", True)
        for ch in guild.text_channels:
            ow = ch.overwrites_for(guild.default_role)
            if ow.send_messages is not False:
                ow.send_messages = False
                try:
                    await ch.set_permissions(guild.default_role, overwrite=ow,
                                             reason="[AntiRaid] Lockdown automatique")
                except discord.Forbidden:
                    pass

    async def _unlock(self, guild: discord.Guild):
        await self.bot.db.update_antiraid_setting(guild.id, "lockdown_active", False)
        for ch in guild.text_channels:
            ow = ch.overwrites_for(guild.default_role)
            if ow.send_messages is False:
                ow.send_messages = None
                try:
                    if ow.is_empty():
                        await ch.set_permissions(guild.default_role, overwrite=None,
                                                 reason="[AntiRaid] Fin du lockdown")
                    else:
                        await ch.set_permissions(guild.default_role, overwrite=ow,
                                                 reason="[AntiRaid] Fin du lockdown")
                except discord.Forbidden:
                    pass

    async def _send_alert(self, guild: discord.Guild, config: dict, count: int, action: str, reason: str):
        ch_id = config.get("alert_channel_id")
        if not ch_id:
            settings = await self.bot.db.get_guild_settings(guild.id)
            ch_id = settings.get("log_channel_id")
        if not ch_id:
            return
        ch = guild.get_channel(ch_id)
        if not ch:
            return
        lang = await self.bot.db.get_guild_lang(guild.id)
        embed = discord.Embed(
            title=t(lang, "raid.alert_title"),
            description=t(lang, "raid.alert_desc", count=count, reason=reason, action=action),
            color=Colors.ERROR,
            timestamp=datetime.now(timezone.utc)
        )
        if action == "lockdown":
            embed.add_field(
                name=t(lang, "raid.lockdown_active_field"),
                value=t(lang, "raid.lockdown_active_hint"),
                inline=False
            )
        embed.set_footer(text=t(lang, "raid.footer"))
        try:
            await ch.send(embed=embed)
        except discord.Forbidden:
            pass

    # ── on_member_join ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        config = await self.bot.db.get_antiraid_config(member.guild.id)
        if not config.get("enabled"):
            return

        # — Vérification de l'âge du compte —
        min_age = config.get("min_account_age", 0)
        if min_age > 0:
            age_days = (datetime.now(timezone.utc) - member.created_at).days
            if age_days < min_age:
                await self._kick_or_ban(member, config.get("action", "kick"),
                                        f"Compte trop récent ({age_days}j < {min_age}j requis)")
                await self._send_alert(member.guild, config, 1, config.get("action", "kick"),
                                       f"Compte créé il y a {age_days} jour(s) (minimum : {min_age}j)")
                return

        # — Vérification du débit de rejoins —
        now = time.monotonic()
        gid = member.guild.id
        window = config.get("join_window", 30)
        threshold = config.get("join_threshold", 10)

        self._join_events[gid] = [
            (ts, m) for ts, m in self._join_events[gid] if now - ts <= window
        ]
        self._join_events[gid].append((now, member))

        if len(self._join_events[gid]) >= threshold:
            recent_members = [m for _, m in self._join_events[gid]]
            self._join_events[gid].clear()

            action = config.get("action", "kick")
            for m in recent_members:
                if m in member.guild.members:
                    await self._kick_or_ban(m, action, "Raid détecté — mass-join")

            if action == "lockdown":
                await self._lockdown(member.guild)

            await self._send_alert(
                member.guild, config, len(recent_members), action,
                f"{len(recent_members)} joins en {window}s (seuil : {threshold})"
            )

    # ── Commands ──────────────────────────────────────────────────────────────

    antiraid_group = app_commands.Group(name="antiraid", description="Gestion de l'anti-raid")

    @antiraid_group.command(name="lockdown", description="Verrouille manuellement tout le serveur")
    @app_commands.describe(raison="Raison du lockdown")
    @app_commands.default_permissions(manage_guild=True)
    async def ar_lockdown(self, interaction: discord.Interaction, raison: str = None):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        raison = raison or t(lang, "raid.manual_lockdown_default")
        await interaction.response.defer()
        await self._lockdown(interaction.guild)
        embed = discord.Embed(
            title=t(lang, "raid.lockdown_on_title"),
            description=t(lang, "raid.lockdown_on_desc", reason=raison),
            color=Colors.ERROR
        )
        embed.set_footer(text=t(lang, "raid.lockdown_on_footer"))
        await interaction.followup.send(embed=embed)

        if logs := self.bot.get_cog("Logs"):
            await logs.send_log(interaction.guild, embed)

    @antiraid_group.command(name="unlock", description="Lève le lockdown du serveur")
    @app_commands.default_permissions(manage_guild=True)
    async def ar_unlock(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        await interaction.response.defer()
        await self._unlock(interaction.guild)
        embed = discord.Embed(
            title=t(lang, "raid.lockdown_off_title"),
            description=t(lang, "raid.lockdown_off_desc"),
            color=Colors.SUCCESS
        )
        await interaction.followup.send(embed=embed)

        if logs := self.bot.get_cog("Logs"):
            await logs.send_log(interaction.guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiRaid(bot))
