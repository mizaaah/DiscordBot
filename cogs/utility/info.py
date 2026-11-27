import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from utils.colors import Colors
from utils.i18n import t



# ══════════════════════════════════════════════════════════════════════════════
#  Help UI (V2)
# ══════════════════════════════════════════════════════════════════════════════

HELP_PAGES = {
    "home": {
        "title": "Accueil & Aperçu",
        "emoji": "🏠",
        "desc": "Sommaire et guide d'utilisation du bot",
        "content": (
            "### 🧭 Bienvenue sur le Centre d'Aide !\n"
            "Explorez toutes les commandes du bot regroupées par domaine d'expertise :\n\n"
            "> 🛡️ **Modération :** Sanctions, avertissements et nettoyage avancé (`/clear`, `/ban`, `/mute`...)\n"
            "> 🚨 **Sécurité :** Audit de failles, Anti-Nuke, Anti-Raid et sauvegardes (`/security-audit`, `/backup`...)\n"
            "> ⚙️ **Configuration :** Dashboard complet et personnalisation (`/config`, `/autorole`, `/cmdperm`...)\n"
            "> ✨ **Niveaux XP :** Rangs, cartes d'expérience et récompenses de paliers (`/rank`, `/leaderboard`...)\n"
            "> 🎭 **Communauté :** Salons vocaux temporaires, Reaction Roles, Giveaways (`/tempvoice`, `/rr`...)\n"
            "> ℹ️ **Utilitaires :** Profils membres, infos serveur, créateur d'embeds (`/userinfo`, `/serverinfo`...)\n"
            "> 👑 **Administration :** Whitelist/Blacklist et maintenance bot (`/wl`, `/bl`...)\n\n"
            "💡 **Astuce :** Sélectionnez une catégorie dans le menu déroulant ci-dessous ou cliquez directement sur un bouton rapide."
        )
    },
    "moderation": {
        "title": "Modération & Sanctions",
        "emoji": "🛡️",
        "desc": "Outils avancés pour modérer et nettoyer le serveur",
        "content": (
            "### 🛡️ Commandes de Modération & Nettoyage\n"
            "• `/clear [nombre] [options...]` : Efface les messages avec filtres combinables :\n"
            "> - `membre` : supprime uniquement les messages d'un utilisateur spécifique\n"
            "> - `bots:Vrai` : supprime uniquement les messages envoyés par des bots/webhooks\n"
            "> - `liens:Vrai` : supprime uniquement les messages contenant des URLs ou invitations\n"
            "> - `images:Vrai` : supprime uniquement les messages avec images ou pièces jointes\n"
            "> - `contient` : supprime uniquement les messages contenant un mot spécifique\n"
            "> *(Sécurité native : les messages épinglés ne sont jamais supprimés)*\n\n"
            "• `/kick [membre] [raison]` : Expulse un membre du serveur\n"
            "• `/ban [membre] [delete_days] [raison]` : Bannit un membre définitivement\n"
            "• `/unban [user_id] [raison]` : Révoque le bannissement d'un utilisateur\n"
            "• `/mute [membre] [duree] [raison]` : Exclut temporairement un membre (ex: `10m`, `2h`, `1d`)\n"
            "• `/unmute [membre] [raison]` : Retire l'exclusion temporaire\n"
            "• `/warn [membre] [raison]` : Attribue un avertissement formel\n"
            "• `/warnings [membre]` : Historique des avertissements d'un membre\n"
            "• `/clearwarnings [membre]` : Réinitialise les avertissements d'un membre\n"
            "• `/autosanction add/remove/list` : Sanctions automatiques configurées par palier de warns\n"
            "• `/slowmode [secondes]` : Définit le ralentissement du salon textuel\n"
            "• `/lock` & `/unlock` : Verrouille ou rouvre le salon textuel\n"
            "• `/snipe` & `/editsnipe` : Récupère le dernier message supprimé ou modifié"
        )
    },
    "security": {
        "title": "Sécurité, Défense & Audit",
        "emoji": "🚨",
        "desc": "Audit de sécurité, Anti-Nuke, Anti-Raid et AutoMod",
        "content": (
            "### 🚨 Sécurité, Défense & Audit du Serveur\n"
            "• `/security-audit` *(ou `/audit`)* : **Audit de sécurité complet du serveur** :\n"
            "> - Analyse instantanée des permissions critiques du rôle `@everyone`\n"
            "> - Décompte des modérateurs et bots disposant des permissions Administrateur\n"
            "> - Évaluation des réglages Discord (2FA modération, filtre média, niveau vérif)\n"
            "> - Score sur 100 avec note (A+, A, B, C, D, F) et bouton `🔄 Réanalyser` en direct\n\n"
            "• `Anti-Nuke` *(via `/config`)* : Protège contre la destruction du serveur par un compte staff compromis :\n"
            "> - Bloque les suppressions massives de salons, rôles, expulsions et bannissements\n"
            "> - Sanctions immédiates : Quarantaine (retrait de tous les rôles), Ban ou Kick\n\n"
            "• `Anti-Raid` *(via `/config`)* : Détecte et bloque les vagues de comptes d'attaque :\n"
            "> - Ratio de joins par seconde configurable avec sanction automatique\n"
            "> - Âge minimum de compte Discord requis pour rejoindre le serveur\n\n"
            "• `AutoMod` *(via `/config`)* : Surveillance 24/7 en temps réel du chat :\n"
            "> - Modules : Anti-Spam, Anti-Liens, Anti-Invites, Anti-Majuscules, Anti-Mentions, Anti-Flood\n\n"
            "• `/ghostping` : Détecte et affiche les messages qui mentionnent des membres avant d'être effacés\n"
            "• `/backup create/load/list/delete` : Système de sauvegarde et restauration complète du serveur"
        )
    },
    "config": {
        "title": "Configuration & Gestion",
        "emoji": "⚙️",
        "desc": "Dashboard /config, auto-rôles, logs et personnalisation",
        "content": (
            "### ⚙️ Configuration & Gestion du Serveur\n"
            "• `/config` *(ou `/setup`)* : **Dashboard complet interactif (Components v2)**\n"
            "> - Gestion de l'ensemble des modules en une interface unifiée\n"
            "> - Indicateur de progression en direct et statuts des systèmes\n\n"
            "• `/autorole [cible:Humains/Bots] [role]` : Rôles automatiques distincts à l'arrivée\n"
            "• `Logs Avancés` *(via `/config`)* : Génère automatiquement 4 salons de logs sécurisés :\n"
            "> - `logs-messages`, `logs-vocaux`, `logs-modération`, `logs-serveur`\n\n"
            "• `Message d'Accueil` *(via `/config`)* : Personnalisation du titre, message, bannière GIF et couleur\n"
            "• `Auto-Réactions Photos` *(via `/config`)* : Réactions automatiques ciblées sur photos et médias\n"
            "• `/cmdperm` : Restreint ou autorise l'accès à certaines commandes slash selon les rôles\n"
            "• `/notifications` : Dashboard d'alertes de lives Twitch et vidéos TikTok automatiques\n"
            "• `/ticket setup` : Crée un panel de tickets de support avec salons privés dédiés"
        )
    },
    "xp": {
        "title": "Niveaux & Récompenses (XP)",
        "emoji": "✨",
        "desc": "Cartes de rang, classements et rôles par niveau",
        "content": (
            "### ✨ Système de Niveaux & Expérience (XP)\n"
            "• `/rank [membre]` : Affiche la carte de profil, niveau actuel et progression d'expérience\n"
            "• `/leaderboard` : Affiche le classement top 10 des membres les plus actifs du serveur\n"
            "• `/xprole add [niveau] [role]` : Associe un rôle de récompense débloqué à un niveau précis\n"
            "• `/xprole remove [niveau]` : Supprime une récompense de niveau\n"
            "• `/xprole list` : Affiche toutes les récompenses de rôles configurées\n"
            "• `/setxp [membre] [montant]` : Définit manuellement l'XP d'un utilisateur *(Admin)*\n"
            "• `/addxp [membre] [montant]` : Ajoute de l'XP à un utilisateur *(Admin)*\n"
            "• `/resetxp [membre/all]` : Réinitialise l'XP d'un membre ou de tout le serveur *(Admin)*\n"
            "• `Salon Level Up` *(via `/config`)* : Définit le salon recevant les annonces de niveau"
        )
    },
    "community": {
        "title": "Communauté & Salons Vocaux",
        "emoji": "🎭",
        "desc": "TempVoice, Reaction Roles, Giveaways et Starboard",
        "content": (
            "### 🎭 Communauté, Vocaux & Animation\n"
            "• `/tempvoice` : Déploie le système de salons vocaux temporaires automatiques :\n"
            "> - Les membres rejoignent le salon déclencheur pour créer leur salon privé éphémère\n"
            "> - Contrôle autonome : limite de membres, verrouillage et gestion\n\n"
            "• `/rr setup` / `/rr add` / `/rr remove` : Reaction Roles avec boutons interactifs élégants\n"
            "• `/giveaway start [duree] [gagnants] [prix]` : Lance un tirage au sort interactif\n"
            "• `/giveaway reroll [message_id]` : Tire un nouveau gagnant pour un concours clos\n"
            "• `/giveaway end [message_id]` : Termine un giveaway prématurément\n"
            "• `/giveaway list` : Liste tous les concours actuellement actifs\n"
            "• `/starboard` : Configure le salon vitrine qui met en avant les messages étoilés ⭐\n"
            "• `/afk set [raison]` : Déclare votre statut d'absence et prévient automatiquement les mentions"
        )
    },
    "utility": {
        "title": "Utilitaires & Informations",
        "emoji": "ℹ️",
        "desc": "Userinfo, serverinfo, avatar, botinfo et créateur d'embeds",
        "content": (
            "### ℹ️ Utilitaires & Fiches d'Information\n"
            "• `/userinfo [membre]` : Fiche complète d'un membre (date de création, arrivée, rôles, badges...)\n"
            "• `/serverinfo` : Statistiques détaillées du serveur (création, salons, rôles, boosts...)\n"
            "• `/botinfo` : Informations système, latence Gateway, version Discord.py et statut\n"
            "• `/avatar [membre]` : Affiche l'avatar en grand et fournit les liens de téléchargement HD\n"
            "• `/roleinfo [role]` : Analyse complète d'un rôle (permissions, couleur, membres...)\n"
            "• `/embed create` : Interface visuelle pour concevoir des embeds personnalisés\n"
            "• `/embed edit [message_id]` : Modifie un embed existant posté par le bot\n"
            "• `/embed button [message_id]` : Ajoute des boutons de redirection URL sous un message"
        )
    },
    "admin": {
        "title": "Administration Bot (Propriétaire)",
        "emoji": "👑",
        "desc": "Commandes propriétaires, whitelist et blacklist",
        "content": (
            "### 👑 Administration du Bot\n"
            "• `/wl add [membre]` : Ajoute un membre à la liste blanche (whitelist)\n"
            "• `/wl remove [membre]` : Retire un membre de la whitelist\n"
            "• `/wl list` : Liste l'ensemble des membres whitelistés\n"
            "• `/bl add [membre] [raison]` : Ajoute un utilisateur à la blacklist du bot\n"
            "• `/bl remove [membre]` : Retire un utilisateur de la blacklist\n"
            "• `/bl list` : Liste l'ensemble des utilisateurs blacklistés\n"
            "• `/reload [module]` : Recharge un module à chaud sans interrompre le bot\n"
            "• `/shutdown` : Arrête le bot en toute sécurité"
        )
    }
}

