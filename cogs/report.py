import discord
from datetime import timedelta
from discord import app_commands
from discord.ext import commands
from utils.colors import Colors


# ══════════════════════════════════════════════════════════════════════════════
#  Persistent view
# ══════════════════════════════════════════════════════════════════════════════

class ReportView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    async def _get_report(self, interaction: discord.Interaction) -> dict | None:
        report = await interaction.client.db.get_report_by_msg(interaction.message.id)
        if not report:
            await interaction.response.send_message("❌ Signalement introuvable.", ephemeral=True)
        return report

    async def _require_mod(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ Réservé aux modérateurs.", ephemeral=True)
            return False
        return True

    def _mark_resolved(self, embed: discord.Embed, by: discord.Member) -> discord.Embed:
        embed.color = Colors.SUCCESS
        embed.add_field(name="✅ Résolu par", value=by.mention, inline=True)
        return embed

    @discord.ui.button(label="✅ Résolu", style=discord.ButtonStyle.success, custom_id="rep_resolve", row=0)
    async def btn_resolve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._require_mod(interaction): return
        report = await self._get_report(interaction)
        if not report: return
        if report["resolved"]:
            return await interaction.response.send_message("❌ Déjà résolu.", ephemeral=True)
        await interaction.client.db.resolve_report(report["id"])
        embed = self._mark_resolved(interaction.message.embeds[0].copy(), interaction.user)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🔇 Mute 1h", style=discord.ButtonStyle.secondary, custom_id="rep_mute", row=0)
    async def btn_mute(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._require_mod(interaction): return
        report = await self._get_report(interaction)
        if not report: return
        member = interaction.guild.get_member(report["reported_id"])
        if not member:
            return await interaction.response.send_message("❌ Membre introuvable (a quitté ?).", ephemeral=True)
        try:
            await member.timeout(timedelta(hours=1), reason=f"[Report #{report['id']}] {report['reason']}")
            await interaction.response.send_message(f"✅ {member.mention} muté 1h.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Permissions insuffisantes.", ephemeral=True)

    @discord.ui.button(label="👢 Kick", style=discord.ButtonStyle.danger, custom_id="rep_kick", row=0)
    async def btn_kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._require_mod(interaction): return
        report = await self._get_report(interaction)
        if not report: return
        member = interaction.guild.get_member(report["reported_id"])
        if not member:
            return await interaction.response.send_message("❌ Membre introuvable.", ephemeral=True)
        try:
            await member.kick(reason=f"[Report #{report['id']}] {report['reason']}")
            await interaction.client.db.resolve_report(report["id"])
            embed = self._mark_resolved(interaction.message.embeds[0].copy(), interaction.user)
            embed.add_field(name="Action", value="👢 Expulsé", inline=True)
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Permissions insuffisantes.", ephemeral=True)

    @discord.ui.button(label="🔨 Ban", style=discord.ButtonStyle.danger, custom_id="rep_ban", row=0)
    async def btn_ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._require_mod(interaction): return
        report = await self._get_report(interaction)
        if not report: return
        member = interaction.guild.get_member(report["reported_id"])
        if not member:
            return await interaction.response.send_message("❌ Membre introuvable.", ephemeral=True)
        try:
            await member.ban(reason=f"[Report #{report['id']}] {report['reason']}", delete_message_days=0)
            await interaction.client.db.resolve_report(report["id"])
            embed = self._mark_resolved(interaction.message.embeds[0].copy(), interaction.user)
            embed.add_field(name="Action", value="🔨 Banni", inline=True)
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Permissions insuffisantes.", ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  Cog
# ══════════════════════════════════════════════════════════════════════════════

class Report(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(ReportView(self.bot))

    @app_commands.command(name="report", description="Signale un membre aux modérateurs")
    @app_commands.describe(membre="Le membre à signaler", raison="Raison du signalement")
    async def report(self, interaction: discord.Interaction, membre: discord.Member, raison: str):
        if membre == interaction.user:
            return await interaction.response.send_message("❌ Tu ne peux pas te signaler toi-même.", ephemeral=True)
        if membre.bot:
            return await interaction.response.send_message("❌ Tu ne peux pas signaler un bot.", ephemeral=True)

        settings = await self.bot.db.get_guild_settings(interaction.guild.id)
        report_ch = interaction.guild.get_channel(settings.get("report_channel_id") or 0)
        if not report_ch:
            return await interaction.response.send_message(
                "❌ Aucun canal de signalement configuré. Demande à un admin d'utiliser `/setreport`.",
                ephemeral=True
            )

        embed = discord.Embed(
            title="🚨 Nouveau signalement",
            color=Colors.ERROR,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="🎯 Signalé",      value=f"{membre.mention}\n`{membre.id}`", inline=True)
        embed.add_field(name="👤 Par",           value=interaction.user.mention,            inline=True)
        embed.add_field(name="💬 Salon",         value=interaction.channel.mention,         inline=True)
        embed.add_field(name="📝 Raison",        value=raison,                              inline=False)
        embed.set_thumbnail(url=membre.display_avatar.url)
        embed.set_footer(text=f"ID: {membre.id}")

        view = ReportView(self.bot)
        try:
            msg = await report_ch.send(embed=embed, view=view)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Je ne peux pas envoyer dans le canal de signalement.", ephemeral=True)

        await self.bot.db.create_report(
            interaction.guild.id, msg.id, interaction.user.id, membre.id, raison
        )
        await interaction.response.send_message(
            "✅ Ton signalement a été envoyé aux modérateurs.", ephemeral=True
        )

    @app_commands.command(name="setreport", description="Définit le canal de signalement")
    @app_commands.describe(salon="Canal où envoyer les signalements")
    @app_commands.default_permissions(manage_guild=True)
    async def setreport(self, interaction: discord.Interaction, salon: discord.TextChannel):
        await self.bot.db.update_guild_setting(interaction.guild.id, "report_channel_id", salon.id)
        await interaction.response.send_message(f"✅ Canal de signalement défini sur {salon.mention}.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Report(bot))
