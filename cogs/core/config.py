import discord
from discord import app_commands
from discord.ext import commands
from utils.i18n import t, SUPPORTED
from utils.colors import Colors
from utils.embeds import error_embed, success_embed
from utils.media import resolve_media_url


def get_logs(bot: commands.Bot):
    return bot.get_cog("Logs")


# ══════════════════════════════════════════════════════════════════════════════
#  /setup wizard
# ══════════════════════════════════════════════════════════════════════════════

class SetupCategorySelect(discord.ui.Select):
    def __init__(self, lang: str, current: str = None):
        options = [
            discord.SelectOption(label="Tableau de bord",         value="home",      emoji="🏠", description="Retourner à l'accueil du dashboard", default=(current == "home")),
            discord.SelectOption(label="Protection AutoMod",     value="automod",   emoji="🛡️", description="Anti-spam, anti-liens, anti-flood",  default=(current == "automod")),
            discord.SelectOption(label="Protection Anti-Raid",   value="antiraid",  emoji="⚔️", description="Blocage des vagues d'arrivées",       default=(current == "antiraid")),
            discord.SelectOption(label="Protection Anti-Nuke",   value="antinuke",  emoji="☢️", description="Protection destructions massives",    default=(current == "antinuke")),
            discord.SelectOption(label="Logs Avancés",            value="logs",      emoji="🪵", description="4 salons dédiés (messages, voc, mod)",default=(current == "logs")),
            discord.SelectOption(label="Accueil & Bienvenue",      value="welcome",   emoji="👋", description="Message, image, titre et couleur",     default=(current == "welcome")),
            discord.SelectOption(label="Auto-Rôles (Membres/Bots)",value="autorole", emoji="🎭", description="Rôles automatiques distincts",       default=(current == "autorole")),
            discord.SelectOption(label="Rôle Tag 17th",            value="tagrole",  emoji="🏷️", description="Rôle auto pour porteurs du tag",      default=(current == "tagrole")),
            discord.SelectOption(label="Signalements Staff",      value="report",    emoji="🚨", description="Salon de transmission des signalements",default=(current == "report")),
            discord.SelectOption(label="Système XP & Niveaux",    value="xp",        emoji="✨", description="Salon d'annonces de level up",         default=(current == "xp")),
            discord.SelectOption(label="Salons TempVoice",        value="tempvoice", emoji="🔊", description="Salons vocaux temporaires personnels",default=(current == "tempvoice")),
            discord.SelectOption(label="Salons Statistiques",      value="stats",     emoji="📊", description="Compteurs vocaux en direct",          default=(current == "stats")),
            discord.SelectOption(label="Auto-Réactions Photos",   value="autoreact", emoji="📸", description="Réactions automatiques aux photos",   default=(current == "autoreact")),
            discord.SelectOption(label="Langue du Bot",           value="language",  emoji="🌐", description="Français ou English",                 default=(current == "language")),
        ]
        super().__init__(placeholder="⚡ Choisissez un module à configurer...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        val = self.values[0]
        if val == "home":
            await view.show_home(interaction)
        else:
            await view.show_category(interaction, val)


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
    def __init__(self, lang: str, setting_key: str = "autorole_id", placeholder: str = None, row: int = 1):
        ph = placeholder or t(lang, "setup.autorole_placeholder")
        super().__init__(placeholder=ph, row=row)
        self.setting_key = setting_key

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        role = self.values[0]
        
        # Safeguard if top_role is None for some reason
        me = interaction.guild.me if interaction.guild else None
        if me and me.top_role and role >= me.top_role:
            return await interaction.response.send_message(embed=error_embed(t(view.lang, "cfg.autorole_too_high")), ephemeral=True)
            
        await interaction.client.db.update_guild_setting(interaction.guild.id, self.setting_key, role.id)
        if self.setting_key == "autorole_bots_id":
            await view.refresh(interaction, f"Auto-rôle des bots défini sur {role.mention} ! 🎭")
        elif self.setting_key == "tagrole_id":
            await view.refresh(interaction, f"Rôle du Tag 17th défini sur {role.mention} ! 🏷️")
        else:
            await view.refresh(interaction, f"Auto-rôle des membres défini sur {role.mention} ! 🎭")


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


class SetupTitleModal(discord.ui.Modal):
    title_text = discord.ui.TextInput(
        label="Titre de bienvenue",
        style=discord.TextStyle.short,
        required=False,
        max_length=200,
        placeholder="ex: 👋 Bienvenue sur {server} !"
    )

    def __init__(self, setup_view: "SetupView", setting_key: str, title: str, current: str = None):
        super().__init__(title=title)
        self._setup_view = setup_view
        self.setting_key = setting_key
        if current:
            self.title_text.default = current

    async def on_submit(self, interaction: discord.Interaction):
        value = self.title_text.value.strip() or None
        await interaction.client.db.update_guild_setting(interaction.guild.id, self.setting_key, value)
        await self._setup_view.refresh(interaction, "Le titre a bien été sauvegardé ! 🏷️")


class SetupTitleButton(discord.ui.Button):
    def __init__(self, lang: str, setting_key: str, modal_title: str, current: str = None):
        super().__init__(label="🏷️ Titre", style=discord.ButtonStyle.secondary, row=2)
        self.setting_key = setting_key
        self.modal_title = modal_title
        self.current = current

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        await interaction.response.send_modal(SetupTitleModal(view, self.setting_key, self.modal_title, self.current))


class SetupImageModal(discord.ui.Modal):
    image_url = discord.ui.TextInput(label="URL de l'image (PNG/GIF/Klipy/Tenor)", style=discord.TextStyle.short, required=False, max_length=500, placeholder="https://...")

    def __init__(self, setup_view: "SetupView", setting_key: str, title: str, current: str = None):
        super().__init__(title=title)
        self._setup_view = setup_view
        self.setting_key = setting_key
        if current:
            self.image_url.default = current

    async def on_submit(self, interaction: discord.Interaction):
        value = self.image_url.value.strip() or None
        if value:
            resolved = await resolve_media_url(value)
            await interaction.client.db.update_guild_setting(interaction.guild.id, self.setting_key, resolved)
        else:
            await interaction.client.db.update_guild_setting(interaction.guild.id, self.setting_key, None)
        await self._setup_view.refresh(interaction, "L'image a bien été sauvegardée ! 🖼️")


class SetupImageButton(discord.ui.Button):
    def __init__(self, lang: str, setting_key: str, modal_title: str, current: str = None):
        super().__init__(label="🖼️ Bannière / GIF", style=discord.ButtonStyle.secondary, row=2)
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


class SetupResetSettingButton(discord.ui.Button):
    def __init__(self, setting_key: str, label: str, confirm_msg: str, emoji: str = "❌", row: int = 2):
        super().__init__(label=label, emoji=emoji, style=discord.ButtonStyle.danger, row=row)
        self.setting_key = setting_key
        self.confirm_msg = confirm_msg

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        await interaction.client.db.update_guild_setting(interaction.guild.id, self.setting_key, None)
        await view.refresh(interaction, self.confirm_msg)


class SetupResetLogsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Désactiver les logs", emoji="❌", style=discord.ButtonStyle.danger, row=2)

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        db = interaction.client.db
        gid = interaction.guild.id
        await db.update_guild_setting(gid, "log_category_id", None)
        await db.update_guild_setting(gid, "log_messages_id", None)
        await db.update_guild_setting(gid, "log_voice_id", None)
        await db.update_guild_setting(gid, "log_mod_id", None)
        await db.update_guild_setting(gid, "log_server_id", None)
        await view.refresh(interaction, "Le système de logs a bien été désactivé !")


class SetupResetTVButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Désactiver TempVoice", emoji="❌", style=discord.ButtonStyle.danger, row=3)

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        db = interaction.client.db
        gid = interaction.guild.id
        await db.update_tempvoice_config(gid, "trigger_channel_id", None)
        await db.update_tempvoice_config(gid, "category_id", None)
        await view.refresh(interaction, "Le système TempVoice a bien été désactivé !")


class SetupTagTextModal(discord.ui.Modal):
    tag_input = discord.ui.TextInput(
        label="Tag à détecter",
        style=discord.TextStyle.short,
        required=True,
        max_length=30,
        placeholder="ex: 17th"
    )

    def __init__(self, setup_view: "SetupView", current: str = "17th"):
        super().__init__(title="Configuration du Tag")
        self._setup_view = setup_view
        if current:
            self.tag_input.default = current

    async def on_submit(self, interaction: discord.Interaction):
        value = self.tag_input.value.strip() or "17th"
        await interaction.client.db.update_guild_setting(interaction.guild.id, "tagrole_text", value)
        await self._setup_view.refresh(interaction, f"Tag défini sur `{value}` ! 🏷️")


class SetupTagTextButton(discord.ui.Button):
    def __init__(self, current: str = "17th"):
        super().__init__(label="Modifier le Tag", emoji="🏷️", style=discord.ButtonStyle.secondary, row=2)
        self.current = current

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        await interaction.response.send_modal(SetupTagTextModal(view, self.current))


class SetupTagScanButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Scanner les membres", emoji="🔄", style=discord.ButtonStyle.primary, row=2)

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        await interaction.response.defer()
        
        from cogs.systems.tagrole import member_has_tag
        settings = await view.bot.db.get_guild_settings(interaction.guild.id)
        role_id = settings.get("tagrole_id")
        if not role_id:
            return await view.refresh(interaction, "❌ Veuillez d'abord choisir un rôle pour le tag.")
            
        role = interaction.guild.get_role(role_id)
        if not role or interaction.guild.me.top_role <= role:
            return await view.refresh(interaction, "❌ Le rôle configuré est inaccessible ou supérieur au bot.")

        tag_text = settings.get("tagrole_text") or "17th"
        added = 0
        removed = 0
        for m in interaction.guild.members:
            if not m.bot:
                has_tag = member_has_tag(m, tag_text, interaction.guild)
                has_r = role in m.roles
                try:
                    if has_tag and not has_r:
                        await m.add_roles(role, reason=f"Tag '{tag_text}' détecté (scan)")
                        added += 1
                    elif not has_tag and has_r:
                        await m.remove_roles(role, reason=f"Tag '{tag_text}' manquant (scan)")
                        removed += 1
                except Exception:
                    pass
        await view.refresh(interaction, f"Scan terminé : +{added} rôle(s) attribué(s), -{removed} retiré(s) !")


class SetupAutoReactChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="Sélectionner un salon pour l'auto-réaction...", channel_types=[discord.ChannelType.text], row=1)

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        channel = self.values[0]
        db = interaction.client.db
        gid = interaction.guild.id
        await db.add_autoreact_channel(gid, channel.id, ["❤️"], photos_only=True)
        
        cog = interaction.client.get_cog("AutoReact")
        if cog:
            cog._cache[channel.id] = {
                "guild_id": gid,
                "channel_id": channel.id,
                "emojis": ["❤️"],
                "photos_only": 1
            }
        view.selected_autoreact_channel = channel.id
        await view.refresh(interaction, f"Salon {channel.mention} ajouté aux auto-réactions photos (réaction par défaut : ❤️) !")