class HelpCategorySelect(discord.ui.Select):
    def __init__(self, current_page: str):
        options = [
            discord.SelectOption(
                label=data["title"],
                value=key,
                emoji=data["emoji"],
                description=data["desc"][:50],
                default=(key == current_page)
            ) for key, data in HELP_PAGES.items()
        ]
        super().__init__(placeholder="📖 Sélectionnez une catégorie à explorer...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_page(interaction, self.values[0])

class HelpViewV2(discord.ui.LayoutView):
    def __init__(self, bot: commands.Bot, default_page="home"):
        super().__init__(timeout=300)
        self.bot = bot
        self.current_page = default_page
        self._build_page(default_page)

    def _build_page(self, page_key: str):
        self.clear_items()
        data = HELP_PAGES.get(page_key, HELP_PAGES["home"])

        page_colors = {
            "home": 0x5865F2,
            "moderation": 0xED4245,
            "security": 0xED4245,
            "config": 0x5865F2,
            "xp": 0xF1C40F,
            "community": 0xEB459E,
            "utility": 0x3498DB,
            "admin": 0x9B59B6,
        }
        accent = page_colors.get(page_key, 0x5865F2)
        cont = discord.ui.Container(accent_color=accent)

        bot_user = self.bot.user
        avatar_url = bot_user.display_avatar.url if bot_user else None
        header_text = (
            f"# 📚 Centre d'Aide • {bot_user.name if bot_user else 'Bot'}\n"
            f"> Documentation interactive de l'ensemble des commandes et fonctionnalités.\n"
        )
        if avatar_url:
            cont.add_item(discord.ui.Section(discord.ui.TextDisplay(header_text), accessory=discord.ui.Thumbnail(avatar_url)))
        else:
            cont.add_item(discord.ui.TextDisplay(header_text))

        cont.add_item(discord.ui.Separator())

        if page_key != "home":
            cont.add_item(discord.ui.TextDisplay(f"## {data['emoji']} Section : {data['title']}\n> {data['desc']}"))
            cont.add_item(discord.ui.Separator())

        cont.add_item(discord.ui.TextDisplay(data["content"]))
        cont.add_item(discord.ui.Separator())

        cont.add_item(discord.ui.ActionRow(HelpCategorySelect(page_key)))

        def make_quick_btn(target: str, label: str, emoji: str):
            btn = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.primary if page_key == target else discord.ButtonStyle.secondary)
            async def btn_cb(inter: discord.Interaction):
                await self.show_page(inter, target)
            btn.callback = btn_cb
            return btn

        btn_home = make_quick_btn("home", "Accueil", "🏠")
        btn_mod = make_quick_btn("moderation", "Modération", "🛡️")
        btn_sec = make_quick_btn("security", "Sécurité", "🚨")
        btn_cfg = make_quick_btn("config", "Config", "⚙️")
        btn_xp = make_quick_btn("xp", "XP", "✨")
        cont.add_item(discord.ui.ActionRow(btn_home, btn_mod, btn_sec, btn_cfg, btn_xp))

        self.add_item(cont)

    async def show_page(self, interaction: discord.Interaction, page_key: str):
        self.current_page = page_key
        self._build_page(page_key)
        await interaction.response.edit_message(view=self, embed=None)

    async def send_initial(self, interaction: discord.Interaction):
        self._build_page(self.current_page)
        await interaction.response.send_message(view=self, ephemeral=True)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ══════════════════════════════════════════════════════════════════════════════
