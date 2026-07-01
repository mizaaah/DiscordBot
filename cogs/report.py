import discord
from datetime import timedelta
from discord import app_commands
from discord.ext import commands
from utils.colors import Colors
from utils.embeds import error_embed, success_embed
from utils.i18n import t


# ══════════════════════════════════════════════════════════════════════════════
#  Persistent view
# ══════════════════════════════════════════════════════════════════════════════

class ReportView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    async def _get_report(self, interaction: discord.Interaction, lang: str) -> dict | None:
        report = await interaction.client.db.get_report_by_msg(interaction.message.id)
        if not report:
            await interaction.response.send_message(embed=error_embed(t(lang, "report.not_found")), ephemeral=True)
        return report

    async def _require_mod(self, interaction: discord.Interaction, lang: str) -> bool:
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(embed=error_embed(t(lang, "report.mods_only")), ephemeral=True)
            return False
        return True

    def _mark_resolved(self, embed: discord.Embed, by: discord.Member, lang: str) -> discord.Embed:
        embed.color = Colors.SUCCESS
        embed.add_field(name=t(lang, "report.resolved_by"), value=by.mention, inline=True)
        return embed

    @discord.ui.button(label="✅ Résolu", style=discord.ButtonStyle.success, custom_id="rep_resolve", row=0)
    async def btn_resolve(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang = await interaction.client.db.get_guild_lang(interaction.guild_id)
        if not await self._require_mod(interaction, lang): return
        report = await self._get_report(interaction, lang)
        if not report: return
        if report["resolved"]:
            return await interaction.response.send_message(embed=error_embed(t(lang, "report.already_resolved")), ephemeral=True)
        await interaction.client.db.resolve_report(report["id"])
        embed = self._mark_resolved(interaction.message.embeds[0].copy(), interaction.user, lang)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🔇 Mute 1h", style=discord.ButtonStyle.secondary, custom_id="rep_mute", row=0)
    async def btn_mute(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang = await interaction.client.db.get_guild_lang(interaction.guild_id)
        if not await self._require_mod(interaction, lang): return
        report = await self._get_report(interaction, lang)
        if not report: return
        member = interaction.guild.get_member(report["reported_id"])
        if not member:
            return await interaction.response.send_message(embed=error_embed(t(lang, "report.member_not_found_left")), ephemeral=True)
        try:
            await member.timeout(timedelta(hours=1), reason=f"[Report #{report['id']}] {report['reason']}")
            await interaction.response.send_message(embed=success_embed(t(lang, "report.muted", member=member.mention)), ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(embed=error_embed(t(lang, "report.no_perms")), ephemeral=True)

    @discord.ui.button(label="👢 Kick", style=discord.ButtonStyle.danger, custom_id="rep_kick", row=0)
    async def btn_kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang = await interaction.client.db.get_guild_lang(interaction.guild_id)
        if not await self._require_mod(interaction, lang): return
        report = await self._get_report(interaction, lang)
        if not report: return
        member = interaction.guild.get_member(report["reported_id"])
        if not member:
            return await interaction.response.send_message(embed=error_embed(t(lang, "report.member_not_found")), ephemeral=True)
        try:
            await member.kick(reason=f"[Report #{report['id']}] {report['reason']}")
            await interaction.client.db.resolve_report(report["id"])
            embed = self._mark_resolved(interaction.message.embeds[0].copy(), interaction.user, lang)
            embed.add_field(name=t(lang, "report.action_field"), value=t(lang, "report.action_kicked"), inline=True)
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.Forbidden:
            await interaction.response.send_message(embed=error_embed(t(lang, "report.no_perms")), ephemeral=True)

    @discord.ui.button(label="🔨 Ban", style=discord.ButtonStyle.danger, custom_id="rep_ban", row=0)
    async def btn_ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang = await interaction.client.db.get_guild_lang(interaction.guild_id)
        if not await self._require_mod(interaction, lang): return
        report = await self._get_report(interaction, lang)
        if not report: return
        member = interaction.guild.get_member(report["reported_id"])
        if not member:
            return await interaction.response.send_message(embed=error_embed(t(lang, "report.member_not_found")), ephemeral=True)
        try:
            await member.ban(reason=f"[Report #{report['id']}] {report['reason']}", delete_message_days=0)
            await interaction.client.db.resolve_report(report["id"])
            embed = self._mark_resolved(interaction.message.embeds[0].copy(), interaction.user, lang)
            embed.add_field(name=t(lang, "report.action_field"), value=t(lang, "report.action_banned"), inline=True)
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.Forbidden:
            await interaction.response.send_message(embed=error_embed(t(lang, "report.no_perms")), ephemeral=True)


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
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        if membre == interaction.user:
            return await interaction.response.send_message(embed=error_embed(t(lang, "report.cant_self")), ephemeral=True)
        if membre.bot:
            return await interaction.response.send_message(embed=error_embed(t(lang, "report.cant_bot")), ephemeral=True)

        settings = await self.bot.db.get_guild_settings(interaction.guild.id)
        report_ch = interaction.guild.get_channel(settings.get("report_channel_id") or 0)
        if not report_ch:
            return await interaction.response.send_message(
                t(lang, "report.no_channel_configured"),
                ephemeral=True
            )

        embed = discord.Embed(
            title=t(lang, "report.new_title"),
            color=Colors.ERROR,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name=t(lang, "report.target_field"),  value=f"{membre.mention}\n`{membre.id}`", inline=True)
        embed.add_field(name=t(lang, "report.by_field"),      value=interaction.user.mention,            inline=True)
        embed.add_field(name=t(lang, "report.channel_field"), value=interaction.channel.mention,         inline=True)
        embed.add_field(name=t(lang, "report.reason_field"),  value=raison,                              inline=False)
        embed.set_thumbnail(url=membre.display_avatar.url)
        embed.set_footer(text=f"ID: {membre.id}")

        view = ReportView(self.bot)
        try:
            msg = await report_ch.send(embed=embed, view=view)
        except discord.Forbidden:
            return await interaction.response.send_message(embed=error_embed(t(lang, "report.cant_send")), ephemeral=True)

        await self.bot.db.create_report(
            interaction.guild.id, msg.id, interaction.user.id, membre.id, raison
        )
        await interaction.response.send_message(
            t(lang, "report.sent"), ephemeral=True
        )

    @app_commands.command(name="setreport", description="Définit le canal de signalement")
    @app_commands.describe(salon="Canal où envoyer les signalements")
    @app_commands.default_permissions(manage_guild=True)
    async def setreport(self, interaction: discord.Interaction, salon: discord.TextChannel):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        await self.bot.db.update_guild_setting(interaction.guild.id, "report_channel_id", salon.id)
        await interaction.response.send_message(embed=success_embed(t(lang, "report.channel_set", channel=salon.mention)))


async def setup(bot: commands.Bot):
    await bot.add_cog(Report(bot))