class SetupAutoReactEmojisModal(discord.ui.Modal):
    emojis_input = discord.ui.TextInput(
        label="Emojis de réaction (séparés par un espace)",
        style=discord.TextStyle.short,
        required=True,
        max_length=100,
        placeholder="ex: ❤️ 🔥 ⭐"
    )

    def __init__(self, setup_view: "SetupView", channel_id: int, current: str):
        super().__init__(title="Modifier les réactions")
        self._setup_view = setup_view
        self.channel_id = channel_id
        if current:
            self.emojis_input.default = current

    async def on_submit(self, interaction: discord.Interaction):
        from cogs.systems.autoreact import parse_emojis
        emojis = parse_emojis(self.emojis_input.value.strip())
        db = interaction.client.db
        gid = interaction.guild.id
        cfg = await db.get_autoreact_channel(gid, self.channel_id)
        p_only = bool(cfg.get("photos_only", 1)) if cfg else True
        await db.add_autoreact_channel(gid, self.channel_id, emojis, photos_only=p_only)
        
        cog = interaction.client.get_cog("AutoReact")
        if cog:
            cog._cache[self.channel_id] = {
                "guild_id": gid,
                "channel_id": self.channel_id,
                "emojis": emojis,
                "photos_only": 1 if p_only else 0
            }
        await self._setup_view.refresh(interaction, f"Réactions mises à jour : {' '.join(emojis)} !")


