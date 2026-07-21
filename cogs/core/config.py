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
            discord.SelectOption(label=t(lang, "setup.opt_autorole"), value="autorole", emoji="🎭"),
            discord.SelectOption(label=t(lang, "setup.opt_report"),   value="report",   emoji="🚨"),
            discord.SelectOption(label=t(lang, "setup.opt_language"), value="language", emoji="🌐"),
            discord.SelectOption(label="Système XP",                  value="xp",       emoji="✨"),
            discord.SelectOption(label="AutoMod",                     value="automod",  emoji="🛡️"),
            discord.SelectOption(label="Anti-Raid",                   value="antiraid", emoji="⚔️"),
            discord.SelectOption(label="Statistiques",                value="stats",    emoji="📊"),
            discord.SelectOption(label="TempVoice", value="tempvoice", emoji="🔊"),
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
        
        # Safeguard if top_role is None for some reason
        me = interaction.guild.me if interaction.guild else None
        if me and me.top_role and role >= me.top_role:
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



class SetupColorModal(discord.ui.Modal):
    color_hex = discord.ui.TextInput(label="Couleur de l'embed (Hex: #FFFFFF)", style=discord.TextStyle.short, required=False, max_length=7, placeholder="#5865F2")

    def __init__(self, setup_view: "SetupView", setting_key: str, title: str, current: str = None):
        super().__init__(title=title)
        self._setup_view = setup_view
        self.setting_key = setting_key
        if current:
            self.color_hex.default = current

    async def on_submit(self, interaction: discord.Interaction):
        value = self.color_hex.value.strip() or None
        if value and not value.startswith("#"):
            value = "#" + value
        if value:
            await interaction.client.db.update_guild_setting(interaction.guild.id, self.setting_key, value)
        await self._setup_view.refresh(interaction, "La couleur a bien été sauvegardée ! 🎨")


class SetupColorButton(discord.ui.Button):
    def __init__(self, lang: str, setting_key: str, modal_title: str, current: str = None):
        super().__init__(label="🎨 Couleur", style=discord.ButtonStyle.secondary, row=2)
        self.setting_key = setting_key
        self.modal_title = modal_title
        self.current = current

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        await interaction.response.send_modal(SetupColorModal(view, self.setting_key, self.modal_title, self.current))


class StatsToggleButton(discord.ui.Button):
    def __init__(self, current: bool):
        super().__init__(label="Désactiver les stats" if current else "Générer les salons de stats", style=discord.ButtonStyle.danger if current else discord.ButtonStyle.success, row=1)
        self.current = current
    
    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        stats_cog = interaction.client.get_cog("Stats")
        if self.current:
            # Desactiver
            await interaction.client.db.delete_stats_channels(interaction.guild.id)
            await view.refresh(interaction, "Salons de statistiques désactivés (vous pouvez les supprimer manuellement).")
        else:
            # Generer
            if stats_cog:
                try:
                    await stats_cog.create_stats_channels(interaction.guild)
                    await view.refresh(interaction, "Les salons de statistiques ont été créés !")
                except Exception as e:
                    await interaction.response.send_message(f"❌ Erreur lors de la création : {e}", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Le module de statistiques n'est pas chargé.", ephemeral=True)


class SetupTVChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, placeholder: str, is_category: bool = False):
        types = [discord.ChannelType.category] if is_category else [discord.ChannelType.voice]
        super().__init__(placeholder=placeholder, channel_types=types, row=1 if not is_category else 2)
        self.is_category = is_category

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        channel = self.values[0]
        if self.is_category:
            await interaction.client.db.update_tempvoice_config(interaction.guild.id, "category_id", channel.id)
            msg = f"Catégorie définie sur {channel.mention}"
        else:
            await interaction.client.db.update_tempvoice_config(interaction.guild.id, "trigger_channel_id", channel.id)
            msg = f"Salon déclencheur défini sur {channel.mention}"
        await view.refresh(interaction, msg)

