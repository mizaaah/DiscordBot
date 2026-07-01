import discord
from datetime import datetime, timezone, timedelta
from discord import app_commands
from discord.ext import commands
from utils.helpers import parse_duration, duration_to_str
from utils.colors import Colors
from utils.embeds import error_embed, success_embed
from utils.i18n import t

ACTION_CHOICES = [
    app_commands.Choice(name="Mute (timeout)",          value="mute"),
    app_commands.Choice(name="Expulser (kick)",          value="kick"),
    app_commands.Choice(name="Bannir (permanent)",       value="ban"),
    app_commands.Choice(name="Bannir temporairement",    value="tempban"),
]

ACTION_NEEDS_DURATION = {"mute", "tempban"}


class AutoSanctions(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_warn_added(self, guild: discord.Guild, member: discord.Member, warn_count: int):
        thresholds = await self.bot.db.get_autosanctions(guild.id)
        threshold  = next((t for t in thresholds if t["warn_count"] == warn_count), None)
        if not threshold:
            return
        await self._apply(guild, member, threshold)

    async def _apply(self, guild: discord.Guild, member: discord.Member, threshold: dict):
        lang     = await self.bot.db.get_guild_lang(guild.id)
        action   = threshold["action"]
        duration = threshold["duration"]
        reason   = t(lang, "asanc.reason", count=threshold['warn_count'])

        try:
            if action == "mute" and duration:
                until = datetime.now(timezone.utc) + timedelta(seconds=duration)
                await member.timeout(until, reason=reason)
            elif action == "kick":
                await member.kick(reason=reason)
            elif action == "ban":
                await member.ban(reason=reason, delete_message_days=0)
            elif action == "tempban" and duration:
                unban_at = datetime.now(timezone.utc) + timedelta(seconds=duration)
                await member.ban(reason=reason, delete_message_days=0)
                await self.bot.db.add_temp_ban(guild.id, member.id, self.bot.user.id, reason, unban_at)
        except discord.Forbidden:
            pass

        try:
            label = _action_label(lang, action, duration)
            await member.send(t(lang, "asanc.dm_notice", server=guild.name, label=label, count=threshold['warn_count']))
        except discord.Forbidden:
            pass

        if logs := self.bot.get_cog("Logs"):
            embed = discord.Embed(
                title=t(lang, "asanc.log_title", label=_action_label(lang, action, duration)),
                description=t(lang, "asanc.log_desc", member=member.mention, count=threshold['warn_count']),
                color=Colors.DANGER
            )
            await logs.send_log(guild, embed)

    # ── Commands ──────────────────────────────────────────────────────────────

    as_group = app_commands.Group(name="autosanction", description="Sanctions automatiques par seuil de warns")

    @as_group.command(name="add", description="Ajoute ou modifie une sanction automatique")
    @app_commands.describe(
        warns="Nombre de warns pour déclencher la sanction",
        action="Action à effectuer",
        duree="Durée (ex: 1h, 7d) — requise pour mute/tempban"
    )
    @app_commands.choices(action=ACTION_CHOICES)
    @app_commands.default_permissions(manage_guild=True)
    async def as_add(
        self,
        interaction: discord.Interaction,
        warns: app_commands.Range[int, 1],
        action: str,
        duree: str = None
    ):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        duration = None
        if action in ACTION_NEEDS_DURATION:
            if not duree:
                return await interaction.response.send_message(
                    t(lang, "asanc.duration_required", action=action), ephemeral=True
                )
            try:
                duration, _ = parse_duration(duree)
            except ValueError as e:
                return await interaction.response.send_message(embed=error_embed(f"❌ {e}"), ephemeral=True)

        await self.bot.db.add_autosanction(interaction.guild.id, warns, action, duration)
        label = _action_label(lang, action, duration)
        await interaction.response.send_message(
            t(lang, "asanc.add_success", warns=warns, label=label)
        )

    @as_group.command(name="remove", description="Supprime une sanction automatique")
    @app_commands.describe(warns="Le seuil à supprimer")
    @app_commands.default_permissions(manage_guild=True)
    async def as_remove(self, interaction: discord.Interaction, warns: int):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        deleted = await self.bot.db.remove_autosanction(interaction.guild.id, warns)
        if deleted:
            await interaction.response.send_message(embed=success_embed(t(lang, "asanc.remove_success", warns=warns)))
        else:
            await interaction.response.send_message(embed=error_embed(t(lang, "asanc.remove_not_found", warns=warns)), ephemeral=True)

    @as_group.command(name="list", description="Liste les sanctions automatiques")
    @app_commands.default_permissions(manage_guild=True)
    async def as_list(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        rows = await self.bot.db.get_autosanctions(interaction.guild.id)
        embed = discord.Embed(title=t(lang, "asanc.list_title"), color=Colors.DANGER)
        if not rows:
            embed.description = t(lang, "asanc.list_empty")
        else:
            lines = [
                t(lang, "asanc.list_entry", count=r['warn_count'], label=_action_label(lang, r['action'], r['duration']))
                for r in rows
            ]
            embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed)


def _action_label(lang: str, action: str, duration: int | None) -> str:
    base = t(lang, f"asanc.action_{action}")
    if duration:
        return f"{base} ({duration_to_str_from_seconds(duration)})"
    return base


def duration_to_str_from_seconds(seconds: int) -> str:
    if seconds >= 86400:
        return f"{seconds // 86400}j"
    if seconds >= 3600:
        return f"{seconds // 3600}h"
    return f"{seconds // 60}m"


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoSanctions(bot))
