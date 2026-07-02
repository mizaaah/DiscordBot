import discord
from discord import app_commands
from discord.ext import commands
from utils.i18n import t, SUPPORTED
from utils.colors import Colors


def get_logs(bot: commands.Bot):
    return bot.get_cog("Logs")


# ══════════════════════════════════════════════════════════════════════════════
#  /setup wizard
# ══════════════════════════════════════════════════════════════════════════════

class SetupCategorySelect(discord.ui.Select):
    def __init__(self, lang: str):
        options = [
            discord.SelectOption(label=t(lang, "setup.opt_logs"),     value="logs",     emoji="🪵"),
            discord.SelectOption(label=t(lang, "setup.opt_welcome"),  value="welcome",  emoji="👋"),
            discord.SelectOption(label=t(lang, "setup.opt_goodbye"),  value="goodbye",  emoji="🚪"),
            discord.SelectOption(label=t(lang, "setup.opt_autorole"), value="autorole", emoji="🎭"),
            discord.SelectOption(label=t(lang, "setup.opt_report"),   value="report",   emoji="🚨"),
            discord.SelectOption(label=t(lang, "setup.opt_language"), value="language", emoji="🌐"),
        ]
        super().__init__(placeholder=t(lang, "setup.select_placeholder"), options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        await view.show_category(interaction, self.values[0])


class SetupChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, lang: str, setting_key: str, placeholder_key: str):
        super().__init__(placeholder=t(lang, placeholder_key), channel_types=[discord.ChannelType.text], row=1)
        self.setting_key = setting_key

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        channel = self.values[0]
        await interaction.client.db.update_guild_setting(interaction.guild.id, self.setting_key, channel.id)
        await view.refresh(interaction, t(view.lang, "setup.saved_channel", channel=channel.mention))


class SetupRoleSelect(discord.ui.RoleSelect):
    def __init__(self, lang: str):
        super().__init__(placeholder=t(lang, "setup.autorole_placeholder"), row=1)

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        role = self.values[0]
        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(t(view.lang, "cfg.autorole_too_high"), ephemeral=True)
        await interaction.client.db.update_guild_setting(interaction.guild.id, "autorole_id", role.id)
        await view.refresh(interaction, t(view.lang, "setup.saved_role", role=role.mention))


class SetupMessageModal(discord.ui.Modal):
    message = discord.ui.TextInput(label="Message", style=discord.TextStyle.long, required=False, max_length=1000)

    def __init__(self, setup_view: "SetupView", setting_key: str, title: str, current: str = None):
        super().__init__(title=title)
        self._setup_view = setup_view
        self.setting_key = setting_key
        if current:
            self.message.default = current

    async def on_submit(self, interaction: discord.Interaction):
        value = self.message.value.strip() or None
        if value:
            await interaction.client.db.update_guild_setting(interaction.guild.id, self.setting_key, value)
        await self._setup_view.refresh(interaction, t(self._setup_view.lang, "setup.saved_message"))


class SetupMessageButton(discord.ui.Button):
    def __init__(self, lang: str, setting_key: str, modal_title: str, current: str = None):
        super().__init__(label=t(lang, "setup.customize_message_btn"), style=discord.ButtonStyle.secondary, row=2)
        self.setting_key = setting_key
        self.modal_title = modal_title
        self.current = current

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        await interaction.response.send_modal(SetupMessageModal(view, self.setting_key, self.modal_title, self.current))


