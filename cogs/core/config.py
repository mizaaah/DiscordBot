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


class SetupImageModal(discord.ui.Modal):
    image_url = discord.ui.TextInput(label="URL de l'image (PNG/GIF)", style=discord.TextStyle.short, required=False, max_length=500, placeholder="https://...")

    def __init__(self, setup_view: "SetupView", setting_key: str, title: str, current: str = None):
        super().__init__(title=title)
        self._setup_view = setup_view
        self.setting_key = setting_key
        if current:
            self.image_url.default = current

    async def on_submit(self, interaction: discord.Interaction):
        value = self.image_url.value.strip() or None
        if value:
            await interaction.client.db.update_guild_setting(interaction.guild.id, self.setting_key, value)
        await self._setup_view.refresh(interaction, "L'image a bien été sauvegardée ! 🖼️")


class SetupImageButton(discord.ui.Button):
    def __init__(self, lang: str, setting_key: str, modal_title: str, current: str = None):
        super().__init__(label="🖼️ Ajouter une Bannière", style=discord.ButtonStyle.secondary, row=2)
        self.setting_key = setting_key
        self.modal_title = modal_title
        self.current = current

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        await interaction.response.send_modal(SetupImageModal(view, self.setting_key, self.modal_title, self.current))


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

class AutomodModuleSelect(discord.ui.Select):
    def __init__(self, current_module: str = None):
        options = [
            discord.SelectOption(label="Anti-Spam", value="spam", emoji="🔁", default=current_module=="spam"),
            discord.SelectOption(label="Anti-Liens", value="link", emoji="🔗", default=current_module=="link"),
            discord.SelectOption(label="Anti-Invites", value="invite", emoji="📨", default=current_module=="invite"),
            discord.SelectOption(label="Anti-Majuscules", value="caps", emoji="🔠", default=current_module=="caps"),
            discord.SelectOption(label="Anti-Mentions", value="mention", emoji="📢", default=current_module=="mention"),
            discord.SelectOption(label="Anti-Flood", value="flood", emoji="🌊", default=current_module=="flood"),
        ]
        super().__init__(placeholder="Sélectionner un module à configurer...", options=options, row=2)

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        view.automod_module = self.values[0]
        await view.show_category(interaction, "automod")

class AutomodModuleToggleButton(discord.ui.Button):
    def __init__(self, module: str, current: bool):
        super().__init__(label=f"{'Désactiver' if current else 'Activer'} le module", style=discord.ButtonStyle.danger if current else discord.ButtonStyle.success, row=4)
        self.module = module
        self.current = current

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        new_val = 0 if self.current else 1
        await interaction.client.db.update_automod_setting(interaction.guild.id, f"{self.module}_enabled", new_val)
        await view.refresh(interaction, "Module mis à jour !")

class AutomodActionSelect(discord.ui.Select):
    def __init__(self, module: str, current_action: str):
        self.module = module
        options = [
            discord.SelectOption(label="Warn (Avertissement)", value="warn", emoji="⚠️", default=current_action=="warn"),
            discord.SelectOption(label="Mute (Exclusion temporaire)", value="mute", emoji="🔇", default=current_action=="mute"),
            discord.SelectOption(label="Kick (Expulser)", value="kick", emoji="👢", default=current_action=="kick"),
            discord.SelectOption(label="Ban (Bannir)", value="ban", emoji="🔨", default=current_action=="ban"),
            discord.SelectOption(label="Delete (Supprimer uniquement)", value="delete", emoji="🗑️", default=current_action=="delete"),
        ]
        super().__init__(placeholder="Action en cas d'infraction...", options=options, row=3)

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        action = self.values[0]
        await interaction.client.db.update_automod_setting(interaction.guild.id, f"{self.module}_action", action)
        await view.refresh(interaction, "Action mise à jour !")

class AutomodThresholdModal(discord.ui.Modal):
    threshold = discord.ui.TextInput(label="Limite", style=discord.TextStyle.short)

    def __init__(self, setup_view: "SetupView", module: str, current: int):
        super().__init__(title=f"Seuil pour {module.capitalize()}")
        self._setup_view = setup_view
        self.module = module
        self.threshold.default = str(current)
        if module == "caps":
            self.threshold.label = "Pourcentage max de majuscules (ex: 70)"
        else:
            self.threshold.label = "Nombre max par message/fenêtre"

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.threshold.value.strip())
            await interaction.client.db.update_automod_setting(interaction.guild.id, f"{self.module}_threshold", val)
            await self._setup_view.refresh(interaction, "Seuil mis à jour !")
        except ValueError:
            await interaction.response.send_message("Valeur invalide.", ephemeral=True)

