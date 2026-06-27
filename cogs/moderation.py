import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone
from utils.helpers import parse_duration, duration_to_str


def get_logs(bot: commands.Bot):
    return bot.get_cog("Logs")


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_temp_bans.start()

    def cog_unload(self):
        self.check_temp_bans.cancel()

    # ── Hierarchy check ──────────────────────────────────────────────────────

    def _can_act_on(self, interaction: discord.Interaction, target: discord.Member) -> bool:
        if target == interaction.guild.owner:
            return False
        if target.top_role >= interaction.guild.me.top_role:
            return False
        if target.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
            return False
        return True

    # ── /kick ────────────────────────────────────────────────────────────────

    @app_commands.command(name="kick", description="Expulse un membre du serveur")
    @app_commands.describe(membre="Le membre à expulser", raison="Raison de l'expulsion")
    @app_commands.default_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison fournie"):
        if not self._can_act_on(interaction, membre):
            return await interaction.response.send_message("❌ Je ne peux pas agir sur ce membre.", ephemeral=True)
        try:
            await membre.send(f"Tu as été expulsé de **{interaction.guild.name}**.\n**Raison :** {raison}")
        except discord.Forbidden:
            pass
        await membre.kick(reason=raison)
        embed = discord.Embed(
            title="👢 Membre expulsé",
            description=f"**{membre}** a été expulsé.",
            color=discord.Color.orange()
        )
        embed.add_field(name="Raison", value=raison)
        await interaction.response.send_message(embed=embed)
        if logs := get_logs(self.bot):
            await logs.log_kick(interaction.guild, membre, interaction.user, raison)

    # ── /ban ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="ban", description="Bannit un membre (permanent ou temporaire)")
    @app_commands.describe(
        membre="Le membre à bannir",
        durée="Durée du ban (ex: 10m, 2h, 1d, 1w) — laisser vide pour permanent",
        raison="Raison du ban"
    )
    @app_commands.default_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, membre: discord.Member, durée: str = None, raison: str = "Aucune raison fournie"):
        if not self._can_act_on(interaction, membre):
            return await interaction.response.send_message("❌ Je ne peux pas agir sur ce membre.", ephemeral=True)

        unban_at = None
        duration_label = None
        if durée:
            try:
                seconds, delta = parse_duration(durée)
                unban_at = datetime.now(timezone.utc) + delta
                duration_label = duration_to_str(durée)
            except ValueError as e:
                return await interaction.response.send_message(f"❌ {e}", ephemeral=True)

        try:
            dm_msg = f"Tu as été banni de **{interaction.guild.name}**.\n**Raison :** {raison}"
            if duration_label:
                dm_msg += f"\n**Durée :** {duration_label}"
            await membre.send(dm_msg)
        except discord.Forbidden:
            pass

        await membre.ban(reason=raison, delete_message_days=0)

        if unban_at:
            await self.bot.db.add_temp_ban(
                interaction.guild.id, membre.id, interaction.user.id, raison, unban_at
            )

        embed = discord.Embed(
            title="🔨 Membre banni",
            description=f"**{membre}** a été banni.",
            color=discord.Color.red()
        )
        embed.add_field(name="Raison", value=raison, inline=False)
        if duration_label:
            embed.add_field(name="Durée", value=duration_label, inline=True)
            embed.add_field(name="Fin du ban", value=discord.utils.format_dt(unban_at, 'R'), inline=True)
        await interaction.response.send_message(embed=embed)
        if logs := get_logs(self.bot):
            await logs.log_ban(interaction.guild, membre, interaction.user, raison, duration_label)

    # ── /unban ───────────────────────────────────────────────────────────────

    @app_commands.command(name="unban", description="Débannie un utilisateur par son ID")
    @app_commands.describe(user_id="L'ID de l'utilisateur", raison="Raison du déban")
    @app_commands.default_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str, raison: str = "Aucune raison fournie"):
        try:
            uid = int(user_id)
        except ValueError:
            return await interaction.response.send_message("❌ ID invalide.", ephemeral=True)
        try:
            user = await self.bot.fetch_user(uid)
            await interaction.guild.unban(user, reason=raison)
            await self.bot.db.remove_temp_ban(interaction.guild.id, uid)
            embed = discord.Embed(
                title="✅ Membre débanni",
                description=f"**{user}** a été débanni.",
                color=discord.Color.green()
            )
            embed.add_field(name="Raison", value=raison)
            await interaction.response.send_message(embed=embed)
            if logs := get_logs(self.bot):
                await logs.log_unban(interaction.guild, user, interaction.user, raison)
        except discord.NotFound:
            await interaction.response.send_message("❌ Cet utilisateur n'est pas banni.", ephemeral=True)

    # ── /mute ────────────────────────────────────────────────────────────────

    @app_commands.command(name="mute", description="Rend muet un membre (timeout Discord natif)")
    @app_commands.describe(
        membre="Le membre à muter",
        durée="Durée du mute (ex: 10m, 2h, 1d) — max 28j",
        raison="Raison du mute"
    )
    @app_commands.default_permissions(moderate_members=True)
    async def mute(self, interaction: discord.Interaction, membre: discord.Member, durée: str, raison: str = "Aucune raison fournie"):
        if not self._can_act_on(interaction, membre):
            return await interaction.response.send_message("❌ Je ne peux pas agir sur ce membre.", ephemeral=True)
        try:
            seconds, delta = parse_duration(durée)
        except ValueError as e:
            return await interaction.response.send_message(f"❌ {e}", ephemeral=True)

        if seconds > 2419200:
            return await interaction.response.send_message("❌ La durée maximale est de 28 jours.", ephemeral=True)

        until = datetime.now(timezone.utc) + delta
        await membre.timeout(until, reason=raison)
        duration_label = duration_to_str(durée)

        embed = discord.Embed(
            title="🔇 Membre muté",
            description=f"**{membre.mention}** a été rendu muet.",
            color=discord.Color.dark_orange()
        )
        embed.add_field(name="Durée", value=duration_label, inline=True)
        embed.add_field(name="Fin", value=discord.utils.format_dt(until, 'R'), inline=True)
        embed.add_field(name="Raison", value=raison, inline=False)
        await interaction.response.send_message(embed=embed)

        try:
            await membre.send(f"Tu as été muté sur **{interaction.guild.name}** pendant {duration_label}.\n**Raison :** {raison}")
        except discord.Forbidden:
            pass

        if logs := get_logs(self.bot):
            await logs.log_mute(interaction.guild, membre, interaction.user, raison, duration_label)

    # ── /unmute ──────────────────────────────────────────────────────────────

    @app_commands.command(name="unmute", description="Retire le mute d'un membre")
    @app_commands.describe(membre="Le membre à démuter", raison="Raison")
    @app_commands.default_permissions(moderate_members=True)
    async def unmute(self, interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison fournie"):
        if not membre.is_timed_out():
            return await interaction.response.send_message("❌ Ce membre n'est pas muté.", ephemeral=True)
        await membre.timeout(None, reason=raison)
        embed = discord.Embed(
            title="🔊 Membre démuté",
            description=f"**{membre.mention}** n'est plus muet.",
            color=discord.Color.green()
        )
        embed.add_field(name="Raison", value=raison)
        await interaction.response.send_message(embed=embed)
        if logs := get_logs(self.bot):
            await logs.log_unmute(interaction.guild, membre, interaction.user, raison)

    # ── /warn ────────────────────────────────────────────────────────────────

    @app_commands.command(name="warn", description="Avertit un membre")
    @app_commands.describe(membre="Le membre à avertir", raison="Raison de l'avertissement")
    @app_commands.default_permissions(manage_messages=True)
    async def warn(self, interaction: discord.Interaction, membre: discord.Member, raison: str):
        if membre.bot:
            return await interaction.response.send_message("❌ Impossible d'avertir un bot.", ephemeral=True)

        warn_id = await self.bot.db.add_warning(interaction.guild.id, membre.id, interaction.user.id, raison)
        total = await self.bot.db.get_warning_count(interaction.guild.id, membre.id)

        embed = discord.Embed(
            title="⚠️ Avertissement",
            description=f"**{membre.mention}** a reçu un avertissement.",
            color=discord.Color.yellow()
        )
        embed.add_field(name="Raison", value=raison, inline=False)
        embed.add_field(name="Total warns", value=str(total), inline=True)
        embed.set_footer(text=f"ID warn : #{warn_id}")
        await interaction.response.send_message(embed=embed)

        try:
            await membre.send(
                f"Tu as reçu un avertissement sur **{interaction.guild.name}**.\n"
                f"**Raison :** {raison}\n**Total warns :** {total}"
            )
        except discord.Forbidden:
            pass

        if logs := get_logs(self.bot):
            await logs.log_warn(interaction.guild, membre, interaction.user, raison, warn_id, total)

    # ── /unwarn ──────────────────────────────────────────────────────────────

    @app_commands.command(name="unwarn", description="Supprime un avertissement par son ID")
    @app_commands.describe(id_warn="L'ID de l'avertissement à supprimer")
    @app_commands.default_permissions(manage_messages=True)
    async def unwarn(self, interaction: discord.Interaction, id_warn: int):
        removed = await self.bot.db.remove_warning(id_warn, interaction.guild.id)
        if removed:
            await interaction.response.send_message(f"✅ Avertissement `#{id_warn}` supprimé.")
        else:
            await interaction.response.send_message(f"❌ Aucun avertissement `#{id_warn}` trouvé.", ephemeral=True)

    # ── /warnings ────────────────────────────────────────────────────────────

    @app_commands.command(name="warnings", description="Affiche les avertissements d'un membre")
    @app_commands.describe(membre="Le membre dont voir les warns")
    @app_commands.default_permissions(manage_messages=True)
    async def warnings(self, interaction: discord.Interaction, membre: discord.Member):
        warns = await self.bot.db.get_warnings(interaction.guild.id, membre.id)
        embed = discord.Embed(
            title=f"⚠️ Avertissements de {membre}",
            color=discord.Color.yellow()
        )
        if not warns:
            embed.description = "Aucun avertissement."
        else:
            for w in warns[:10]:
                mod = interaction.guild.get_member(w["moderator_id"])
                mod_name = str(mod) if mod else f"ID:{w['moderator_id']}"
                date = discord.utils.format_dt(w["created_at"], 'd')
                embed.add_field(
                    name=f"#{w['id']} — {date}",
                    value=f"**Raison :** {w['reason']}\n**Modérateur :** {mod_name}",
                    inline=False
                )
            embed.set_footer(text=f"{len(warns)} avertissement(s) au total")
        await interaction.response.send_message(embed=embed)

    # ── /clearwarnings ───────────────────────────────────────────────────────

    @app_commands.command(name="clearwarnings", description="Efface tous les avertissements d'un membre")
    @app_commands.describe(membre="Le membre dont effacer les warns")
    @app_commands.default_permissions(manage_guild=True)
    async def clearwarnings(self, interaction: discord.Interaction, membre: discord.Member):
        count = await self.bot.db.clear_warnings(interaction.guild.id, membre.id)
        await interaction.response.send_message(
            f"✅ **{count}** avertissement(s) supprimé(s) pour {membre.mention}."
        )

    # ── /clear ───────────────────────────────────────────────────────────────

    @app_commands.command(name="clear", description="Supprime des messages en masse")
    @app_commands.describe(
        nombre="Nombre de messages à supprimer (1–100)",
        membre="Ne supprimer que les messages de ce membre (optionnel)"
    )
    @app_commands.default_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, nombre: app_commands.Range[int, 1, 100], membre: discord.Member = None):
        await interaction.response.defer(ephemeral=True)

        def check(msg: discord.Message) -> bool:
            return membre is None or msg.author == membre

        deleted = await interaction.channel.purge(limit=nombre, check=check)
        await interaction.followup.send(f"✅ **{len(deleted)}** message(s) supprimé(s).", ephemeral=True)

        if logs := get_logs(self.bot):
            await logs.log_clear(interaction.guild, interaction.channel, interaction.user, len(deleted))

    # ── /slowmode ────────────────────────────────────────────────────────────

    @app_commands.command(name="slowmode", description="Active ou désactive le mode lent sur le salon")
    @app_commands.describe(secondes="Délai en secondes (0 pour désactiver, max 21600)")
    @app_commands.default_permissions(manage_channels=True)
    async def slowmode(self, interaction: discord.Interaction, secondes: app_commands.Range[int, 0, 21600] = 0):
        await interaction.channel.edit(slowmode_delay=secondes)
        if secondes == 0:
            await interaction.response.send_message("✅ Mode lent désactivé.")
        else:
            await interaction.response.send_message(f"✅ Mode lent activé : **{secondes}** seconde(s).")

    # ── /lock ────────────────────────────────────────────────────────────────

    @app_commands.command(name="lock", description="Verrouille le salon actuel")
    @app_commands.describe(raison="Raison du verrouillage")
    @app_commands.default_permissions(manage_channels=True)
    async def lock(self, interaction: discord.Interaction, raison: str = "Aucune raison fournie"):
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        embed = discord.Embed(
            title="🔒 Salon verrouillé",
            description=f"**Raison :** {raison}",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        if logs := get_logs(self.bot):
            await logs.log_lock(interaction.guild, interaction.channel, interaction.user, raison, True)

    # ── /unlock ──────────────────────────────────────────────────────────────

    @app_commands.command(name="unlock", description="Déverrouille le salon actuel")
    @app_commands.describe(raison="Raison du déverrouillage")
    @app_commands.default_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction, raison: str = "Aucune raison fournie"):
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        embed = discord.Embed(
            title="🔓 Salon déverrouillé",
            description=f"**Raison :** {raison}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)
        if logs := get_logs(self.bot):
            await logs.log_lock(interaction.guild, interaction.channel, interaction.user, raison, False)

    # ── Background task: check temp bans ─────────────────────────────────────

    @tasks.loop(minutes=1)
    async def check_temp_bans(self):
        expired = await self.bot.db.get_expired_bans()
        for ban in expired:
            guild = self.bot.get_guild(ban["guild_id"])
            if not guild:
                continue
            try:
                user = await self.bot.fetch_user(ban["user_id"])
                await guild.unban(user, reason="Durée du ban expirée")
            except (discord.NotFound, discord.Forbidden):
                pass
            finally:
                await self.bot.db.remove_temp_ban(ban["guild_id"], ban["user_id"])

    @check_temp_bans.before_loop
    async def before_check_temp_bans(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
