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
        "desc": "Sommaire et guide des commandes",
        "content": (
            "### 🌟 Bienvenue sur le Centre d'Aide 17th !\n"
            "Choisis une catégorie dans le menu déroulant ci-dessous pour découvrir toutes les fonctionnalités.\n\n"
            "🛡️ **Modération** ➔ Nettoyage du chat, sanctions & expulsions\n"
            "🚨 **Sécurité** ➔ Audit de failles, Anti-Nuke, Anti-Raid & Backups\n"
            "⚙️ **Configuration** ➔ Dashboard `/config`, auto-rôles & logs\n"
            "✨ **Niveaux XP** ➔ Rangs, leaderboard & rôles récompenses\n"
            "🎭 **Communauté** ➔ Vocaux temporaires, Reaction Roles & Giveaways\n"
            "ℹ️ **Utilitaires** ➔ Profils membres, infos serveur & embeds\n"
            "👑 **Administration** ➔ Gestion propriétaire & whitelist\n\n"
            "👇 *Utilise le menu déroulant ci-dessous pour explorer chaque section.*"
        )
    },
    "moderation": {
        "title": "Modération & Sanctions",
        "emoji": "🛡️",
        "desc": "Nettoyage, expulsions, mutes et bans",
        "content": (
            "### 🛡️ Commandes de Modération\n"
            "🧹 `/clear [nombre]` ➔ Suppression filtrée *(membres, bots, liens, images, texte)*\n"
            "🔨 `/ban [membre]` ➔ Bannir un membre du serveur\n"
            "🔓 `/unban [id]` ➔ Révoquer un bannissement\n"
            "👢 `/kick [membre]` ➔ Expulser un membre du serveur\n"
            "🔇 `/mute [membre] [durée]` ➔ Exclusion temporaire *(ex: 10m, 2h, 1d)*\n"
            "🔊 `/unmute [membre]` ➔ Retirer la sourdine d'un membre\n"
            "⚠️ `/warn [membre]` ➔ Attribuer un avertissement formel\n"
            "📋 `/warnings [membre]` ➔ Consulter l'historique des avertissements\n"
            "🗑️ `/clearwarnings [membre]` ➔ Réinitialiser les avertissements\n"
            "⚡ `/autosanction` ➔ Sanctions automatiques configurées par palier\n"
            "⏳ `/slowmode [secondes]` ➔ Définir le mode lent d'un salon\n"
            "🔒 `/lock` ➔ Verrouiller l'accès en écriture au salon\n"
            "🔓 `/unlock` ➔ Déverrouiller le salon\n"
            "👁️ `/snipe` ➔ Voir le dernier message supprimé\n"
            "✏️ `/editsnipe` ➔ Voir la dernière modification de message"
        )
    },
    "security": {
        "title": "Sécurité, Défense & Audit",
        "emoji": "🚨",
        "desc": "Audit sécurité, Anti-Nuke, Anti-Raid et AutoMod",
        "content": (
            "### 🚨 Sécurité, Défense & Audit\n"
            "🔍 `/security-audit` *(ou `/audit`)* ➔ Scan complet du serveur, score /100 et détection des failles\n"
            "☢️ **Anti-Nuke** *(via `/config`)* ➔ Bloque les destructions massives de salons, rôles et bans\n"
            "⚔️ **Anti-Raid** *(via `/config`)* ➔ Bloque les vagues de joins et filtre l'âge des comptes\n"
            "🤖 **AutoMod** *(via `/config`)* ➔ Anti-spam, liens, invites, majuscules, mentions, flood\n"
            "👻 `/ghostping` ➔ Détecte et affiche les pings fantômes supprimés\n"
            "💾 `/backup` ➔ Sauvegarde et restauration complète du serveur"
        )
    },
    "config": {
        "title": "Configuration & Gestion",
        "emoji": "⚙️",
        "desc": "Dashboard /config, auto-rôles, logs et réglages",
        "content": (
            "### ⚙️ Configuration & Gestion du Serveur\n"
            "🎛️ `/config` *(ou `/setup`)* ➔ Dashboard interactif pour tout configurer\n"
            "🎭 `/autorole [cible] [role]` ➔ Auto-rôles distincts pour humains et bots\n"
            "🏷️ `/tagrole [config/disable/scan]` ➔ Rôle automatique pour porteurs du tag 17th\n"
            "🪵 **Logs Avancés** *(via `/config`)* ➔ 4 salons dédiés *(messages, vocal, mod, serveur)*\n"
            "👋 **Accueil** *(via `/config`)* ➔ Titre, message, GIF et couleur de bienvenue\n"
            "📸 **Auto-Réactions** *(via `/config`)* ➔ Réactions automatiques sur photos et médias\n"
            "🔐 `/cmdperm` ➔ Verrouiller l'accès des commandes à certains rôles\n"
            "🔔 `/notifications` ➔ Alertes automatiques Twitch et TikTok\n"
            "🎟️ `/ticket setup` ➔ Panneau de support et tickets privés"
        )
    },
    "xp": {
        "title": "Niveaux & Récompenses (XP)",
        "emoji": "✨",
        "desc": "Cartes de rang, classements et rôles par niveau",
        "content": (
            "### ✨ Niveaux & Récompenses XP\n"
            "🏆 `/rank [membre]` ➔ Carte de profil, rang et progression XP\n"
            "👑 `/leaderboard` ➔ Classement des membres les plus actifs\n"
            "🎁 `/xprole add [niveau] [role]` ➔ Débloquer un rôle à un palier précis\n"
            "❌ `/xprole remove [niveau]` ➔ Supprimer un rôle de palier\n"
            "📜 `/xprole list` ➔ Afficher toutes les récompenses de rôles\n"
            "💎 `/addxp [membre] [xp]` ➔ Ajouter de l'XP à un membre\n"
            "⚙️ `/setxp [membre] [xp]` ➔ Modifier directement le niveau/XP\n"
            "🔄 `/resetxp [membre/all]` ➔ Remettre à zéro l'expérience\n"
            "📢 **Level Up** *(via `/config`)* ➔ Salon d'annonces de montée de niveau"
        )
    },
    "community": {
        "title": "Communauté & Salons Vocaux",
        "emoji": "🎭",
        "desc": "TempVoice, Reaction Roles, Giveaways et Starboard",
        "content": (
            "### 🎭 Communauté, Vocaux & Animation\n"
            "🔊 `/tempvoice` ➔ Salons vocaux temporaires automatiques personnalisables\n"
            "🔘 `/rr setup` ➔ Créer un panneau de reaction roles avec boutons\n"
            "➕ `/rr add` ➔ Ajouter un rôle à un bouton existant\n"
            "➖ `/rr remove` ➔ Retirer un bouton de rôle\n"
            "🎉 `/giveaway start` ➔ Lancer un concours avec compte à rebours\n"
            "🎲 `/giveaway reroll` ➔ Tirer un nouveau gagnant au sort\n"
            "⏹️ `/giveaway end` ➔ Terminer immédiatement un giveaway\n"
            "📜 `/giveaway list` ➔ Liste des concours actuellement actifs\n"
            "⭐ `/starboard` ➔ Salon vitrine des messages les plus étoilés\n"
            "💤 `/afk set [raison]` ➔ Prévenir les membres que tu es absent"
        )
    },
    "utility": {
        "title": "Utilitaires & Informations",
        "emoji": "ℹ️",
        "desc": "Userinfo, serverinfo, avatar, botinfo et embeds",
        "content": (
            "### ℹ️ Utilitaires & Informations\n"
            "👤 `/userinfo [membre]` ➔ Fiche complète, badges, création et rôles\n"
            "🏰 `/serverinfo` ➔ Statistiques détaillées, membres, boosts et salons\n"
            "🤖 `/botinfo` ➔ Version, latence en direct, mémoire et statut\n"
            "🖼️ `/avatar [membre]` ➔ Télécharger l'avatar en haute qualité\n"
            "🎭 `/roleinfo [role]` ➔ Analyse, permissions et membres d'un rôle\n"
            "🎨 `/embed create` ➔ Créateur visuel d'embeds personnalisés\n"
            "✏️ `/embed edit` ➔ Modifier un embed existant posté par le bot\n"
            "🔗 `/embed button` ➔ Ajouter des boutons liens URL sous un embed"
        )
    },
    "admin": {
        "title": "Administration Bot (Propriétaire)",
        "emoji": "👑",
        "desc": "Commandes propriétaires, whitelist et blacklist",
        "content": (
            "### 👑 Administration du Bot\n"
            "🛡️ `/wl add [membre]` ➔ Ajouter un membre à la whitelist\n"
            "❌ `/wl remove [membre]` ➔ Retirer de la whitelist\n"
            "📜 `/wl list` ➔ Voir la liste des membres whitelistés\n"
            "🚫 `/bl add [membre]` ➔ Bloquer un utilisateur (blacklist)\n"
            "✅ `/bl remove [membre]` ➔ Débloquer un utilisateur\n"
            "📋 `/bl list` ➔ Voir la liste des blacklistés\n"
            "⚡ `/reload [module]` ➔ Recharger un module à chaud\n"
            "🔌 `/shutdown` ➔ Éteindre le bot proprement"
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
        super().__init__(placeholder="📖 Choisir une catégorie...", options=options, row=0)

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
            f"# 📚 Centre d'Aide ✦ {bot_user.name if bot_user else '17th'}\n"
            f"> Documentation interactive de l'ensemble des commandes.\n"
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
            
            "config": "config", "setup": "config", "autorole": "config", "tagrole": "config", "cmdperm": "config",
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