class AutomodThresholdButton(discord.ui.Button):
    def __init__(self, module: str, current: int):
        super().__init__(label=f"Seuil actuel : {current}", style=discord.ButtonStyle.secondary, row=4)
        self.module = module
        self.current = current

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        await interaction.response.send_modal(AutomodThresholdModal(view, self.module, self.current))

class AntiraidToggleButton(discord.ui.Button):
    def __init__(self, current: bool):
        super().__init__(label="Désactiver Anti-Raid" if current else "Activer Anti-Raid", style=discord.ButtonStyle.danger if current else discord.ButtonStyle.success, row=1)
        self.current = current
    
    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        new_val = 0 if self.current else 1
        await interaction.client.db.update_antiraid_setting(interaction.guild.id, "enabled", new_val)
        await view.refresh(interaction, "Anti-Raid a été " + ("désactivé" if self.current else "activé"))

class AntiraidActionSelect(discord.ui.Select):
    def __init__(self, current_action: str):
        options = [
            discord.SelectOption(label="Kick (Expulser)", value="kick", emoji="👢", default=current_action=="kick"),
            discord.SelectOption(label="Ban (Bannir)", value="ban", emoji="🔨", default=current_action=="ban"),
            discord.SelectOption(label="Warn (Avertissement)", value="warn", emoji="⚠️", default=current_action=="warn"),
        ]
        super().__init__(placeholder="Action lors d'un raid...", options=options, row=2)

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        await interaction.client.db.update_antiraid_setting(interaction.guild.id, "action", self.values[0])
        await view.refresh(interaction, "Action Anti-Raid mise à jour !")

class AntiraidThresholdModal(discord.ui.Modal, title="Filtre Anti-Raid"):
    joins = discord.ui.TextInput(label="Membres max", style=discord.TextStyle.short)
    window = discord.ui.TextInput(label="En combien de secondes ?", style=discord.TextStyle.short)

    def __init__(self, setup_view: "SetupView", current_joins: int, current_window: int):
        super().__init__()
        self._setup_view = setup_view
        self.joins.default = str(current_joins)
        self.window.default = str(current_window)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            j = int(self.joins.value.strip())
            w = int(self.window.value.strip())
            await interaction.client.db.update_antiraid_setting(interaction.guild.id, "join_threshold", j)
            await interaction.client.db.update_antiraid_setting(interaction.guild.id, "join_window", w)
            await self._setup_view.refresh(interaction, "Filtre Anti-Raid mis à jour !")
        except ValueError:
            await interaction.response.send_message("Valeurs invalides.", ephemeral=True)

class AntiraidThresholdButton(discord.ui.Button):
    def __init__(self, joins: int, window: int):
        super().__init__(label=f"Filtre : {joins} joins / {window}s", style=discord.ButtonStyle.secondary, row=3)
        self.joins = joins
        self.window = window

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        await interaction.response.send_modal(AntiraidThresholdModal(view, self.joins, self.window))

class AntiraidAgeModal(discord.ui.Modal, title="Âge minimum du compte"):
    age = discord.ui.TextInput(label="Jours minimum (0 pour désactiver)", style=discord.TextStyle.short)

    def __init__(self, setup_view: "SetupView", current: int):
        super().__init__()
        self._setup_view = setup_view
        self.age.default = str(current)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.age.value.strip())
            await interaction.client.db.update_antiraid_setting(interaction.guild.id, "min_account_age", val)
            await self._setup_view.refresh(interaction, "Âge minimum mis à jour !")
        except ValueError:
            await interaction.response.send_message("Valeur invalide.", ephemeral=True)

class AntiraidAgeButton(discord.ui.Button):
    def __init__(self, age: int):
        super().__init__(label=f"Âge min : {age} jours" if age > 0 else "Âge min : Désactivé", style=discord.ButtonStyle.secondary, row=3)
        self.age = age

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        await interaction.response.send_modal(AntiraidAgeModal(view, self.age))

class SetupBackButton(discord.ui.Button):
    def __init__(self, lang: str):
        super().__init__(label=t(lang, "setup.back_btn"), style=discord.ButtonStyle.danger, row=4)

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        await view.show_home(interaction)