#  Cog
# ══════════════════════════════════════════════════════════════════════════════

class Info(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /userinfo ─────────────────────────────────────────────────────────────

    @app_commands.command(name="userinfo", description="Affiche les informations d'un membre")
    @app_commands.describe(membre="Le membre dont voir les infos (toi-même si vide)")
    async def userinfo(self, interaction: discord.Interaction, membre: discord.Member = None):
        lang   = await self.bot.db.get_guild_lang(interaction.guild_id)
        member = membre or interaction.user
        color  = member.color if member.color != discord.Color.default() else Colors.INFO
        embed  = discord.Embed(
            title=f"👤 {member.display_name}",
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)

        embed.add_field(name=t(lang, "info.id"),               value=f"> `{member.id}`",                                    inline=True)
        embed.add_field(name=t(lang, "info.bot"),              value="> ✅" if member.bot else "> ❌",                      inline=True)
        embed.add_field(name="​",                              value="​",                                         inline=True)
        embed.add_field(name=t(lang, "info.account_created"),  value=f"> {discord.utils.format_dt(member.created_at, 'D')}",  inline=True)
        embed.add_field(name=t(lang, "info.joined"),           value=f"> {discord.utils.format_dt(member.joined_at, 'D')}",   inline=True)
        embed.add_field(name="​",                              value="​",                                         inline=True)

        if member.is_timed_out():
            embed.add_field(
                name=t(lang, "info.muted_until"),
                value=discord.utils.format_dt(member.communication_disabled_until, 'R'),
                inline=False,
            )

        status_map = {
            discord.Status.online:  t(lang, "info.status_online"),
            discord.Status.idle:    t(lang, "info.status_idle"),
            discord.Status.dnd:     t(lang, "info.status_dnd"),
            discord.Status.offline: t(lang, "info.status_offline"),
        }
        embed.add_field(name=t(lang, "info.status"),     value=f"> {status_map.get(member.status, t(lang, 'info.status_unknown'))}", inline=True)
        embed.add_field(name=t(lang, "info.top_role"),   value=f"> {member.top_role.mention}", inline=True)
        embed.add_field(name="​",                        value="​", inline=True)
        embed.add_field(name=t(lang, "info.key_perms"),  value=f"> {self._key_perms(lang, member)}", inline=False)

        roles = [r.mention for r in reversed(member.roles) if r != interaction.guild.default_role]
        if roles:
            roles_str = " ".join(roles[:15])
            if len(roles) > 15:
                roles_str += t(lang, "info.roles_more", count=len(roles) - 15)
            embed.add_field(name=t(lang, "info.roles_field", count=len(roles)), value=roles_str, inline=False)

        await interaction.response.send_message(embed=embed)

    def _key_perms(self, lang: str, member: discord.Member) -> str:
        perms = member.guild_permissions
        checks = {
            t(lang, "info.perm_admin"): perms.administrator,
            t(lang, "info.perm_manage_guild"): perms.manage_guild,
            t(lang, "info.perm_ban"): perms.ban_members,
            t(lang, "info.perm_kick"): perms.kick_members,
            t(lang, "info.perm_manage_messages"): perms.manage_messages,
            t(lang, "info.perm_manage_roles"): perms.manage_roles,
            t(lang, "info.perm_mention_everyone"): perms.mention_everyone,
        }
        active = [name for name, has in checks.items() if has]
        return ", ".join(active) if active else t(lang, "info.no_key_perms")

    # ── /serverinfo ───────────────────────────────────────────────────────────

    @app_commands.command(name="serverinfo", description="Affiche les informations du serveur")
    async def serverinfo(self, interaction: discord.Interaction):
        lang  = await self.bot.db.get_guild_lang(interaction.guild_id)
        guild = interaction.guild
        embed = discord.Embed(
            title=f"🏰 {guild.name}",
            color=Colors.INFO,
            timestamp=discord.utils.utcnow(),
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        if guild.banner:
            embed.set_image(url=guild.banner.url)

        embed.add_field(name=t(lang, "info.id"),          value=f"> `{guild.id}`",                                       inline=True)
        embed.add_field(name=t(lang, "info.owner"),       value=f"> {guild.owner.mention if guild.owner else t(lang, 'info.unknown')}",   inline=True)
        embed.add_field(name=t(lang, "info.created_on"),  value=f"> {discord.utils.format_dt(guild.created_at, 'D')}",      inline=True)

        total = guild.member_count
        bots  = sum(1 for m in guild.members if m.bot)
        embed.add_field(name=t(lang, "info.members"),  value=f"> {t(lang, 'info.members_value', total=total, humans=total - bots, bots=bots)}",  inline=True)
        embed.add_field(name=t(lang, "info.channels"), value=f"> {t(lang, 'info.channels_value', text=len(guild.text_channels), voice=len(guild.voice_channels))}", inline=True)
        embed.add_field(name=t(lang, "info.roles"),    value=f"> `{len(guild.roles)}`",                                   inline=True)
        embed.add_field(name=t(lang, "info.emojis"),   value=f"> `{len(guild.emojis)}/{guild.emoji_limit}`",              inline=True)
        embed.add_field(name=t(lang, "info.boosts"),   value=f"> {t(lang, 'info.boosts_value', count=guild.premium_subscription_count, tier=guild.premium_tier)}", inline=True)

        level_map = {
            discord.VerificationLevel.none:    t(lang, "info.verif_none"),
            discord.VerificationLevel.low:     t(lang, "info.verif_low"),
            discord.VerificationLevel.medium:  t(lang, "info.verif_medium"),
            discord.VerificationLevel.high:    t(lang, "info.verif_high"),
            discord.VerificationLevel.highest: t(lang, "info.verif_highest"),
        }
        embed.add_field(name=t(lang, "info.verification"), value=f"> {level_map.get(guild.verification_level, t(lang, 'info.unknown'))}", inline=True)
        await interaction.response.send_message(embed=embed)

    # ── /botinfo ──────────────────────────────────────────────────────────────

    @app_commands.command(name="botinfo", description="Affiche les informations du bot")
    async def botinfo(self, interaction: discord.Interaction):
        lang  = await self.bot.db.get_guild_lang(interaction.guild_id)
        bot   = self.bot
        embed = discord.Embed(
            title=f"🤖 {bot.user.name}",
            color=Colors.INFO,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=bot.user.display_avatar.url)
        embed.add_field(name=t(lang, "info.id"),               value=f"> `{bot.user.id}`",                        inline=True)
        embed.add_field(name=t(lang, "info.servers"),          value=f"> `{len(bot.guilds)}`",                    inline=True)
        embed.add_field(name=t(lang, "info.total_members"),    value=f"> `{sum(g.member_count for g in bot.guilds)}`", inline=True)
        embed.add_field(name=t(lang, "info.latency"),          value=f"> `{round(bot.latency * 1000)} ms`",       inline=True)
        embed.add_field(name=t(lang, "info.discordpy"),        value=f"> `{discord.__version__}`",                inline=True)
        embed.add_field(name=t(lang, "info.commands"),         value=f"> `{len(bot.tree.get_commands())}`",        inline=True)
        await interaction.response.send_message(embed=embed)

    # ── /avatar ───────────────────────────────────────────────────────────────

    @app_commands.command(name="avatar", description="Affiche l'avatar d'un membre")
    @app_commands.describe(membre="Le membre dont voir l'avatar (toi-même si vide)")
    async def avatar(self, interaction: discord.Interaction, membre: discord.Member = None):
        lang   = await self.bot.db.get_guild_lang(interaction.guild_id)
        member = membre or interaction.user
        embed  = discord.Embed(
            title=t(lang, "info.avatar_title", member=member.display_name),
            color=member.color if member.color != discord.Color.default() else Colors.INFO,
        )
        embed.set_image(url=member.display_avatar.url)
        embed.add_field(
            name=t(lang, "info.links"),
            value=(
                f"[PNG]({member.display_avatar.with_format('png').url}) · "
                f"[JPG]({member.display_avatar.with_format('jpg').url}) · "
                f"[WebP]({member.display_avatar.with_format('webp').url})"
            ),
        )
        await interaction.response.send_message(embed=embed)

    # ── /roleinfo ─────────────────────────────────────────────────────────────

    @app_commands.command(name="roleinfo", description="Affiche les informations d'un rôle")
    @app_commands.describe(role="Le rôle dont voir les infos")
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role):
        lang  = await self.bot.db.get_guild_lang(interaction.guild_id)
        embed = discord.Embed(
            title=f"🎭 @{role.name}",
            color=role.color,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name=t(lang, "info.id"),              value=f"> `{role.id}`",          inline=True)
        embed.add_field(name=t(lang, "info.color"),          value=f"> `{role.color}`",       inline=True)
        embed.add_field(name=t(lang, "info.position"),         value=f"> `{role.position}`",    inline=True)
        embed.add_field(name=t(lang, "info.mentionable"),     value="> ✅" if role.mentionable else "> ❌", inline=True)
        embed.add_field(name=t(lang, "info.hoisted"),   value="> ✅" if role.hoist     else "> ❌", inline=True)
        embed.add_field(name=t(lang, "info.managed"),     value="> ✅" if role.managed   else "> ❌", inline=True)
        embed.add_field(name=t(lang, "info.members"),           value=f"> `{len(role.members)}`", inline=True)
        embed.add_field(name=t(lang, "info.created_on"),           value=f"> {discord.utils.format_dt(role.created_at, 'D')}", inline=True)
        await interaction.response.send_message(embed=embed)

    # ── /help ─────────────────────────────────────────────────────────────────

    async def _cmd_autocomplete(self, interaction: discord.Interaction, current: str):
        names = []
        for cmd in self.bot.tree.get_commands():
            if isinstance(cmd, app_commands.Group):
                for sub in cmd.commands:
                    if isinstance(sub, app_commands.Group):
                        for sub2 in sub.commands:
                            names.append(sub2.qualified_name)
                    else:
                        names.append(sub.qualified_name)
            else:
                names.append(cmd.qualified_name)
        filtered = sorted(c for c in names if current.lower() in c.lower())
        return [app_commands.Choice(name=c, value=c) for c in filtered[:25]]

    @app_commands.command(name="help", description="Affiche l'aide complète et moderne du bot")
    @app_commands.describe(commande="Aller directement à la section d'une commande précise (optionnel)")
    @app_commands.autocomplete(commande=_cmd_autocomplete)
    async def help(self, interaction: discord.Interaction, commande: str = None):
        cmd_map = {
            "kick": "moderation", "ban": "moderation", "unban": "moderation", "mute": "moderation",
            "unmute": "moderation", "warn": "moderation", "warnings": "moderation", "clearwarnings": "moderation",
            "clear": "moderation", "slowmode": "moderation", "lock": "moderation", "unlock": "moderation",
            "snipe": "moderation", "editsnipe": "moderation", "autosanction": "moderation",
            
            "security-audit": "security", "audit": "security", "backup": "security", "ghostping": "security",
            "automod": "security", "antiraid": "security", "antinuke": "security",
            
            "config": "config", "setup": "config", "autorole": "config", "cmdperm": "config",
            "notifications": "config", "ticket": "config",
            
            "rank": "xp", "leaderboard": "xp", "setxp": "xp", "addxp": "xp", "resetxp": "xp", "xprole": "xp",
            
            "tempvoice": "community", "rr": "community", "giveaway": "community", "starboard": "community", "afk": "community",
            
            "userinfo": "utility", "serverinfo": "utility", "botinfo": "utility", "avatar": "utility",
            "roleinfo": "utility", "embed": "utility",
            
            "wl": "admin", "bl": "admin", "reload": "admin", "shutdown": "admin"
        }
        
        page = "home"
        if commande:
            base_cmd = commande.split()[0].lower()
            page = cmd_map.get(base_cmd, "home")
            
        view = HelpViewV2(self.bot, default_page=page)
        await view.send_initial(interaction)


async def setup(bot: commands.Bot):
    await bot.add_cog(Info(bot))