class SetupLanguageSelect(discord.ui.Select):
    def __init__(self, lang: str):
        options = [
            discord.SelectOption(label="Français", value="fr", emoji="🇫🇷"),
            discord.SelectOption(label="English",  value="en", emoji="🇬🇧"),
        ]
        super().__init__(placeholder=t(lang, "setup.language_placeholder"), options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        new_lang = self.values[0]
        await interaction.client.db.update_guild_setting(interaction.guild.id, "language", new_lang)
        view.lang = new_lang
        await view.refresh(interaction, t(new_lang, "setup.saved_language"))


class SetupBackButton(discord.ui.Button):
    def __init__(self, lang: str):
        super().__init__(label=t(lang, "setup.back_btn"), style=discord.ButtonStyle.danger, row=3)

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        await view.show_home(interaction)


class SetupView(discord.ui.View):
    def __init__(self, bot: commands.Bot, lang: str, guild_id: int):
        super().__init__(timeout=300)
        self.bot = bot
        self.lang = lang
        self.guild_id = guild_id
        self._build_home()

    def _build_home(self):
        self.clear_items()
        self.add_item(SetupCategorySelect(self.lang))

    async def build_home_embed(self, guild: discord.Guild) -> discord.Embed:
        settings = await self.bot.db.get_guild_settings(self.guild_id)
        lang = self.lang

        def ch(cid):
            if not cid:
                return t(lang, "cfg.not_set")
            c = guild.get_channel(cid)
            return c.mention if c else t(lang, "cfg.channel_missing", id=cid)

        def role(rid):
            if not rid:
                return t(lang, "cfg.not_set")
            r = guild.get_role(rid)
            return r.mention if r else t(lang, "cfg.role_missing", id=rid)

        embed = discord.Embed(title=t(lang, "setup.home_title"), description=t(lang, "setup.home_desc"), color=Colors.INFO)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name=t(lang, "setup.opt_logs"),     value=ch(settings.get("log_channel_id")),      inline=True)
        embed.add_field(name=t(lang, "setup.opt_welcome"),  value=ch(settings.get("welcome_channel_id")),  inline=True)
        embed.add_field(name=t(lang, "setup.opt_goodbye"),  value=ch(settings.get("goodbye_channel_id")),  inline=True)
        embed.add_field(name=t(lang, "setup.opt_autorole"), value=role(settings.get("autorole_id")),       inline=True)
        embed.add_field(name=t(lang, "setup.opt_report"),   value=ch(settings.get("report_channel_id")),   inline=True)
        embed.add_field(name=t(lang, "setup.opt_language"), value=f"`{settings.get('language') or 'fr'}`", inline=True)
        return embed

    async def show_home(self, interaction: discord.Interaction):
        self._build_home()
        embed = await self.build_home_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    async def show_category(self, interaction: discord.Interaction, category: str):
        settings = await self.bot.db.get_guild_settings(self.guild_id)
        lang = self.lang
        self.clear_items()
        self.add_item(SetupCategorySelect(lang))

        if category == "logs":
            self.add_item(SetupChannelSelect(lang, "log_channel_id", "setup.logs_placeholder"))
        elif category == "welcome":
            self.add_item(SetupChannelSelect(lang, "welcome_channel_id", "setup.welcome_placeholder"))
            self.add_item(SetupMessageButton(lang, "welcome_message", t(lang, "setup.welcome_modal_title"), settings.get("welcome_message")))
        elif category == "goodbye":
            self.add_item(SetupChannelSelect(lang, "goodbye_channel_id", "setup.goodbye_placeholder"))
            self.add_item(SetupMessageButton(lang, "goodbye_message", t(lang, "setup.goodbye_modal_title"), settings.get("goodbye_message")))
        elif category == "autorole":
            self.add_item(SetupRoleSelect(lang))
        elif category == "report":
            self.add_item(SetupChannelSelect(lang, "report_channel_id", "setup.report_placeholder"))
        elif category == "language":
            self.add_item(SetupLanguageSelect(lang))

        self.add_item(SetupBackButton(lang))
        embed = discord.Embed(
            title=t(lang, f"setup.opt_{category}"),
            description=t(lang, f"setup.{category}_desc"),
            color=Colors.INFO
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def refresh(self, interaction: discord.Interaction, confirm_text: str):
        self._build_home()
        embed = await self.build_home_embed(interaction.guild)
        embed.add_field(name=t(self.lang, "setup.saved_field"), value=confirm_text, inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class Config(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /setup ────────────────────────────────────────────────────────────────

    @app_commands.command(name="setup", description="Assistant de configuration interactif du bot")
    @app_commands.default_permissions(manage_guild=True)
    async def setup_wizard(self, interaction: discord.Interaction):
        lang  = await self.bot.db.get_guild_lang(interaction.guild_id)
        view  = SetupView(self.bot, lang, interaction.guild.id)
        embed = await view.build_home_embed(interaction.guild)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

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
            color=Colors.INFO
        )
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
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
    @app_commands.describe(langue="Langue / Language")
    @app_commands.choices(langue=[
        app_commands.Choice(name="Français", value="fr"),
        app_commands.Choice(name="English", value="en"),
    ])
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