class SetupView(discord.ui.LayoutView):
    def __init__(self, bot, lang: str, guild_id: int):
        super().__init__(timeout=300)
        self.bot = bot
        self.lang = lang
        self.guild_id = guild_id
        self.automod_module = None

    async def init_home(self, guild: discord.Guild):
        await self._build_home(guild)

    async def _build_home(self, guild: discord.Guild, confirm_text: str = None):
        self.clear_items()
        settings = await self.bot.db.get_guild_settings(self.guild_id)
        am_cfg = await self.bot.db.get_automod_config(self.guild_id)
        ar_cfg = await self.bot.db.get_antiraid_config(self.guild_id)

        def ch(cid):
            if not cid: return "Non défini"
            c = guild.get_channel(cid)
            return c.mention if c else "Introuvable"

        def role(rid):
            if not rid: return "Non défini"
            r = guild.get_role(rid)
            return r.mention if r else "Introuvable"

        cont = discord.ui.Container(accent_color=Colors.INFO.value)

        header = f"# Configuration de {guild.name}\nSélectionnez une catégorie ci-dessous pour configurer les fonctionnalités du bot.\n\n"
        if confirm_text:
            header = f"✅ **{confirm_text}**\n\n" + header
        cont.add_item(discord.ui.TextDisplay(header))

        am_status = am_cfg.get("enabled")
        btn_am = discord.ui.Button(label="Activé" if am_status else "Désactivé", style=discord.ButtonStyle.success if am_status else discord.ButtonStyle.secondary, disabled=True)
        cont.add_item(discord.ui.Section(discord.ui.TextDisplay("🛡️ **AutoMod**\nModération automatique et protection contre les liens/spams."), accessory=btn_am))

        ar_status = ar_cfg.get("enabled")
        btn_ar = discord.ui.Button(label="Activé" if ar_status else "Désactivé", style=discord.ButtonStyle.success if ar_status else discord.ButtonStyle.secondary, disabled=True)
        cont.add_item(discord.ui.Section(discord.ui.TextDisplay("⚔️ **Anti-Raid**\nProtection contre les raids de bots et les arrivées massives."), accessory=btn_ar))

        desc = (
            "\n\n"
            f"🪵 `Logs :` {ch(settings.get('log_channel_id'))}\n"
            f"👋 `Bienvenue :` {ch(settings.get('welcome_channel_id'))}\n"
            f"👋 `Départ :` {ch(settings.get('goodbye_channel_id'))}\n"
            f"🔰 `Auto-Rôle :` {role(settings.get('autorole_id'))}\n"
        )
        cont.add_item(discord.ui.TextDisplay(desc))

        cont.add_item(discord.ui.ActionRow(SetupCategorySelect(self.lang)))
        self.add_item(cont)

    async def show_home(self, interaction: discord.Interaction):
        await self._build_home(interaction.guild)
        await interaction.response.edit_message(view=self, embed=None)

    async def show_category(self, interaction: discord.Interaction, category: str):
        settings = await self.bot.db.get_guild_settings(self.guild_id)
        lang = self.lang
        self.clear_items()
        
        cont = discord.ui.Container(accent_color=Colors.INFO.value)
        title = t(lang, f"setup.opt_{category}") if category not in ["automod", "antiraid"] else ("🛡️ Configuration AutoMod" if category == "automod" else "⚔️ Configuration Anti-Raid")
        desc = t(lang, f"setup.{category}_desc") if category not in ["automod", "antiraid"] else ("Activez ou désactivez l'AutoMod global.\nChoisissez un sous-module pour affiner la configuration." if category == "automod" else "Configurez les seuils et actions du système Anti-Raid.")
        
        cont.add_item(discord.ui.TextDisplay(f"# {title}\n{desc}\n\n"))

        if category == "logs":
            cont.add_item(discord.ui.TextDisplay("🪵 **Salon des Logs**\nDéfinit le salon où seront envoyés les journaux d'audit du serveur."))
            cont.add_item(discord.ui.ActionRow(SetupChannelSelect(lang, "log_channel_id", "setup.logs_placeholder")))
            
        elif category == "welcome":
            cont.add_item(discord.ui.TextDisplay("👋 **Salon de Bienvenue**\nDéfinit le salon où envoyer les messages d'arrivée."))
            cont.add_item(discord.ui.ActionRow(SetupChannelSelect(lang, "welcome_channel_id", "setup.welcome_placeholder")))
            cont.add_item(discord.ui.ActionRow(
                SetupMessageButton(lang, "welcome_message", t(lang, "setup.welcome_modal_title"), settings.get("welcome_message")),
                SetupImageButton(lang, "welcome_image", "Bannière de Bienvenue", settings.get("welcome_image"))
            ))
            
        elif category == "goodbye":
            cont.add_item(discord.ui.TextDisplay("👋 **Salon de Départ**\nDéfinit le salon où envoyer les messages de départ."))
            cont.add_item(discord.ui.ActionRow(SetupChannelSelect(lang, "goodbye_channel_id", "setup.goodbye_placeholder")))
            cont.add_item(discord.ui.ActionRow(
                SetupMessageButton(lang, "goodbye_message", t(lang, "setup.goodbye_modal_title"), settings.get("goodbye_message")),
                SetupImageButton(lang, "goodbye_image", "Bannière d'Au revoir", settings.get("goodbye_image"))
            ))
            
        elif category == "autorole":
            cont.add_item(discord.ui.TextDisplay("🔰 **Auto-Rôle**\nRôle donné automatiquement aux nouveaux membres."))
            cont.add_item(discord.ui.ActionRow(SetupRoleSelect(lang)))
            
        elif category == "report":
            cont.add_item(discord.ui.TextDisplay("🚨 **Salon des Signalements**\nReçoit les signalements effectués par les membres."))
            cont.add_item(discord.ui.ActionRow(SetupChannelSelect(lang, "report_channel_id", "setup.report_placeholder")))
            
        elif category == "language":
            cont.add_item(discord.ui.TextDisplay("🌐 **Langue du bot**\nDéfinit la langue utilisée par le bot sur ce serveur."))
            cont.add_item(discord.ui.ActionRow(SetupLanguageSelect(lang)))
            
        elif category == "automod":
            am_cfg = await self.bot.db.get_automod_config(self.guild_id)
            btn_am = AutomodToggleButton(bool(am_cfg["enabled"]))
            cont.add_item(discord.ui.Section(discord.ui.TextDisplay("Système Global AutoMod"), accessory=btn_am))
            
            if self.automod_module:
                mod = self.automod_module
                is_enabled = bool(am_cfg[f"{mod}_enabled"])
                action = am_cfg[f"{mod}_action"]
                threshold = am_cfg.get(f"{mod}_threshold", 0)
                
                cont.add_item(discord.ui.TextDisplay(f"\n\n### Module : {mod.capitalize()}\nConfiguration spécifique de ce sous-module."))
                sec_tog = discord.ui.Section(discord.ui.TextDisplay(f"**État du module {mod}**"), accessory=AutomodModuleToggleButton(mod, is_enabled))
                cont.add_item(sec_tog)
                
                if mod not in ["link", "invite"]:
                    sec_thresh = discord.ui.Section(discord.ui.TextDisplay("**Seuil de tolérance**"), accessory=AutomodThresholdButton(mod, threshold))
                    cont.add_item(sec_thresh)
            
            cont.add_item(discord.ui.ActionRow(AutomodModuleSelect(self.automod_module)))
            if self.automod_module:
                cont.add_item(discord.ui.ActionRow(AutomodActionSelect(self.automod_module, action if self.automod_module else "warn")))
                
        elif category == "antiraid":
            ar_cfg = await self.bot.db.get_antiraid_config(self.guild_id)
            cont.add_item(discord.ui.Section(discord.ui.TextDisplay("**État du système Anti-Raid**"), accessory=AntiraidToggleButton(bool(ar_cfg["enabled"]))))
            cont.add_item(discord.ui.Section(discord.ui.TextDisplay("**Seuil de détection (Joins / Secondes)**"), accessory=AntiraidThresholdButton(ar_cfg["join_threshold"], ar_cfg["join_window"])))
            cont.add_item(discord.ui.Section(discord.ui.TextDisplay("**Âge minimum du compte (Jours)**"), accessory=AntiraidAgeButton(ar_cfg["min_account_age"])))
            cont.add_item(discord.ui.ActionRow(AntiraidActionSelect(ar_cfg["action"])))

        cont.add_item(discord.ui.ActionRow(SetupCategorySelect(lang)))
        cont.add_item(discord.ui.ActionRow(SetupBackButton(lang)))
        self.add_item(cont)
        
        try:
            await interaction.response.edit_message(view=self, embed=None)
        except Exception as e:
            import logging
            logging.error(f"Error in show_category for {category}: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Erreur interne : {e}", ephemeral=True)

    async def refresh(self, interaction: discord.Interaction, confirm_text: str):
        await self._build_home(interaction.guild, confirm_text)
        await interaction.response.edit_message(view=self, embed=None)

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
        await view.init_home(interaction.guild)
        await interaction.response.send_message(view=view, ephemeral=True)

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
