import discord
from datetime import datetime, timezone, timedelta
from discord import app_commands
from discord.ext import commands
from utils.helpers import parse_duration, duration_to_str

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
        action   = threshold["action"]
        duration = threshold["duration"]
        reason   = f"[Auto-sanction] {threshold['warn_count']} avertissement(s)"

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
            label = _action_label(action, duration)
            await member.send(
                f"⚠️ Tu as reçu une sanction automatique sur **{guild.name}** : **{label}**\n"
                f"Raison : {threshold['warn_count']} avertissement(s) atteints."
            )
        except discord.Forbidden:
            pass

        if logs := self.bot.get_cog("Logs"):
            embed = discord.Embed(
                title=f"🤖 Auto-sanction : {_action_label(action, duration)}",
                description=f"{member.mention} a atteint **{threshold['warn_count']}** avertissement(s).",
                color=discord.Color.dark_red()
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
        duration = None
        if action in ACTION_NEEDS_DURATION:
            if not duree:
                return await interaction.response.send_message(
                    f"❌ L'action `{action}` nécessite une durée (ex: `1h`, `7d`).", ephemeral=True
                )
            try:
                duration, _ = parse_duration(duree)
            except ValueError as e:
                return await interaction.response.send_message(f"❌ {e}", ephemeral=True)

        await self.bot.db.add_autosanction(interaction.guild.id, warns, action, duration)
        label = _action_label(action, duration)
        await interaction.response.send_message(
            f"✅ À **{warns}** avertissement(s) → **{label}** sera appliqué automatiquement."
        )

    @as_group.command(name="remove", description="Supprime une sanction automatique")
    @app_commands.describe(warns="Le seuil à supprimer")
    @app_commands.default_permissions(manage_guild=True)
    async def as_remove(self, interaction: discord.Interaction, warns: int):
        deleted = await self.bot.db.remove_autosanction(interaction.guild.id, warns)
        if deleted:
            await interaction.response.send_message(f"✅ Sanction au seuil **{warns}** warn(s) supprimée.")
        else:
            await interaction.response.send_message(f"❌ Aucune sanction au seuil **{warns}**.", ephemeral=True)

    @as_group.command(name="list", description="Liste les sanctions automatiques")
    @app_commands.default_permissions(manage_guild=True)
    async def as_list(self, interaction: discord.Interaction):
        rows = await self.bot.db.get_autosanctions(interaction.guild.id)
        embed = discord.Embed(title="🤖 Sanctions automatiques", color=discord.Color.dark_red())
        if not rows:
            embed.description = "Aucune sanction configurée.\nUtilise `/autosanction add` pour en ajouter."
        else:
            lines = [
                f"**{r['warn_count']} warn(s)** → {_action_label(r['action'], r['duration'])}"
                for r in rows
            ]
            embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed)


def _action_label(action: str, duration: int | None) -> str:
    labels = {"mute": "Mute", "kick": "Kick", "ban": "Ban permanent", "tempban": "Ban temporaire"}
    base = labels.get(action, action)
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