class SetupTVModal(discord.ui.Modal, title="Configuration TempVoice"):
    name_format = discord.ui.TextInput(label="Format du nom ({user} = pseudo)", max_length=50, placeholder="✨ | Salon de {user}")
    default_limit = discord.ui.TextInput(label="Limite par défaut (0 = infini)", max_length=2, placeholder="0")

    def __init__(self, view, current_format, current_limit):
        super().__init__()
        self.setup_view = view
        if current_format: self.name_format.default = current_format
        if current_limit is not None: self.default_limit.default = str(current_limit)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.client.db.update_tempvoice_config(interaction.guild.id, "name_format", self.name_format.value or "✨ | Salon de {user}")
        try:
            limit = int(self.default_limit.value or "0")
            await interaction.client.db.update_tempvoice_config(interaction.guild.id, "default_limit", limit)
        except ValueError:
            pass
        await self.setup_view.refresh(interaction, "Configuration sauvegardée !")

class SetupTVButton(discord.ui.Button):
    def __init__(self, config):
        super().__init__(label="Paramètres (Nom & Limite)", style=discord.ButtonStyle.secondary, row=3, emoji="⚙️")
        self.config = config

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        await interaction.response.send_modal(SetupTVModal(view, self.config.get("name_format"), self.config.get("default_limit")))

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

class AntiNukeToggleButton(discord.ui.Button):
    def __init__(self, current: bool):
        super().__init__(label=f"{'Désactiver' if current else 'Activer'} Anti-Nuke", style=discord.ButtonStyle.danger if current else discord.ButtonStyle.success, row=4)
        self.current = current

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        new_val = 0 if self.current else 1
        await interaction.client.db.update_antinuke_setting(interaction.guild.id, "enabled", new_val)
        await view.refresh(interaction, "Anti-Nuke mis à jour !")

class AntiNukeActionSelect(discord.ui.Select):
    def __init__(self, current_action: str):
        options = [
            discord.SelectOption(label="Quarantaine (Retrait des rôles)", value="quarantine", emoji="🛡️", default=current_action=="quarantine"),
            discord.SelectOption(label="Bannissement (Ban)", value="ban", emoji="🔨", default=current_action=="ban"),
            discord.SelectOption(label="Expulsion (Kick)", value="kick", emoji="👢", default=current_action=="kick"),
        ]
        super().__init__(placeholder="Sanction en cas de détection...", options=options, row=2)

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        await interaction.client.db.update_antinuke_setting(interaction.guild.id, "action", self.values[0])
        await view.refresh(interaction, "Sanction Anti-Nuke mise à jour !")

class AntiNukeThresholdsModal(discord.ui.Modal, title="Seuils Anti-Nuke (/minute)"):
    ban_thresh = discord.ui.TextInput(label="Bannissements", style=discord.TextStyle.short)
    kick_thresh = discord.ui.TextInput(label="Expulsions", style=discord.TextStyle.short)
    ch_del_thresh = discord.ui.TextInput(label="Suppressions de salons", style=discord.TextStyle.short)
    role_del_thresh = discord.ui.TextInput(label="Suppressions de rôles", style=discord.TextStyle.short)

    def __init__(self, setup_view: "SetupView", config: dict):
        super().__init__()
        self._setup_view = setup_view
        self.ban_thresh.default = str(config.get("ban_threshold", 3))
        self.kick_thresh.default = str(config.get("kick_threshold", 3))
        self.ch_del_thresh.default = str(config.get("channel_delete_threshold", 2))
        self.role_del_thresh.default = str(config.get("role_delete_threshold", 2))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            db = interaction.client.db
            gid = interaction.guild.id
            await db.update_antinuke_setting(gid, "ban_threshold", int(self.ban_thresh.value.strip()))
            await db.update_antinuke_setting(gid, "kick_threshold", int(self.kick_thresh.value.strip()))
            await db.update_antinuke_setting(gid, "channel_delete_threshold", int(self.ch_del_thresh.value.strip()))
            await db.update_antinuke_setting(gid, "role_delete_threshold", int(self.role_del_thresh.value.strip()))
            await self._setup_view.refresh(interaction, "Seuils Anti-Nuke mis à jour !")
        except ValueError:
            await interaction.response.send_message("Valeurs invalides. Veuillez entrer des nombres entiers.", ephemeral=True)

class AntiNukeAlertChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="Sélectionner le salon d'alerte Anti-Nuke...", channel_types=[discord.ChannelType.text], row=3)

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        await interaction.client.db.update_antinuke_setting(interaction.guild.id, "alert_channel_id", self.values[0].id)
        await view.refresh(interaction, "Salon d'alerte mis à jour !")

class SetupBackButton(discord.ui.Button):
    def __init__(self, lang: str):
        super().__init__(label=t(lang, "setup.back_btn"), style=discord.ButtonStyle.danger, row=4)

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        await view.show_home(interaction)


class SetupLogsCategorySelect(discord.ui.ChannelSelect):
    def __init__(self, lang: str):
        super().__init__(placeholder="Choisissez une catégorie pour les logs...", channel_types=[discord.ChannelType.category])
        self.lang = lang

    async def callback(self, interaction: discord.Interaction):
        category_id = self.values[0].id
        category = interaction.guild.get_channel(category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message("❌ Catégorie introuvable.", ephemeral=True)
            return

        db = interaction.client.db
        guild_id = interaction.guild.id
        
        await interaction.response.defer(ephemeral=True)
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        
        async def get_or_create(name):
            for ch in category.channels:
                if ch.name == name:
                    return ch
            return await category.create_text_channel(name=name, overwrites=overwrites)
            
        try:
            ch_msg = await get_or_create("logs-messages")
            ch_voc = await get_or_create("logs-vocaux")
            ch_mod = await get_or_create("logs-modération")
            ch_srv = await get_or_create("logs-serveur")
        except discord.Forbidden:
            return await interaction.followup.send("❌ Je n'ai pas la permission de créer des salons dans cette catégorie.", ephemeral=True)
            
        await db.update_guild_setting(guild_id, "log_category_id", category.id)
        await db.update_guild_setting(guild_id, "log_messages_id", ch_msg.id)
        await db.update_guild_setting(guild_id, "log_voice_id", ch_voc.id)
        await db.update_guild_setting(guild_id, "log_mod_id", ch_mod.id)
        await db.update_guild_setting(guild_id, "log_server_id", ch_srv.id)
        
        view = self.view
        await view._build_home(interaction.guild, "Catégorie de logs configurée et salons créés !")
        await interaction.edit_original_response(view=view, embed=None)

class SetupView(discord.ui.LayoutView):
    def __init__(self, bot, lang: str, guild_id: int):
        super().__init__(timeout=300)
        self.bot = bot
        self.lang = lang
        self.guild_id = guild_id
        self.automod_module = None
        self.current_category = None

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

        header = f"# ⚙️ Configuration de {guild.name}\n> Gérez les paramètres globaux de votre serveur.\n"
        if confirm_text:
            header = f"✅ **{confirm_text}**\n\n" + header
        cont.add_item(discord.ui.TextDisplay(header))
        cont.add_item(discord.ui.Separator())

        def make_nav(cat: str):
            async def nav_cb(inter: discord.Interaction):
                await self.show_category(inter, cat)
            return nav_cb

        # AutoMod
        am_status = am_cfg.get("enabled")
        btn_am = discord.ui.Button(label="Configurer", style=discord.ButtonStyle.success if am_status else discord.ButtonStyle.secondary)
        btn_am.callback = make_nav("automod")
        cont.add_item(discord.ui.Section(discord.ui.TextDisplay(f"🛡️ **AutoMod**\n> **État :** {'✅ Activé' if am_status else '❌ Désactivé'}\n> Protection automatique contre le spam, les liens et le flood."), accessory=btn_am))

        # Anti-Raid
        ar_status = ar_cfg.get("enabled")
        btn_ar = discord.ui.Button(label="Configurer", style=discord.ButtonStyle.success if ar_status else discord.ButtonStyle.secondary)
        btn_ar.callback = make_nav("antiraid")
        cont.add_item(discord.ui.Section(discord.ui.TextDisplay(f"⚔️ **Anti-Raid**\n> **État :** {'✅ Activé' if ar_status else '❌ Désactivé'}\n> Protection contre les attaques de bots et raids de masse."), accessory=btn_ar))

        # Anti-Nuke
        an_cfg = await self.bot.db.get_antinuke_config(self.guild_id)
        an_status = an_cfg.get("enabled")
        btn_an = discord.ui.Button(label="Configurer", style=discord.ButtonStyle.success if an_status else discord.ButtonStyle.secondary)
        btn_an.callback = make_nav("antinuke")
        cont.add_item(discord.ui.Section(discord.ui.TextDisplay(f"☢️ **Anti-Nuke**\n> **État :** {'✅ Activé' if an_status else '❌ Désactivé'}\n> Limite les actions destructrices de masse (ban, suppression de salons/rôles)."), accessory=btn_an))

        # Logs
        btn_logs = discord.ui.Button(label="Configurer", style=discord.ButtonStyle.secondary)
        btn_logs.callback = make_nav("logs")
        cont.add_item(discord.ui.Section(discord.ui.TextDisplay(f"🪵 **Logs**\n> **Catégorie actuelle :** {ch(settings.get('log_category_id'))}\n> Traçage complet des actions sur le serveur."), accessory=btn_logs))

        # Bienvenue
        btn_welc = discord.ui.Button(label="Configurer", style=discord.ButtonStyle.secondary)
        btn_welc.callback = make_nav("welcome")
        cont.add_item(discord.ui.Section(discord.ui.TextDisplay(f"👋 **Accueil**\n> **Salon actuel :** {ch(settings.get('welcome_channel_id'))}\n> Accueillez les nouveaux membres avec style."), accessory=btn_welc))

        # Auto-Rôle
        btn_auto = discord.ui.Button(label="Configurer", style=discord.ButtonStyle.secondary)
        btn_auto.callback = make_nav("autorole")
        cont.add_item(discord.ui.Section(discord.ui.TextDisplay(f"🎭 **Auto-Rôle**\n> **Rôle actuel :** {role(settings.get('autorole_id'))}\n> Rôle attribué automatiquement aux nouveaux membres."), accessory=btn_auto))

        # Signalement
        btn_rep = discord.ui.Button(label="Configurer", style=discord.ButtonStyle.secondary)
        btn_rep.callback = make_nav("report")
        cont.add_item(discord.ui.Section(discord.ui.TextDisplay(f"🚨 **Signalement**\n> Configuration des signalements de messages au Staff."), accessory=btn_rep))

        # Langue
        btn_lang = discord.ui.Button(label="Configurer", style=discord.ButtonStyle.secondary)
        btn_lang.callback = make_nav("language")
        cont.add_item(discord.ui.Section(discord.ui.TextDisplay(f"🌐 **Langue**\n> **Actuelle :** `{self.lang.upper()}`\n> Définissez la langue du bot pour le serveur."), accessory=btn_lang))

        # XP
        btn_xp = discord.ui.Button(label="Configurer", style=discord.ButtonStyle.secondary)
        btn_xp.callback = make_nav("xp")
        cont.add_item(discord.ui.Section(discord.ui.TextDisplay(f"✨ **Système XP**\n> **Salon Level Up :** {ch(settings.get('levelup_channel_id'))}\n> Gérer l'évolution des niveaux des membres."), accessory=btn_xp))

        # Statistiques
        stats_cfg = await self.bot.db.get_stats_channels(self.guild_id)
        stats_status = bool(stats_cfg)
        btn_stats = discord.ui.Button(label="Configurer", style=discord.ButtonStyle.success if stats_status else discord.ButtonStyle.secondary)
        btn_stats.callback = make_nav("stats")
        cont.add_item(discord.ui.Section(discord.ui.TextDisplay(f"📊 **Statistiques**\n> **État :** {'✅ Activé' if stats_status else '❌ Désactivé'}\n> Salons vocaux affichant les membres/bots en direct."), accessory=btn_stats))

        # TempVoice
        tv_cfg = await self.bot.db.get_tempvoice_config(self.guild_id)
        tv_status = bool(tv_cfg.get("trigger_channel_id"))
        btn_tv = discord.ui.Button(label="Configurer", style=discord.ButtonStyle.success if tv_status else discord.ButtonStyle.secondary)
        btn_tv.callback = make_nav("tempvoice")
        cont.add_item(discord.ui.Section(discord.ui.TextDisplay(f"🔊 **TempVoice**\n> **État :** {'✅ Configurés' if tv_status else '❌ Non configurés'}\n> Salons vocaux temporaires personnels."), accessory=btn_tv))
        
        self.add_item(cont)

    async def show_home(self, interaction: discord.Interaction):
        self.current_category = None
        await self._build_home(interaction.guild)
        await interaction.response.edit_message(view=self, embed=None)

    async def show_category(self, interaction: discord.Interaction, category: str, confirm_text: str = None):
        self.current_category = category
        settings = await self.bot.db.get_guild_settings(self.guild_id)
        lang = self.lang
        self.clear_items()
        
        cont = discord.ui.Container(accent_color=Colors.INFO.value)
        title = t(lang, f"setup.opt_{category}") if category not in ["automod", "antiraid"] else ("🛡️ Configuration AutoMod" if category == "automod" else "⚔️ Configuration Anti-Raid")
        desc = t(lang, f"setup.{category}_desc") if category not in ["automod", "antiraid"] else ("Activez ou désactivez l'AutoMod global.\nChoisissez un sous-module pour affiner la configuration." if category == "automod" else "Configurez les seuils et actions du système Anti-Raid.")
        
        header_text = f"# {title}\n{desc}\n\n"
        if confirm_text:
            header_text = f"✅ **{confirm_text}**\n\n" + header_text
        
        cont.add_item(discord.ui.TextDisplay(header_text))

        if category == "logs":
            cont.add_item(discord.ui.TextDisplay("🪵 **Catégorie des Logs**\n> Définit la catégorie Discord où le bot créera automatiquement les salons de logs avancés (messages, vocal, modération, serveur)."))
            cont.add_item(discord.ui.ActionRow(SetupLogsCategorySelect(lang)))
            
        elif category == "welcome":
            cont.add_item(discord.ui.TextDisplay("👋 **Salon de Bienvenue**\n> Définit le salon où envoyer les messages d'arrivée."))
            cont.add_item(discord.ui.ActionRow(SetupChannelSelect(lang, "welcome_channel_id", "setup.welcome_placeholder")))
            cont.add_item(discord.ui.ActionRow(
                SetupMessageButton(lang, "welcome_message", t(lang, "setup.welcome_modal_title"), settings.get("welcome_message")),
                SetupImageButton(lang, "welcome_image", "Bannière", settings.get("welcome_image")),
                SetupColorButton(lang, "welcome_color", "Couleur Bienvenue", settings.get("welcome_color"))
            ))
            

        elif category == "autorole":
            cont.add_item(discord.ui.TextDisplay("🎭 **Auto-Rôle**\n> Rôle donné automatiquement aux nouveaux membres."))
            cont.add_item(discord.ui.ActionRow(SetupRoleSelect(lang)))
            
        elif category == "report":
            cont.add_item(discord.ui.TextDisplay("🚨 **Salon des Signalements**\n> Reçoit les signalements effectués par les membres."))
            cont.add_item(discord.ui.ActionRow(SetupChannelSelect(lang, "report_channel_id", "setup.report_placeholder")))
            
        elif category == "language":
            cont.add_item(discord.ui.TextDisplay("🌐 **Langue du bot**\n> Définit la langue utilisée par le bot sur ce serveur."))
            cont.add_item(discord.ui.ActionRow(SetupLanguageSelect(lang)))
            
        elif category == "xp":
            cont.add_item(discord.ui.TextDisplay("✨ **Système XP & Rank**\n> Définit le salon où envoyer les annonces de Level Up."))
            cont.add_item(discord.ui.ActionRow(SetupChannelSelect(lang, "levelup_channel_id", "Sélectionner un salon pour le Level Up")))
            

        elif category == "stats":
            stats_channels = await self.bot.db.get_stats_channels(self.guild_id)
            btn = StatsToggleButton(bool(stats_channels))
            cont.add_item(discord.ui.Section(discord.ui.TextDisplay("📊 **Salons de Statistiques**\n> Crée automatiquement des salons vocaux verrouillés affichant le nombre de membres, de connectés et de bots.\n> Les salons sont mis à jour toutes les 10 minutes."), accessory=btn))
            

        elif category == "tempvoice":
            tv_config = await self.bot.db.get_tempvoice_config(self.guild_id)
            cont.add_item(discord.ui.TextDisplay("🔊 **Salons Vocaux Temporaires**\n> Permet aux membres de créer leurs propres salons vocaux en rejoignant un salon défini."))
            cont.add_item(discord.ui.ActionRow(SetupTVChannelSelect("Sélectionner le salon déclencheur (Vocal)", is_category=False)))
            cont.add_item(discord.ui.ActionRow(SetupTVChannelSelect("Sélectionner la catégorie d'accueil", is_category=True)))
            cont.add_item(discord.ui.ActionRow(SetupTVButton(tv_config)))
            
        elif category == "automod":
            am_cfg = await self.bot.db.get_automod_config(self.guild_id)
            btn_am = AutomodToggleButton(bool(am_cfg["enabled"]))
            cont.add_item(discord.ui.Section(discord.ui.TextDisplay("🛡️ **Système Global AutoMod**\n> Activez ou désactivez l'AutoMod sur tout le serveur."), accessory=btn_am))
            
            if self.automod_module:
                mod = self.automod_module
                is_enabled = bool(am_cfg[f"{mod}_enabled"])
                action = am_cfg[f"{mod}_action"]
                threshold = am_cfg.get(f"{mod}_threshold", 0)
                
                cont.add_item(discord.ui.TextDisplay(f"\n\n### ⚙️ Module : {mod.capitalize()}\n> Configuration spécifique de ce sous-module."))
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
            cont.add_item(discord.ui.Section(discord.ui.TextDisplay("**Seuil de détection**\n> Ratio : Joins / Secondes"), accessory=AntiraidThresholdButton(ar_cfg["join_threshold"], ar_cfg["join_window"])))
            cont.add_item(discord.ui.Section(discord.ui.TextDisplay("**Âge minimum du compte**\n> En jours."), accessory=AntiraidAgeButton(ar_cfg["min_account_age"])))
            cont.add_item(discord.ui.ActionRow(AntiraidActionSelect(ar_cfg["action"])))

        elif category == "antinuke":
            an_cfg = await self.bot.db.get_antinuke_config(self.guild_id)
            cont.add_item(discord.ui.Section(discord.ui.TextDisplay("**État du système Anti-Nuke**"), accessory=AntiNukeToggleButton(bool(an_cfg["enabled"]))))
            
            btn_thresh = discord.ui.Button(label="Configurer les seuils", style=discord.ButtonStyle.secondary, emoji="⚙️")
            async def open_thresh_modal(inter: discord.Interaction):
                await inter.response.send_modal(AntiNukeThresholdsModal(self, an_cfg))
            btn_thresh.callback = open_thresh_modal
            cont.add_item(discord.ui.Section(discord.ui.TextDisplay("**Seuils de tolérance**\n> Nombre maximum d'actions par minute."), accessory=btn_thresh))
            
            cont.add_item(discord.ui.ActionRow(AntiNukeActionSelect(an_cfg["action"])))
            cont.add_item(discord.ui.ActionRow(AntiNukeAlertChannelSelect()))

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
        if self.current_category:
            await self.show_category(interaction, self.current_category, confirm_text)
        else:
            await self._build_home(interaction.guild, confirm_text)
            await interaction.response.edit_message(view=self, embed=None)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

class Config(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /config ───────────────────────────────────────────────────────────────

    @app_commands.command(name="config", description="Affiche la configuration actuelle du bot")
    @app_commands.default_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction):
        lang  = await self.bot.db.get_guild_lang(interaction.guild_id)
        view  = SetupView(self.bot, lang, interaction.guild.id)
        await view.init_home(interaction.guild)
        await interaction.response.send_message(view=view, ephemeral=True)

    # (Standalone config commands removed in favor of /setup)

async def setup(bot: commands.Bot):
    await bot.add_cog(Config(bot))
