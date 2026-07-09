import discord
from discord import app_commands
from discord.ext import commands
from utils.i18n import t, SUPPORTED
from utils.colors import Colors
from utils.embeds import error_embed, success_embed


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
            discord.SelectOption(label="AutoMod",                     value="automod",  emoji="🛡️"),
            discord.SelectOption(label="Anti-Raid",                   value="antiraid", emoji="⚔️"),
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
            return await interaction.response.send_message(embed=error_embed(t(view.lang, "cfg.autorole_too_high")), ephemeral=True)
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


class AutomodToggleButton(discord.ui.Button):
    def __init__(self, current: bool):
        super().__init__(label="Désactiver AutoMod" if current else "Activer AutoMod", style=discord.ButtonStyle.danger if current else discord.ButtonStyle.success, row=1)
        self.current = current
    
    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        new_val = 0 if self.current else 1
        await interaction.client.db.update_automod_setting(interaction.guild.id, "enabled", new_val)
        await view.refresh(interaction, "AutoMod a été " + ("désactivé" if self.current else "activé"))

class AntiraidToggleButton(discord.ui.Button):
    def __init__(self, current: bool):
        super().__init__(label="Désactiver Anti-Raid" if current else "Activer Anti-Raid", style=discord.ButtonStyle.danger if current else discord.ButtonStyle.success, row=1)
        self.current = current
    
    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        new_val = 0 if self.current else 1
        await interaction.client.db.update_antiraid_setting(interaction.guild.id, "enabled", new_val)
        await view.refresh(interaction, "Anti-Raid a été " + ("désactivé" if self.current else "activé"))

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

        embed = discord.Embed(
            title=t(lang, f"setup.opt_{category}") if category not in ["automod", "antiraid"] else "",
            description=t(lang, f"setup.{category}_desc") if category not in ["automod", "antiraid"] else "",
            color=Colors.INFO
        )

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
        elif category == "automod":
            am_cfg = await self.bot.db.get_automod_config(self.guild_id)
            self.add_item(AutomodToggleButton(bool(am_cfg["enabled"])))
            embed.title = "🛡️ Configuration AutoMod"
            embed.description = "Activez ou désactivez l'AutoMod global. Pour la configuration fine, utilisez `/automod status`."
        elif category == "antiraid":
            ar_cfg = await self.bot.db.get_antiraid_config(self.guild_id)
            self.add_item(AntiraidToggleButton(bool(ar_cfg["enabled"])))
            embed.title = "⚔️ Configuration Anti-Raid"
            embed.description = "Activez ou désactivez l'Anti-Raid global. Pour la configuration fine, utilisez `/antiraid status`."

        self.add_item(SetupBackButton(lang))
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

    # (Standalone config commands removed in favor of /setup)

async def setup(bot: commands.Bot):
    await bot.add_cog(Config(bot))
