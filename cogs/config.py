import discord
from discord import app_commands
from discord.ext import commands
from utils.i18n import t, SUPPORTED


def get_logs(bot: commands.Bot):
    return bot.get_cog("Logs")


class Config(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /config ───────────────────────────────────────────────────────────────

    @app_commands.command(name="config", description="Affiche la configuration actuelle du bot")
    @app_commands.default_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction):
        settings = await self.bot.db.get_guild_settings(interaction.guild.id)
        lang = settings.get("language") or "fr"

        def channel_str(cid):
            if not cid:
                return t(lang, "cfg.not_set")
            ch = interaction.guild.get_channel(cid)
            return ch.mention if ch else t(lang, "cfg.channel_missing", id=cid)

        def role_str(rid):
            if not rid:
                return t(lang, "cfg.not_set")
            r = interaction.guild.get_role(rid)
            return r.mention if r else t(lang, "cfg.role_missing", id=rid)

        embed = discord.Embed(
            title=t(lang, "cfg.title", server=interaction.guild.name),
            color=discord.Color.blurple()
        )
        embed.add_field(name=t(lang, "cfg.log_channel"),     value=channel_str(settings.get("log_channel_id")),     inline=True)
        embed.add_field(name=t(lang, "cfg.welcome_channel"), value=channel_str(settings.get("welcome_channel_id")), inline=True)
        embed.add_field(name=t(lang, "cfg.goodbye_channel"), value=channel_str(settings.get("goodbye_channel_id")), inline=True)
        embed.add_field(name=t(lang, "cfg.autorole"),        value=role_str(settings.get("autorole_id")),           inline=True)
        embed.add_field(name=t(lang, "cfg.language_field"),  value=f"`{lang}`",                                     inline=True)
        embed.add_field(
            name=t(lang, "cfg.welcome_msg"),
            value=f"`{settings.get('welcome_message') or t(lang, 'cfg.not_set')}`",
            inline=False
        )
        embed.add_field(
            name=t(lang, "cfg.goodbye_msg"),
            value=f"`{settings.get('goodbye_message') or t(lang, 'cfg.not_set')}`",
            inline=False
        )
        embed.set_footer(text=t(lang, "cfg.footer"))
        await interaction.response.send_message(embed=embed)

    # ── /setlanguage ──────────────────────────────────────────────────────────

    @app_commands.command(name="setlanguage", description="Définit la langue du bot / Set the bot language")
    @app_commands.describe(langue="Langue / Language (fr, en)")
    @app_commands.default_permissions(manage_guild=True)
    async def setlanguage(self, interaction: discord.Interaction, langue: str):
        lang = langue.lower().strip()
        if lang not in SUPPORTED:
            cur_lang = await self.bot.db.get_guild_lang(interaction.guild_id)
            return await interaction.response.send_message(
                t(cur_lang, "cfg.language_invalid", langs=", ".join(sorted(SUPPORTED))),
                ephemeral=True
            )
        await self.bot.db.update_guild_setting(interaction.guild.id, "language", lang)
        await interaction.response.send_message(t(lang, "cfg.language_success", lang=lang))
        if logs := get_logs(self.bot):
            await logs.log_config_change(interaction.guild, interaction.user, t(lang, "cfg.language_field"), lang)

    # ── /setlogs ──────────────────────────────────────────────────────────────

    @app_commands.command(name="setlogs", description="Définit le salon de logs de modération")
    @app_commands.describe(salon="Le salon où envoyer les logs")
    @app_commands.default_permissions(manage_guild=True)
    async def setlogs(self, interaction: discord.Interaction, salon: discord.TextChannel):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        await self.bot.db.update_guild_setting(interaction.guild.id, "log_channel_id", salon.id)
        await interaction.response.send_message(t(lang, "cfg.setlogs_success", channel=salon.mention))
        if logs := get_logs(self.bot):
            await logs.log_config_change(interaction.guild, interaction.user, t(lang, "cfg.log_channel"), salon.mention)

    # ── /setwelcome ───────────────────────────────────────────────────────────

    @app_commands.command(name="setwelcome", description="Définit le salon et le message de bienvenue")
    @app_commands.describe(
        salon="Le salon de bienvenue",
        message="Le message (variables: {mention}, {name}, {server}, {count})"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def setwelcome(self, interaction: discord.Interaction, salon: discord.TextChannel, message: str = None):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        await self.bot.db.update_guild_setting(interaction.guild.id, "welcome_channel_id", salon.id)
        if message:
            await self.bot.db.update_guild_setting(interaction.guild.id, "welcome_message", message)
        suffix = t(lang, "cfg.setwelcome_msg_suffix", message=message) if message else ""
        await interaction.response.send_message(t(lang, "cfg.setwelcome_success", channel=salon.mention) + suffix)
        if logs := get_logs(self.bot):
            await logs.log_config_change(interaction.guild, interaction.user, t(lang, "cfg.welcome_channel"), salon.mention)

    # ── /setgoodbye ───────────────────────────────────────────────────────────

    @app_commands.command(name="setgoodbye", description="Définit le salon et le message d'au revoir")
    @app_commands.describe(
        salon="Le salon d'au revoir",
        message="Le message (variables: {name}, {server})"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def setgoodbye(self, interaction: discord.Interaction, salon: discord.TextChannel, message: str = None):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        await self.bot.db.update_guild_setting(interaction.guild.id, "goodbye_channel_id", salon.id)
        if message:
            await self.bot.db.update_guild_setting(interaction.guild.id, "goodbye_message", message)
        await interaction.response.send_message(t(lang, "cfg.setgoodbye_success", channel=salon.mention))
        if logs := get_logs(self.bot):
            await logs.log_config_change(interaction.guild, interaction.user, t(lang, "cfg.goodbye_channel"), salon.mention)

    # ── /setautorole ──────────────────────────────────────────────────────────

    @app_commands.command(name="setautorole", description="Définit le rôle automatique donné aux nouveaux membres")
    @app_commands.describe(role="Le rôle à attribuer automatiquement")
    @app_commands.default_permissions(manage_guild=True)
    async def setautorole(self, interaction: discord.Interaction, role: discord.Role):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(t(lang, "cfg.autorole_too_high"), ephemeral=True)
        await self.bot.db.update_guild_setting(interaction.guild.id, "autorole_id", role.id)
        await interaction.response.send_message(t(lang, "cfg.setautorole_success", role=role.mention))
        if logs := get_logs(self.bot):
            await logs.log_config_change(interaction.guild, interaction.user, t(lang, "cfg.autorole"), role.mention)


async def setup(bot: commands.Bot):
    await bot.add_cog(Config(bot))
