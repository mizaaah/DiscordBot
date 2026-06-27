import time
from collections import defaultdict
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

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
        embed = discord.Embed(
            title="🚨 RAID DÉTECTÉ",
            description=(
                f"**{count}** compte(s) ont rejoint en très peu de temps.\n"
                f"**Raison :** {reason}\n"
                f"**Action appliquée :** `{action}`"
            ),
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        if action == "lockdown":
            embed.add_field(
                name="Lockdown actif",
                value="Utilisez `/antiraid unlock` pour lever le lockdown.",
                inline=False
            )
        embed.set_footer(text="AntiRaid Bot")
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

    @antiraid_group.command(name="status", description="Affiche la configuration anti-raid")
    @app_commands.default_permissions(manage_guild=True)
    async def ar_status(self, interaction: discord.Interaction):
        config = await self.bot.db.get_antiraid_config(interaction.guild.id)

        def yn(v): return "✅ Activé" if v else "❌ Désactivé"

        embed = discord.Embed(
            title="🛡️ Anti-Raid — Configuration",
            color=discord.Color.red() if config.get("lockdown_active") else discord.Color.blurple()
        )
        embed.add_field(name="Statut",          value=yn(config["enabled"]),              inline=True)
        embed.add_field(name="Lockdown actif",  value="🔴 OUI" if config["lockdown_active"] else "🟢 NON", inline=True)
        embed.add_field(name="Seuil",           value=f"{config['join_threshold']} joins / {config['join_window']}s", inline=True)
        embed.add_field(name="Action",          value=f"`{config['action']}`",            inline=True)
        embed.add_field(name="Âge min. compte", value=f"{config['min_account_age']} jour(s)" if config['min_account_age'] else "Désactivé", inline=True)

        alert_ch = interaction.guild.get_channel(config["alert_channel_id"]) if config.get("alert_channel_id") else None
        embed.add_field(name="Salon d'alerte",  value=alert_ch.mention if alert_ch else "❌ Non configuré", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @antiraid_group.command(name="toggle", description="Active ou désactive l'anti-raid")
    @app_commands.describe(activer="Activer ou désactiver")
    @app_commands.default_permissions(manage_guild=True)
    async def ar_toggle(self, interaction: discord.Interaction, activer: bool):
        await self.bot.db.update_antiraid_setting(interaction.guild.id, "enabled", activer)
        state = "activé 🛡️" if activer else "désactivé"
        await interaction.response.send_message(f"Anti-raid {state}.")

    @antiraid_group.command(name="config", description="Configure les paramètres anti-raid")
    @app_commands.describe(
        seuil="Nombre de joins pour déclencher (défaut : 10)",
        fenetre="Fenêtre de temps en secondes (défaut : 30)",
        action="Action à effectuer",
        age_min="Âge minimum du compte en jours (0 = désactivé)",
        salon_alerte="Salon où envoyer les alertes"
    )
    @app_commands.choices(action=ACTION_CHOICES)
    @app_commands.default_permissions(manage_guild=True)
    async def ar_config(
        self,
        interaction: discord.Interaction,
        seuil: int = 10,
        fenetre: int = 30,
        action: str = "kick",
        age_min: int = 0,
        salon_alerte: discord.TextChannel = None
    ):
        db  = self.bot.db
        gid = interaction.guild.id
        await db.update_antiraid_setting(gid, "join_threshold",   seuil)
        await db.update_antiraid_setting(gid, "join_window",      fenetre)
        await db.update_antiraid_setting(gid, "action",           action)
        await db.update_antiraid_setting(gid, "min_account_age",  max(0, age_min))
        if salon_alerte:
            await db.update_antiraid_setting(gid, "alert_channel_id", salon_alerte.id)

        embed = discord.Embed(title="✅ Anti-Raid configuré", color=discord.Color.green())
        embed.add_field(name="Seuil",      value=f"{seuil} joins / {fenetre}s", inline=True)
        embed.add_field(name="Action",     value=f"`{action}`",                  inline=True)
        embed.add_field(name="Âge min.",   value=f"{age_min}j" if age_min else "Désactivé", inline=True)
        if salon_alerte:
            embed.add_field(name="Alertes", value=salon_alerte.mention, inline=True)
        await interaction.response.send_message(embed=embed)

    @antiraid_group.command(name="lockdown", description="Verrouille manuellement tout le serveur")
    @app_commands.describe(raison="Raison du lockdown")
    @app_commands.default_permissions(manage_guild=True)
    async def ar_lockdown(self, interaction: discord.Interaction, raison: str = "Lockdown manuel"):
        await interaction.response.defer()
        await self._lockdown(interaction.guild)
        embed = discord.Embed(
            title="🔒 LOCKDOWN ACTIVÉ",
            description=f"Tous les salons texte sont verrouillés.\n**Raison :** {raison}",
            color=discord.Color.red()
        )
        embed.set_footer(text="Utilisez /antiraid unlock pour lever le lockdown.")
        await interaction.followup.send(embed=embed)

        if logs := self.bot.get_cog("Logs"):
            await logs.send_log(interaction.guild, embed)

    @antiraid_group.command(name="unlock", description="Lève le lockdown du serveur")
    @app_commands.default_permissions(manage_guild=True)
    async def ar_unlock(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self._unlock(interaction.guild)
        embed = discord.Embed(
            title="🔓 LOCKDOWN LEVÉ",
            description="Les salons texte sont de nouveau accessibles.",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed)

        if logs := self.bot.get_cog("Logs"):
            await logs.send_log(interaction.guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiRaid(bot))