class SetupAutoReactEmojisButton(discord.ui.Button):
    def __init__(self, channel_id: int, current_emojis: str):
        super().__init__(label="✏️ Emojis", style=discord.ButtonStyle.secondary, row=2)
        self.channel_id = channel_id
        self.current_emojis = current_emojis

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        await interaction.response.send_modal(SetupAutoReactEmojisModal(view, self.channel_id, self.current_emojis))


class SetupAutoReactToggleModeButton(discord.ui.Button):
    def __init__(self, channel_id: int, current_photos_only: bool):
        lbl = "📸 Photos uniquement" if current_photos_only else "💬 Tous les messages"
        super().__init__(label=lbl, style=discord.ButtonStyle.primary if current_photos_only else discord.ButtonStyle.secondary, row=2)
        self.channel_id = channel_id
        self.current_photos_only = current_photos_only

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        db = interaction.client.db
        gid = interaction.guild.id
        cfg = await db.get_autoreact_channel(gid, self.channel_id)
        emojis = cfg.get("emojis", ["❤️"]) if cfg else ["❤️"]
        new_mode = not self.current_photos_only
        await db.add_autoreact_channel(gid, self.channel_id, emojis, photos_only=new_mode)
        
        cog = interaction.client.get_cog("AutoReact")
        if cog:
            cog._cache[self.channel_id] = {
                "guild_id": gid,
                "channel_id": self.channel_id,
                "emojis": emojis,
                "photos_only": 1 if new_mode else 0
            }
        mode_text = "Photos uniquement" if new_mode else "Tous les messages"
        await view.refresh(interaction, f"Mode d'auto-réaction changé sur `{mode_text}` !")


class SetupAutoReactRemoveButton(discord.ui.Button):
    def __init__(self, channel_id: int):
        super().__init__(label="❌ Retirer ce salon", style=discord.ButtonStyle.danger, row=2)
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction):
        view: SetupView = self.view
        db = interaction.client.db
        gid = interaction.guild.id
        await db.remove_autoreact_channel(gid, self.channel_id)
        cog = interaction.client.get_cog("AutoReact")
        if cog:
            cog._cache.pop(self.channel_id, None)
        view.selected_autoreact_channel = None
        await view.refresh(interaction, "Le salon a été retiré des auto-réactions !")


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
        super().__init__(label="Tableau de bord", emoji="🏠", style=discord.ButtonStyle.secondary, row=4)

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

CATEGORY_THEMES = {
    "automod":   {"title": "Protection AutoMod",             "emoji": "🛡️", "color": 0xED4245, "desc": "Surveillance automatique du chat contre le spam, les liens frauduleux, les invitations et le flood."},
    "antiraid":  {"title": "Protection Anti-Raid",           "emoji": "⚔️", "color": 0xFEE75C, "desc": "Détection automatique des vagues de raids et filtrage des nouveaux comptes."},
    "antinuke":  {"title": "Protection Anti-Nuke",           "emoji": "☢️", "color": 0xED4245, "desc": "Protection d'urgence contre les destructions massives de salons, rôles et sanctions abusives."},
    "logs":      {"title": "Logs Avancés du Serveur",        "emoji": "🪵", "color": 0x57F287, "desc": "Création automatique de 4 salons dédiés (messages, vocal, modération, serveur)."},
    "welcome":   {"title": "Accueil & Bienvenue",            "emoji": "👋", "color": 0x5865F2, "desc": "Personnalisation complète du message d'accueil, du titre, de la bannière GIF et de la couleur."},
    "autorole":  {"title": "Configuration des Auto-Rôles",   "emoji": "🎭", "color": 0xEB459E, "desc": "Attribution automatique de rôles distincts pour les membres humains et les bots dès leur arrivée."},
    "tagrole":   {"title": "Rôle Automatique Tag",          "emoji": "🏷️", "color": 0x5865F2, "desc": "Attribution et retrait automatiques d'un rôle pour les membres arborant le tag du serveur."},
    "report":    {"title": "Signalements Staff",             "emoji": "🚨", "color": 0xFEE75C, "desc": "Salon privé recevant les signalements de messages effectués par les membres de la communauté."},
    "xp":        {"title": "Système de Niveaux & XP",        "emoji": "✨", "color": 0xF1C40F, "desc": "Gestion du salon d'annonces de montée de niveau (Level Up) et de l'expérience."},
    "tempvoice": {"title": "Salons Vocaux Temporaires",      "emoji": "🔊", "color": 0x9B59B6, "desc": "Création automatique de salons vocaux privés éphémères lorsque les membres rejoignent le déclencheur."},
    "stats":     {"title": "Salons de Statistiques en Direct","emoji": "📊", "color": 0x3498DB, "desc": "Salons vocaux verrouillés affichant en temps réel le décompte des membres, connectés et bots."},
    "autoreact": {"title": "Auto-Réactions Photos & Médias", "emoji": "📸", "color": 0xE91E63, "desc": "Ajout automatique de réactions émojis ciblées dès qu'une photo ou un média est posté."},
    "language":  {"title": "Langue du Serveur",              "emoji": "🌐", "color": 0x5865F2, "desc": "Langue utilisée par le bot pour l'affichage de ses messages et interactions sur ce serveur."},
}

class SetupView(discord.ui.LayoutView):
    def __init__(self, bot, lang: str, guild_id: int):
        super().__init__(timeout=300)
        self.bot = bot
        self.lang = lang
        self.guild_id = guild_id
        self.automod_module = None
        self.current_category = None
        self.selected_autoreact_channel = None

    async def init_home(self, guild: discord.Guild):
        await self._build_home(guild)

    async def _build_home(self, guild: discord.Guild, confirm_text: str = None):
        self.clear_items()
        settings = await self.bot.db.get_guild_settings(self.guild_id)
        am_cfg = await self.bot.db.get_automod_config(self.guild_id)
        ar_cfg = await self.bot.db.get_antiraid_config(self.guild_id)
        an_cfg = await self.bot.db.get_antinuke_config(self.guild_id)
        tv_cfg = await self.bot.db.get_tempvoice_config(self.guild_id)
        stats_cfg = await self.bot.db.get_stats_channels(self.guild_id)
        ar_channels = await self.bot.db.get_autoreact_channels(self.guild_id)

        # Statuts individuels
        is_am = bool(am_cfg.get("enabled"))
        is_ar = bool(ar_cfg.get("enabled"))
        is_an = bool(an_cfg.get("enabled"))
        is_logs = bool(settings.get("log_category_id"))
        is_welc = bool(settings.get("welcome_channel_id"))
        is_arole = bool(settings.get("autorole_id") or settings.get("autorole_bots_id"))
        is_rep = bool(settings.get("report_channel_id"))
        is_xp = bool(settings.get("levelup_channel_id"))
        is_stats = bool(stats_cfg)
        is_tv = bool(tv_cfg.get("trigger_channel_id"))
        is_areact = bool(ar_channels)
        is_tagrole = bool(settings.get("tagrole_id"))

        active_count = sum([is_am, is_ar, is_an, is_logs, is_welc, is_arole, is_tagrole, is_rep, is_xp, is_stats, is_tv, is_areact])
        total_modules = 12
        pct = round((active_count / total_modules) * 100)
        filled = round(active_count / total_modules * 10)
        bar = "🟩" * filled + "⬛" * (10 - filled)

        accent = Colors.SUCCESS.value if active_count >= 8 else (Colors.PRIMARY.value if active_count >= 4 else Colors.GOLD.value)
        cont = discord.ui.Container(accent_color=accent)

        # Header avec icône du serveur
        server_icon = guild.icon.url if guild.icon else None
        header_text = (
            f"# ⚙️ Tableau de Bord • {guild.name}\n"
            f"> Centre d'administration, de sécurité et d'automatisation de votre serveur.\n"
        )
        if server_icon:
            cont.add_item(discord.ui.Section(discord.ui.TextDisplay(header_text), accessory=discord.ui.Thumbnail(server_icon)))
        else:
            cont.add_item(discord.ui.TextDisplay(header_text))

        if confirm_text:
            cont.add_item(discord.ui.Separator())
            cont.add_item(discord.ui.TextDisplay(f"> ✅ **Modification enregistrée :** {confirm_text}"))

        cont.add_item(discord.ui.Separator())

        # Progression globale & KPIs
        kpi_text = (
            f"### 📊 État Général des Systèmes\n"
            f"> **Configuration :** `{active_count}/{total_modules} modules actifs` — **{pct}%**\n"
            f"> `{bar}`\n"
            f"> 🛡️ **Défense :** {'🟢' if is_am else '⚪'} AutoMod · {'🟢' if is_ar else '⚪'} Anti-Raid · {'🟢' if is_an else '⚪'} Anti-Nuke\n"
            f"> ⚙️ **Gestion :** {'🟢' if is_logs else '⚪'} Logs · {'🟢' if is_welc else '⚪'} Accueil · {'🟢' if is_arole else '⚪'} Auto-Rôle · {'🟢' if is_tagrole else '⚪'} Tag 17th\n"
            f"> 🌟 **Communauté :** {'🟢' if is_xp else '⚪'} XP · {'🟢' if is_tv else '⚪'} TempVoice · {'🟢' if is_stats else '⚪'} Stats · {'🟢' if is_areact else '⚪'} Auto-Réact · {'🟢' if is_rep else '⚪'} Reports"
        )
        cont.add_item(discord.ui.TextDisplay(kpi_text))
        cont.add_item(discord.ui.Separator())

        # Pillier 1 : Sécurité
        sec_text = (
            f"🛡️ **Sécurité & Défense**\n"
            f"> 🤖 **AutoMod** ➔ {'🟢 Activé' if is_am else '⚪ Désactivé'} *(Anti-spam, liens, flood)*\n"
            f"> ⚔️ **Anti-Raid** ➔ {'🟢 Activé' if is_ar else '⚪ Désactivé'} *({ar_cfg.get('join_threshold', 5)} joins / {ar_cfg.get('join_window', 10)}s)*\n"
            f"> ☢️ **Anti-Nuke** ➔ {'🟢 Activé' if is_an else '⚪ Désactivé'} *(Sanction: {an_cfg.get('action', 'quarantine').upper()})*"
        )
        cont.add_item(discord.ui.TextDisplay(sec_text))

        # Pillier 2 : Gestion
        welc_ch = guild.get_channel(settings.get("welcome_channel_id")) if settings.get("welcome_channel_id") else None
        welc_str = welc_ch.mention if welc_ch else "Non configuré"
        ar_human = guild.get_role(settings.get("autorole_id")) if settings.get("autorole_id") else None
        ar_bot = guild.get_role(settings.get("autorole_bots_id")) if settings.get("autorole_bots_id") else None
        ar_str = f"{ar_human.mention if ar_human else 'Non défini'} & {ar_bot.mention if ar_bot else 'Non défini'}"
        tag_role_id = settings.get("tagrole_id")
        tag_role_obj = guild.get_role(tag_role_id) if tag_role_id else None
        tag_text = settings.get("tagrole_text") or "17th"
        tag_str = f"{tag_role_obj.mention} `[{tag_text}]`" if tag_role_obj else "Non configuré"
        
        gest_text = (
            f"⚙️ **Modération & Arrivées**\n"
            f"> 🪵 **Logs Avancés** ➔ {'🟢 Configuré' if is_logs else '⚪ Inactif'}\n"
            f"> 👋 **Accueil Membres** ➔ {'🟢 ' + welc_str if is_welc else '⚪ Non configuré'}\n"
            f"> 🎭 **Auto-Rôles** ➔ {'🟢 ' + ar_str if is_arole else '⚪ Non configuré'}\n"
            f"> 🏷️ **Rôle Tag {tag_text}** ➔ {'🟢 ' + tag_str if is_tagrole else '⚪ Non configuré'}\n"
            f"> 🚨 **Signalements Staff** ➔ {'🟢 Actif' if is_rep else '⚪ Non configuré'}"
        )
        cont.add_item(discord.ui.TextDisplay(gest_text))

        # Pillier 3 : Communauté
        areact_count = len(ar_channels)
        comm_text = (
            f"🌟 **Communauté & Vocaux**\n"
            f"> ✨ **Système XP** ➔ {'🟢 Actif' if is_xp else '⚪ Non configuré'}\n"
            f"> 🔊 **Salons TempVoice** ➔ {'🟢 Actifs' if is_tv else '⚪ Non configuré'}\n"
            f"> 📊 **Statistiques Live** ➔ {'🟢 Salons créés' if is_stats else '⚪ Désactivé'}\n"
            f"> 📸 **Auto-Réactions Photos** ➔ {'🟢 ' + str(areact_count) + ' salon(s)' if is_areact else '⚪ Inactif'}"
        )
        cont.add_item(discord.ui.TextDisplay(comm_text))

        cont.add_item(discord.ui.Separator())

        # Menu déroulant unique (sans boutons superflus)
        cont.add_item(discord.ui.TextDisplay("👇 **Choisis un module à configurer dans le menu ci-dessous :**"))
        cont.add_item(discord.ui.ActionRow(SetupCategorySelect(self.lang, "home")))

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
        
        theme = CATEGORY_THEMES.get(category, {
            "title": category.capitalize(),
            "emoji": "⚙️",
            "color": Colors.INFO.value,
            "desc": "Paramètres du module"
        })

        def ch(cid):
            if not cid: return "Non défini"
            c = interaction.guild.get_channel(cid)
            return c.mention if c else "Introuvable"

        def role(rid):
            if not rid: return "Non défini"
            r = interaction.guild.get_role(rid)
            return r.mention if r else "Introuvable"

        cont = discord.ui.Container(accent_color=theme["color"])
        header_text = f"# ⚙️ Configuration › {theme['emoji']} {theme['title']}\n> {theme['desc']}\n"
        cont.add_item(discord.ui.TextDisplay(header_text))

        if confirm_text:
            cont.add_item(discord.ui.Separator())
            cont.add_item(discord.ui.TextDisplay(f"> ✅ **Modification enregistrée :** {confirm_text}"))

        cont.add_item(discord.ui.Separator())

        if category == "logs":
            curr_cat = ch(settings.get('log_category_id'))
            cont.add_item(discord.ui.TextDisplay(
                f"### 🪵 Logs Staff du Serveur\n"
                f"> 📁 **Catégorie actuelle :** {curr_cat}\n\n"
                f"💬 `logs-messages` ➔ suppressions et modifications de messages\n"
                f"🔊 `logs-vocaux` ➔ connexions, déconnexions et déplacements\n"
                f"🔨 `logs-modération` ➔ sanctions, kicks, bans, mutes, warns\n"
                f"⚙️ `logs-serveur` ➔ créations et suppressions de salons/rôles"
            ))
            cont.add_item(discord.ui.ActionRow(SetupLogsCategorySelect(lang)))
            if settings.get("log_category_id"):
                cont.add_item(discord.ui.ActionRow(SetupResetLogsButton()))
            
        elif category == "welcome":
            curr_ch = ch(settings.get('welcome_channel_id'))
            w_title = settings.get("welcome_title") or "Non défini (par défaut: Bienvenue sur {server} !)"
            w_msg = settings.get("welcome_message") or "Non défini (message standard avec mentions)"
            w_img = "✅ Configuré" if settings.get("welcome_image") else "❌ Aucune image/GIF"
            w_col = settings.get("welcome_color") or "Par défaut (#5865F2)"
            cont.add_item(discord.ui.TextDisplay(
                f"### 📋 Paramètres du Message d'Accueil\n"
                f"> 📍 **Salon de bienvenue :** {curr_ch}\n"
                f"> 🏷️ **Titre :** `{w_title}`\n"
                f"> 💬 **Message :** {w_msg}\n"
                f"> 🖼️ **Image / GIF :** {w_img}\n"
                f"> 🎨 **Couleur :** `{w_col}`"
            ))
            cont.add_item(discord.ui.ActionRow(SetupChannelSelect(lang, "welcome_channel_id", "setup.welcome_placeholder")))
            cont.add_item(discord.ui.ActionRow(
                SetupTitleButton(lang, "welcome_title", "Titre de bienvenue", settings.get("welcome_title")),
                SetupMessageButton(lang, "welcome_message", t(lang, "setup.welcome_modal_title"), settings.get("welcome_message")),
                SetupImageButton(lang, "welcome_image", "Bannière / GIF", settings.get("welcome_image")),
                SetupColorButton(lang, "welcome_color", "Couleur Bienvenue", settings.get("welcome_color"))
            ))
            reset_buttons = []
            if settings.get("welcome_channel_id"):
                reset_buttons.append(SetupResetSettingButton("welcome_channel_id", "Désactiver salon", "Le salon de bienvenue a été désactivé !"))
            if settings.get("welcome_image"):
                reset_buttons.append(SetupResetSettingButton("welcome_image", "Retirer image", "L'image de bienvenue a été retirée !", emoji="🗑️"))
            if settings.get("welcome_title"):
                reset_buttons.append(SetupResetSettingButton("welcome_title", "Reset Titre", "Le titre a été réinitialisé !", emoji="🔄"))
            if reset_buttons:
                cont.add_item(discord.ui.ActionRow(*reset_buttons))

        elif category == "autorole":
            r_human = role(settings.get('autorole_id'))
            r_bot = role(settings.get('autorole_bots_id'))
            cont.add_item(discord.ui.TextDisplay(
                f"### 📋 Rôles Automatiques à l'Arrivée\n"
                f"> 👤 **Rôle Membres Humains :** {r_human}\n"
                f"> 🤖 **Rôle Bots :** {r_bot}\n\n"
                f"> *Les rôles sont automatiquement attribués dès qu'un membre ou un bot rejoint le serveur.*"
            ))
            cont.add_item(discord.ui.TextDisplay("**👤 Définir le rôle pour les membres humains :**"))
            cont.add_item(discord.ui.ActionRow(SetupRoleSelect(lang, "autorole_id", "Sélectionner le rôle pour les humains...", row=1)))
            cont.add_item(discord.ui.TextDisplay("**🤖 Définir le rôle pour les bots :**"))
            cont.add_item(discord.ui.ActionRow(SetupRoleSelect(lang, "autorole_bots_id", "Sélectionner le rôle pour les bots...", row=2)))

            reset_buttons = []
            if settings.get("autorole_id"):
                reset_buttons.append(SetupResetSettingButton("autorole_id", "Retirer rôle humains", "L'auto-rôle humains a été désactivé !", emoji="👤", row=3))
            if settings.get("autorole_bots_id"):
                reset_buttons.append(SetupResetSettingButton("autorole_bots_id", "Retirer rôle bots", "L'auto-rôle bots a été désactivé !", emoji="🤖", row=3))
            if reset_buttons:
                cont.add_item(discord.ui.ActionRow(*reset_buttons))

        elif category == "tagrole":
            r_tag = role(settings.get('tagrole_id'))
            tag_text = settings.get("tagrole_text") or "17th"
            tag_members_count = 0
            role_obj = interaction.guild.get_role(settings.get('tagrole_id')) if settings.get('tagrole_id') else None
            role_members_count = len(role_obj.members) if role_obj else 0
            
            from cogs.systems.tagrole import member_has_tag
            for m in interaction.guild.members:
                if not m.bot and member_has_tag(m, tag_text, interaction.guild):
                    tag_members_count += 1

            cont.add_item(discord.ui.TextDisplay(
                f"### 🏷️ Rôle Automatique Lié au Tag\n"
                f"> 🎭 **Rôle attribué :** {r_tag}\n"
                f"> 🏷️ **Tag recherché :** `{tag_text}`\n"
                f"> 👥 **Porteurs du tag détectés :** `{tag_members_count}` membre(s)\n"
                f"> 🛡️ **Membres ayant le rôle :** `{role_members_count}` membre(s)\n\n"
                f"**Détections automatiques prises en compte :**\n"
                f"> 🏷️ Badge Serveur Discord *(Tag Clan / Primary Guild)*\n"
                f"> 💬 Pseudo et surnom du membre sur le serveur\n"
                f"> 💭 Statut personnalisé Discord\n\n"
                f"> *Le rôle est automatiquement attribué dès que le membre ajoute le tag, et retiré dès qu'il l'enlève.*"
            ))
            cont.add_item(discord.ui.TextDisplay("**🎭 Définir le rôle pour les porteurs du tag :**"))
            cont.add_item(discord.ui.ActionRow(SetupRoleSelect(lang, "tagrole_id", "Sélectionner le rôle à attribuer pour le tag...", row=1)))

            action_row = [
                SetupTagTextButton(tag_text),
                SetupTagScanButton()
            ]
            if settings.get("tagrole_id"):
                action_row.append(SetupResetSettingButton("tagrole_id", "Désactiver", "Le rôle tag a été désactivé !", emoji="🗑️", row=2))
            cont.add_item(discord.ui.ActionRow(*action_row))
            
        elif category == "report":
            curr_rep = ch(settings.get('report_channel_id'))
            cont.add_item(discord.ui.TextDisplay(
                f"### 📋 Salon des Signalements Staff\n"
                f"> **Salon actuel :** {curr_rep}\n"
                f"> Reçoit les alertes de messages signalés par la communauté pour vérification modérateur."
            ))
            cont.add_item(discord.ui.ActionRow(SetupChannelSelect(lang, "report_channel_id", "setup.report_placeholder")))
            if settings.get("report_channel_id"):
                cont.add_item(discord.ui.ActionRow(
                    SetupResetSettingButton("report_channel_id", "Désactiver les signalements", "Le salon des signalements a été désactivé !")
                ))
            
        elif category == "language":
            cont.add_item(discord.ui.TextDisplay(
                f"### 📋 Langue du Bot\n"
                f"> **Langue actuelle :** `{self.lang.upper()}`\n"
                f"> Modifie la langue utilisée par le bot pour l'ensemble des interactions."
            ))
            cont.add_item(discord.ui.ActionRow(SetupLanguageSelect(lang)))
            
        elif category == "xp":
            curr_xp = ch(settings.get('levelup_channel_id'))
            cont.add_item(discord.ui.TextDisplay(
                f"### 📋 Salon d'Annonces de Niveau (Level Up)\n"
                f"> **Salon actuel :** {curr_xp}\n"
                f"> Salon où le bot annoncera publiquement les montées de rang et nouveaux rôles débloqués."
            ))
            cont.add_item(discord.ui.ActionRow(SetupChannelSelect(lang, "levelup_channel_id", "Sélectionner un salon pour le Level Up")))
            if settings.get("levelup_channel_id"):
                cont.add_item(discord.ui.ActionRow(
                    SetupResetSettingButton("levelup_channel_id", "Désactiver annonces XP", "Les annonces de Level Up ont été désactivées !")
                ))

        elif category == "stats":
            stats_channels = await self.bot.db.get_stats_channels(self.guild_id)
            btn = StatsToggleButton(bool(stats_channels))
            cont.add_item(discord.ui.Section(
                discord.ui.TextDisplay(
                    f"### 📋 Salons de Statistiques en Direct\n"
                    f"> **État actuel :** {'🟢 Salons créés et actifs' if stats_channels else '⚪ Désactivé'}\n"
                    f"> Génère automatiquement des salons vocaux verrouillés affichant :\n"
                    f"> 👥 Membres totaux\n"
                    f"> 🟢 Membres connectés\n"
                    f"> 🤖 Bots\n"
                    f"> *Mis à jour automatiquement toutes les 10 minutes.*"
                ),
                accessory=btn
            ))

        elif category == "tempvoice":
            tv_config = await self.bot.db.get_tempvoice_config(self.guild_id)
            trig_ch = ch(tv_config.get("trigger_channel_id"))
            cat_ch = ch(tv_config.get("category_id"))
            cont.add_item(discord.ui.TextDisplay(
                f"### 📋 Paramètres Salons Vocaux Temporaires\n"
                f"> 🎙️ **Salon déclencheur :** {trig_ch}\n"
                f"> 📁 **Catégorie d'accueil :** {cat_ch}\n"
                f"> 🏷️ **Format du nom :** `{tv_config.get('name_format', '✨ | Salon de {user}')}`\n"
                f"> 👥 **Limite par défaut :** `{tv_config.get('default_limit', 0) or 'Illimitée'}`"
            ))
            cont.add_item(discord.ui.ActionRow(SetupTVChannelSelect("Sélectionner le salon déclencheur (Vocal)", is_category=False)))
            cont.add_item(discord.ui.ActionRow(SetupTVChannelSelect("Sélectionner la catégorie d'accueil", is_category=True)))
            action_items = [SetupTVButton(tv_config)]
            if tv_config.get("trigger_channel_id") or tv_config.get("category_id"):
                action_items.append(SetupResetTVButton())
            cont.add_item(discord.ui.ActionRow(*action_items))

        elif category == "autoreact":
            ar_channels = await self.bot.db.get_autoreact_channels(self.guild_id)
            desc_lines = ["### 📸 Salons d'Auto-Réaction Actifs"]
            if ar_channels:
                for c in ar_channels:
                    ch_obj = interaction.guild.get_channel(c["channel_id"])
                    ch_mention = ch_obj.mention if ch_obj else f"`#{c['channel_id']}`"
                    mode = "Photos uniquement" if c.get("photos_only", 1) else "Tous messages"
                    emojis_str = " ".join(c.get("emojis", ["❤️"]))
                    desc_lines.append(f"> 📍 {ch_mention} ➔ {emojis_str} *({mode})*")
            else:
                desc_lines.append("> ❌ *Aucun salon configuré pour le moment.*")

            desc_lines.append("\n> Sélectionnez un salon ci-dessous pour l'ajouter ou modifier ses réactions.")
            cont.add_item(discord.ui.TextDisplay("\n".join(desc_lines)))
            cont.add_item(discord.ui.ActionRow(SetupAutoReactChannelSelect()))

            # Déterminer quel salon afficher pour les boutons d'action
            active_target = None
            if self.selected_autoreact_channel and any(c["channel_id"] == self.selected_autoreact_channel for c in ar_channels):
                active_target = next(c for c in ar_channels if c["channel_id"] == self.selected_autoreact_channel)
            elif ar_channels:
                active_target = ar_channels[0]

            if active_target:
                t_chid = active_target["channel_id"]
                t_emojis = " ".join(active_target.get("emojis", ["❤️"]))
                t_p_only = bool(active_target.get("photos_only", 1))
                cont.add_item(discord.ui.TextDisplay(f"⚙️ **Configuration pour <#{t_chid}> :**"))
                cont.add_item(discord.ui.ActionRow(
                    SetupAutoReactEmojisButton(t_chid, t_emojis),
                    SetupAutoReactToggleModeButton(t_chid, t_p_only),
                    SetupAutoReactRemoveButton(t_chid)
                ))
            
        elif category == "automod":
            am_cfg = await self.bot.db.get_automod_config(self.guild_id)
            btn_am = AutomodToggleButton(bool(am_cfg["enabled"]))
            cont.add_item(discord.ui.Section(
                discord.ui.TextDisplay(
                    f"### 🛡️ État Global AutoMod\n"
                    f"> **Statut :** {'🟢 Système actif sur tout le serveur' if am_cfg['enabled'] else '⚪ Système désactivé'}"
                ),
                accessory=btn_am
            ))

            # Table récapitulative des sous-modules
            def m_status(mod_key):
                en = bool(am_cfg.get(f"{mod_key}_enabled", 0))
                act = am_cfg.get(f"{mod_key}_action", "warn").upper()
                return f"{'🟢' if en else '⚪'} `{act}`"

            overview_mods = (
                f"### 📋 Sous-Modules AutoMod\n"
                f"> 🔁 **Anti-Spam :** {m_status('spam')} ({am_cfg.get('spam_threshold', 5)} msg/5s)\n"
                f"> 🔗 **Anti-Liens :** {m_status('link')}\n"
                f"> 📨 **Anti-Invites :** {m_status('invite')}\n"
                f"> 🔠 **Anti-Majuscules :** {m_status('caps')} ({am_cfg.get('caps_threshold', 70)}%)\n"
                f"> 📢 **Anti-Mentions :** {m_status('mention')} ({am_cfg.get('mention_threshold', 4)} pings)\n"
                f"> 🌊 **Anti-Flood :** {m_status('flood')} ({am_cfg.get('flood_threshold', 6)} lignes)"
            )
            cont.add_item(discord.ui.TextDisplay(overview_mods))
            
            if self.automod_module:
                mod = self.automod_module
                is_enabled = bool(am_cfg[f"{mod}_enabled"])
                action = am_cfg[f"{mod}_action"]
                threshold = am_cfg.get(f"{mod}_threshold", 0)
                
                cont.add_item(discord.ui.TextDisplay(f"### ⚙️ Configuration du module : `{mod.upper()}`"))
                sec_tog = discord.ui.Section(discord.ui.TextDisplay(f"**État :** {'🟢 Activé' if is_enabled else '⚪ Désactivé'}"), accessory=AutomodModuleToggleButton(mod, is_enabled))
                cont.add_item(sec_tog)
                
                if mod not in ["link", "invite"]:
                    sec_thresh = discord.ui.Section(discord.ui.TextDisplay(f"**Seuil de détection :** `{threshold}`"), accessory=AutomodThresholdButton(mod, threshold))
                    cont.add_item(sec_thresh)
            
            cont.add_item(discord.ui.ActionRow(AutomodModuleSelect(self.automod_module)))
            if self.automod_module:
                cont.add_item(discord.ui.ActionRow(AutomodActionSelect(self.automod_module, action if self.automod_module else "warn")))
                
        elif category == "antiraid":
            ar_cfg = await self.bot.db.get_antiraid_config(self.guild_id)
            cont.add_item(discord.ui.Section(
                discord.ui.TextDisplay(
                    f"### ⚔️ Système Anti-Raid\n"
                    f"> **Statut :** {'🟢 Protection active' if ar_cfg['enabled'] else '⚪ Désactivé'}\n"
                    f"> **Déclenchement :** `{ar_cfg['join_threshold']}` arrivées en moins de `{ar_cfg['join_window']}` secondes\n"
                    f"> **Âge minimum :** `{ar_cfg['min_account_age']} jours` ({'Inactif' if ar_cfg['min_account_age'] == 0 else 'Actif'})\n"
                    f"> **Sanction :** `{ar_cfg['action'].upper()}`"
                ),
                accessory=AntiraidToggleButton(bool(ar_cfg["enabled"]))
            ))
            cont.add_item(discord.ui.Section(discord.ui.TextDisplay("**Seuil de détection rapide :**"), accessory=AntiraidThresholdButton(ar_cfg["join_threshold"], ar_cfg["join_window"])))
            cont.add_item(discord.ui.Section(discord.ui.TextDisplay("**Filtre par âge de compte Discord :**"), accessory=AntiraidAgeButton(ar_cfg["min_account_age"])))
            cont.add_item(discord.ui.ActionRow(AntiraidActionSelect(ar_cfg["action"])))

        elif category == "antinuke":
            an_cfg = await self.bot.db.get_antinuke_config(self.guild_id)
            al_ch = ch(an_cfg.get("alert_channel_id"))
            cont.add_item(discord.ui.Section(
                discord.ui.TextDisplay(
                    f"### ☢️ Système Anti-Nuke (Destruction de Masse)\n"
                    f"> **Statut :** {'🟢 Protection active' if an_cfg['enabled'] else '⚪ Désactivé'}\n"
                    f"> **Sanction d'urgence :** `{an_cfg['action'].upper()}` (Quarantaine / Ban / Kick)\n"
                    f"> **Salon d'alerte :** {al_ch}\n\n"
                    f"> ⛔ **Bannissements :** `{an_cfg.get('ban_threshold', 3)}/min`\n"
                    f"> 👢 **Expulsions :** `{an_cfg.get('kick_threshold', 3)}/min`\n"
                    f"> 📁 **Suppr. Salons :** `{an_cfg.get('channel_delete_threshold', 2)}/min`\n"
                    f"> 🎭 **Suppr. Rôles :** `{an_cfg.get('role_delete_threshold', 2)}/min`"
                ),
                accessory=AntiNukeToggleButton(bool(an_cfg["enabled"]))
            ))
            
            btn_thresh = discord.ui.Button(label="Modifier les seuils", style=discord.ButtonStyle.secondary, emoji="⚙️")
            async def open_thresh_modal(inter: discord.Interaction):
                await inter.response.send_modal(AntiNukeThresholdsModal(self, an_cfg))
            btn_thresh.callback = open_thresh_modal
            cont.add_item(discord.ui.Section(discord.ui.TextDisplay("**Ajuster les seuils de tolérance par minute :**"), accessory=btn_thresh))
            
            cont.add_item(discord.ui.ActionRow(AntiNukeActionSelect(an_cfg["action"])))
            cont.add_item(discord.ui.ActionRow(AntiNukeAlertChannelSelect()))

        cont.add_item(discord.ui.Separator())
        cont.add_item(discord.ui.ActionRow(SetupCategorySelect(lang, category)))
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

    # ── /config & /setup & /autorole ──────────────────────────────────────────

    @app_commands.command(name="config", description="Affiche la configuration actuelle du bot")
    @app_commands.default_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction):
        lang  = await self.bot.db.get_guild_lang(interaction.guild_id)
        view  = SetupView(self.bot, lang, interaction.guild.id)
        await view.init_home(interaction.guild)
        await interaction.response.send_message(view=view, ephemeral=True)

    @app_commands.command(name="setup", description="Panneau de configuration du bot")
    @app_commands.default_permissions(manage_guild=True)
    async def setup(self, interaction: discord.Interaction):
        await self.config(interaction)

    @app_commands.command(name="autorole", description="Configure ou désactive le rôle automatique à l'arrivée")
    @app_commands.describe(
        role="Le rôle à attribuer (laissez vide pour désactiver)",
        cible="Attribuer ce rôle aux membres humains ou aux bots"
    )
    @app_commands.choices(cible=[
        app_commands.Choice(name="👤 Humains (Membres)", value="humans"),
        app_commands.Choice(name="🤖 Bots", value="bots"),
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def autorole(self, interaction: discord.Interaction, role: discord.Role = None, cible: str = "humans"):
        setting_key = "autorole_bots_id" if cible == "bots" else "autorole_id"
        cible_name = "des bots" if cible == "bots" else "des membres humains"

        if role is None:
            await self.bot.db.update_guild_setting(interaction.guild.id, setting_key, None)
            return await interaction.response.send_message(f"✅ L'auto-rôle {cible_name} a été **désactivé** avec succès. 🎭", ephemeral=True)

        me = interaction.guild.me
        if me and me.top_role and role >= me.top_role:
            return await interaction.response.send_message(embed=error_embed("❌ Ce rôle est supérieur ou égal au rôle du bot."), ephemeral=True)

        await self.bot.db.update_guild_setting(interaction.guild.id, setting_key, role.id)
        await interaction.response.send_message(embed=success_embed(f"✅ L'auto-rôle {cible_name} a été défini sur {role.mention}."), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Config(bot))
