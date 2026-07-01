import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from utils.colors import Colors


# ══════════════════════════════════════════════════════════════════════════════
#  Help data
# ══════════════════════════════════════════════════════════════════════════════

HELP_PAGES: dict[str, dict] = {
    "home": {
        "label": "🏠 Vue d'ensemble",
        "color": 0x5865F2,
        "title": "📋 Aide — Vue d'ensemble",
        "description": (
            "Bienvenue dans l'aide ! Choisis une catégorie ci-dessous.\n​"
        ),
        "fields": [
            ("🛡️ Modération",                "Kick, ban, mute, warn, history, clear, lock…",  True),
            ("🤖 Auto-Mod & Anti-Raid",       "Spam, flood, invites, caps, antiraid…",         True),
            ("⭐ XP & Niveaux",               "Rank, leaderboard paginé, rôles par niveau…",   True),
            ("🎫 Tickets",                    "Système de support par catégories…",            True),
            ("🎭 Rôles",                      "Rôles réactifs, auto-sanctions…",               True),
            ("🎙️ Vocal Temporaire",           "Salons vocaux auto avec panneau intégré…",      True),
            ("🖼️ Embeds",                     "Créer des messages riches avec boutons…",       True),
            ("🎉 Giveaways",                  "Tirages au sort…",                              True),
            ("⭐ Starboard & AFK",            "Messages épinglés, statut absent…",             True),
            ("💜 Communauté",                 "Boost rewards, signalements…",                  True),
            ("🔐 Permissions",                "Restreindre les commandes par rôle/salon…",     True),
            ("⚙️ Configuration",              "Logs, welcome, langue, autorole, infos…",       True),
        ],
    },
    "moderation": {
        "label": "🛡️ Modération",
        "color": 0xED4245,
        "title": "🛡️ Modération",
        "description": "Gestion des membres et application des sanctions.",
        "fields": [
            ("🚫 Sanctions",
             "`/kick @membre [raison]` — Expulse un membre\n"
             "`/ban @membre [durée] [raison]` — Bannit un membre\n"
             "`/unban user_id` — Débannit un utilisateur\n"
             "`/mute @membre durée [raison]` — Timeout un membre\n"
             "`/unmute @membre` — Retire le timeout",
             False),
            ("⚠️ Avertissements",
             "`/warn @membre raison` — Ajoute un avertissement\n"
             "`/unwarn id` — Supprime un avertissement\n"
             "`/warnings @membre` — Voir les avertissements\n"
             "`/clearwarnings @membre` — Efface tout\n"
             "`/history @membre` — Historique de toutes les sanctions",
             False),
            ("🧹 Messages & Salons",
             "`/clear [nombre] [membre] [bots] [images] [contient]`\n"
             "`/slowmode [secondes]` — Mode lent\n"
             "`/lock [raison]` — Verrouille le salon\n"
             "`/unlock [raison]` — Déverrouille le salon",
             False),
        ],
    },
    "giveaways": {
        "label": "🎉 Giveaways",
        "color": 0xFFD700,
        "title": "🎉 Giveaways",
        "description": "Tirages au sort avec boutons.",
        "fields": [
            ("🎉 Giveaways",
             "`/giveaway start lot durée [gagnants] [salon]` — Lancer un giveaway\n"
             "`/giveaway end id` — Terminer manuellement\n"
             "`/giveaway reroll id` — Nouveau tirage\n"
             "`/giveaway list` — Giveaways actifs",
             False),
        ],
    },
    "starboard_afk": {
        "label": "⭐ Starboard & AFK",
        "color": 0xFFD700,
        "title": "⭐ Starboard & 💤 AFK",
        "description": "Épingle les meilleurs messages et gère les statuts AFK.",
        "fields": [
            ("⭐ Starboard",
             "`/starboard setup #salon [seuil]` — Configurer (défaut: 3⭐)\n"
             "`/starboard disable` — Désactiver\n"
             "`/starboard status` — Voir la configuration\n\n"
             "Les messages ayant assez de ⭐ sont automatiquement épinglés.",
             False),
            ("💤 AFK",
             "`/afk [raison]` — Passer en mode AFK (ou revenir si déjà AFK)\n\n"
             "Le bot notifie ceux qui te mentionnent que tu es AFK.\n"
             "Quand tu envoies un message, le statut AFK est retiré.",
             False),
        ],
    },
    "automod": {
        "label": "🤖 Auto-Mod & Anti-Raid",
        "color": 0xFF6B35,
        "title": "🤖 Auto-Modération & Anti-Raid",
        "description": "Protection automatique contre le spam, les raids et les abus.",
        "fields": [
            ("🔇 Auto-Modération",
             "`/automod status` — Voir la config\n"
             "`/automod toggle` — Activer/désactiver\n"
             "`/automod spam <max> <secs>` — Anti-spam\n"
             "`/automod flood <max> <secs>` — Anti-flood\n"
             "`/automod invites on/off` — Bloquer les invitations\n"
             "`/automod links on/off` — Bloquer tous les liens\n"
             "`/automod linkwhitelist domaine` — Domaine autorisé\n"
             "`/automod caps <pct>` — Limiter les majuscules\n"
             "`/automod mentions <max>` — Limiter les mentions\n"
             "`/automod bypass @role` — Rôle exempt",
             False),
            ("🛡️ Anti-Raid",
             "`/antiraid status` — Voir la config\n"
             "`/antiraid toggle` — Activer/désactiver\n"
             "`/antiraid config <joins> <secs>` — Seuil de détection\n"
             "`/antiraid lockdown` — Fermer le serveur d'urgence\n"
             "`/antiraid unlock` — Rouvrir le serveur",
             False),
            ("👻 Ghost Pings",
             "`/ghostping true/false` — Activer la détection des ghost pings\n"
             "*(Log automatique si un ping est supprimé en < 30 secondes)*",
             False),
        ],
    },
    "xp": {
        "label": "⭐ XP & Niveaux",
        "color": 0xFFD700,
        "title": "⭐ Système XP & Niveaux",
        "description": "Progression basée sur l'activité dans le chat. 15–25 XP par message (cooldown 60s).",
        "fields": [
            ("📊 Consultation",
             "`/rank [@membre]` — Voir ton rang et ton XP\n"
             "`/leaderboard` — Classement XP du serveur",
             False),
            ("⚙️ Administration",
             "`/setxp @membre quantité` — Définir l'XP\n"
             "`/addxp @membre quantité` — Ajouter de l'XP\n"
             "`/resetxp @membre` — Réinitialiser l'XP",
             False),
            ("🏆 Rôles par niveau",
             "`/xprole add <niveau> @role` — Rôle à un palier de niveau\n"
             "`/xprole remove <niveau>` — Supprimer un palier\n"
             "`/xprole list` — Voir tous les paliers",
             False),
        ],
    },
    "tickets": {
        "label": "🎫 Tickets",
        "color": 0x00B0F4,
        "title": "🎫 Système de Tickets",
        "description": "Créez et gérez des tickets de support avec catégories.",
        "fields": [
            ("⚙️ Configuration",
             "`/ticket setup <categorie> [staff]` — Configurer\n"
             "`/ticket categories` — Gérer les catégories\n"
             "`/ticket couleur <hex>` — Couleur des embeds\n"
             "`/ticket message` — Envoyer le panneau d'ouverture",
             False),
            ("🎛️ Gestion d'un ticket",
             "`/tadd @membre` — Ajouter un membre\n"
             "`/tremove @membre` — Retirer un membre\n"
             "`/tclaim` — Prendre en charge\n"
             "`/tunclaim` — Libérer le ticket",
             False),
        ],
    },
    "roles": {
        "label": "🎭 Rôles",
        "color": 0xEB459E,
        "title": "🎭 Rôles Réactifs & Auto-Sanctions",
        "description": "Attribution automatique de rôles via boutons, et sanctions programmées.",
        "fields": [
            ("🎭 Rôles réactifs",
             "`/rr create <titre> [description]` — Créer un panneau\n"
             "`/rr add <panel_id> @role [label] [emoji]` — Ajouter un rôle\n"
             "`/rr remove <panel_id> @role` — Retirer un rôle\n"
             "`/rr delete <panel_id>` — Supprimer le panneau\n"
             "`/rr list` — Lister les panneaux",
             False),
            ("🤖 Auto-Sanctions",
             "`/autosanction add <warns> <action> [durée]` — Ajouter un palier\n"
             "`/autosanction remove <warns>` — Supprimer un palier\n"
             "`/autosanction list` — Voir tous les paliers\n\n"
             "**Actions :** `mute` `kick` `ban` `tempban`",
             False),
        ],
    },
    "vocal": {
        "label": "🎙️ Vocal Temporaire",
        "color": 0x57F287,
        "title": "🎙️ Salons Vocaux Temporaires",
        "description": (
            "Rejoins le salon déclencheur → un salon vocal est créé automatiquement avec "
            "un panneau de contrôle **intégré directement dedans**."
        ),
        "fields": [
            ("⚙️ Configuration (Admin)",
             "`/tempvoice setup <déclencheur> [catégorie]` — Configurer\n"
             "`/tempvoice config [format] [limite]` — Format du nom et limite\n"
             "`/tempvoice status` — Voir la configuration\n\n"
             "**Format :** `{user}` = pseudo du membre",
             False),
            ("🎛️ Panneau de contrôle (dans le salon)",
             "🔒 **Lock** — Verrouiller l'accès\n"
             "👁️ **Masquer** — Cacher le salon\n"
             "🔐 **Privé** — Lock + Masquer simultanément\n"
             "✏️ **Renommer** — Changer le nom\n"
             "👥 **Limite** — Définir le nombre max de membres\n"
             "👑 **Transférer** — Donner la propriété\n"
             "➕ **Autoriser** — Inviter quelqu'un (mode privé)\n"
             "🚫 **Expulser** — Kick un membre du salon\n"
             "🗑️ **Supprimer** — Fermer le salon",
             False),
        ],
    },
    "embeds": {
        "label": "🖼️ Embeds",
        "color": 0x9B59B6,
        "title": "🖼️ Constructeur d'Embeds",
        "description": "Crée des messages riches avec boutons personnalisés (liens, rôles, messages).",
        "fields": [
            ("📝 Commandes",
             "`/embed create` — Formulaire de création\n"
             "`/embed edit <message_id>` — Modifier un embed existant\n\n"
             "**Boutons disponibles :**\n"
             "• 🔗 Lien URL\n"
             "• 🎭 Attribution/retrait de rôle\n"
             "• 💬 Message personnalisé en réponse",
             False),
        ],
    },
    "community": {
        "label": "💜 Communauté",
        "color": 0xF47FFF,
        "title": "💜 Communauté — Boosts & Signalements",
        "description": "Récompenses pour les boosters et système de signalement de membres.",
        "fields": [
            ("🚀 Boost Rewards",
             "`/boost setup @role #salon` — Configurer\n"
             "`/boost message <texte>` — Personnaliser le message\n"
             "`/boost status` — Voir la configuration\n\n"
             "**Variables :** `{mention}` `{user}` `{server}` `{count}`",
             False),
            ("🚨 Signalements",
             "`/report @membre raison` — Signaler un membre\n"
             "`/setreport #salon` — Salon des signalements\n\n"
             "Les modérateurs peuvent **Résoudre**, **Mute**, **Kick** ou **Ban** "
             "directement depuis le rapport.",
             False),
        ],
    },
    "permissions": {
        "label": "🔐 Permissions",
        "color": 0xFEE75C,
        "title": "🔐 Permissions par Commande",
        "description": "Restreins n'importe quelle commande par rôle ou salon. Les administrateurs sont toujours exemptés.",
        "fields": [
            ("⚙️ Commandes",
             "`/cmdperm allow-role <commande> @role` — Réserver à un rôle\n"
             "`/cmdperm deny-role <commande> @role` — Bloquer un rôle\n"
             "`/cmdperm channel <commande> #salon` — Limiter à un salon\n"
             "`/cmdperm reset <commande>` — Supprimer les restrictions\n"
             "`/cmdperm list [commande]` — Voir les restrictions",
             False),
            ("ℹ️ Ordre de vérification",
             "1. **Administrateur** → toujours autorisé\n"
             "2. **Rôle bloqué** → refus immédiat\n"
             "3. **Salon autorisé** → doit être dans ce salon\n"
             "4. **Rôle autorisé** → doit avoir ce rôle",
             False),
        ],
    },
    "config": {
        "label": "⚙️ Configuration",
        "color": 0x95A5A6,
        "title": "⚙️ Configuration du Serveur",
        "description": "Paramètres généraux du bot pour ce serveur.",
        "fields": [
            ("🔧 Paramètres",
             "`/config` — Voir toute la configuration\n"
             "`/setlanguage fr|en` — 🌐 Changer la langue du bot\n"
             "`/setlogs #salon` — Salon des logs\n"
             "`/setwelcome #salon [message]` — Salon d'arrivée\n"
             "`/setgoodbye #salon [message]` — Salon de départ\n"
             "`/setautorole @role` — Rôle automatique à l'arrivée\n"
             "`/setreport #salon` — Salon des signalements",
             False),
            ("ℹ️ Informations",
             "`/userinfo [@membre]` — Infos sur un membre\n"
             "`/serverinfo` — Infos sur le serveur\n"
             "`/botinfo` — Infos sur le bot\n"
             "`/avatar [@membre]` — Voir un avatar\n"
             "`/roleinfo @role` — Infos sur un rôle",
             False),
        ],
    },
}


def _build_help_embed(page_key: str) -> discord.Embed:
    page = HELP_PAGES.get(page_key, HELP_PAGES["home"])
    embed = discord.Embed(
        title=page["title"],
        description=page.get("description", ""),
        color=page["color"],
    )
    for name, value, inline in page.get("fields", []):
        embed.add_field(name=name, value=value, inline=inline)
    embed.set_footer(text="Toutes les commandes utilisent les slash commands (/)")
    return embed


# ══════════════════════════════════════════════════════════════════════════════
#  Help UI
# ══════════════════════════════════════════════════════════════════════════════

class HelpSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=data["label"], value=key)
            for key, data in HELP_PAGES.items()
        ]
        super().__init__(
            placeholder="📂 Choisir une catégorie…",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        embed = _build_help_embed(self.values[0])
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(HelpSelect())

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
        member = membre or interaction.user
        color  = member.color if member.color != discord.Color.default() else Colors.INFO
        embed  = discord.Embed(
            title=f"👤 {member.display_name}",
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)

        embed.add_field(name="🆔 ID",          value=str(member.id),                                    inline=True)
        embed.add_field(name="🤖 Bot",          value="✅" if member.bot else "❌",                      inline=True)
        embed.add_field(name="​",           value="​",                                         inline=True)
        embed.add_field(name="📅 Compte créé",  value=discord.utils.format_dt(member.created_at, 'D'),  inline=True)
        embed.add_field(name="📥 A rejoint",     value=discord.utils.format_dt(member.joined_at, 'D'),   inline=True)
        embed.add_field(name="​",           value="​",                                         inline=True)

        if member.is_timed_out():
            embed.add_field(
                name="🔇 Muté jusqu'à",
                value=discord.utils.format_dt(member.communication_disabled_until, 'R'),
                inline=False,
            )

        status_map = {
            discord.Status.online:  "🟢 En ligne",
            discord.Status.idle:    "🟡 Absent",
            discord.Status.dnd:     "🔴 Ne pas déranger",
            discord.Status.offline: "⚫ Hors ligne",
        }
        embed.add_field(name="📶 Statut", value=status_map.get(member.status, "Inconnu"), inline=True)
        embed.add_field(name="👑 Rôle haut",   value=member.top_role.mention, inline=True)
        embed.add_field(name="🔑 Permissions", value=self._key_perms(member), inline=False)

        roles = [r.mention for r in reversed(member.roles) if r != interaction.guild.default_role]
        if roles:
            roles_str = " ".join(roles[:15])
            if len(roles) > 15:
                roles_str += f" *+{len(roles) - 15} autres*"
            embed.add_field(name=f"🎭 Rôles ({len(roles)})", value=roles_str, inline=False)

        await interaction.response.send_message(embed=embed)

    def _key_perms(self, member: discord.Member) -> str:
        perms = member.guild_permissions
        checks = {
            "Administrateur": perms.administrator,
            "Gérer le serveur": perms.manage_guild,
            "Bannir": perms.ban_members,
            "Expulser": perms.kick_members,
            "Gérer les messages": perms.manage_messages,
            "Gérer les rôles": perms.manage_roles,
            "Mentionner @everyone": perms.mention_everyone,
        }
        active = [name for name, has in checks.items() if has]
        return ", ".join(active) if active else "Aucune permission clé"

    # ── /serverinfo ───────────────────────────────────────────────────────────

    @app_commands.command(name="serverinfo", description="Affiche les informations du serveur")
    async def serverinfo(self, interaction: discord.Interaction):
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

        embed.add_field(name="🆔 ID",          value=str(guild.id),                                       inline=True)
        embed.add_field(name="👑 Propriétaire", value=guild.owner.mention if guild.owner else "Inconnu",   inline=True)
        embed.add_field(name="📅 Créé le",      value=discord.utils.format_dt(guild.created_at, 'D'),      inline=True)

        total = guild.member_count
        bots  = sum(1 for m in guild.members if m.bot)
        embed.add_field(name="👥 Membres",  value=f"**{total}** ({total - bots} humains · {bots} bots)",  inline=True)
        embed.add_field(name="💬 Salons",   value=f"**{len(guild.text_channels)}** texte · **{len(guild.voice_channels)}** vocal", inline=True)
        embed.add_field(name="🎭 Rôles",    value=str(len(guild.roles)),                                   inline=True)
        embed.add_field(name="😀 Emojis",   value=f"{len(guild.emojis)}/{guild.emoji_limit}",              inline=True)
        embed.add_field(name="🚀 Boosts",   value=f"**{guild.premium_subscription_count}** (Niveau {guild.premium_tier})", inline=True)

        level_map = {
            discord.VerificationLevel.none:    "Aucune",
            discord.VerificationLevel.low:     "Faible",
            discord.VerificationLevel.medium:  "Moyenne",
            discord.VerificationLevel.high:    "Élevée",
            discord.VerificationLevel.highest: "Très élevée",
        }
        embed.add_field(name="🔒 Vérification", value=level_map.get(guild.verification_level, "Inconnue"), inline=True)
        await interaction.response.send_message(embed=embed)

    # ── /botinfo ──────────────────────────────────────────────────────────────

    @app_commands.command(name="botinfo", description="Affiche les informations du bot")
    async def botinfo(self, interaction: discord.Interaction):
        bot   = self.bot
        embed = discord.Embed(
            title=f"🤖 {bot.user.name}",
            color=Colors.INFO,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=bot.user.display_avatar.url)
        embed.add_field(name="🆔 ID",               value=str(bot.user.id),                        inline=True)
        embed.add_field(name="🌐 Serveurs",          value=str(len(bot.guilds)),                    inline=True)
        embed.add_field(name="👥 Membres totaux",    value=str(sum(g.member_count for g in bot.guilds)), inline=True)
        embed.add_field(name="📡 Latence",           value=f"{round(bot.latency * 1000)} ms",       inline=True)
        embed.add_field(name="📦 discord.py",        value=discord.__version__,                     inline=True)
        embed.add_field(name="⚡ Commandes",         value=str(len(bot.tree.get_commands())),        inline=True)
        await interaction.response.send_message(embed=embed)

    # ── /avatar ───────────────────────────────────────────────────────────────

    @app_commands.command(name="avatar", description="Affiche l'avatar d'un membre")
    @app_commands.describe(membre="Le membre dont voir l'avatar (toi-même si vide)")
    async def avatar(self, interaction: discord.Interaction, membre: discord.Member = None):
        member = membre or interaction.user
        embed  = discord.Embed(
            title=f"🖼️ Avatar de {member.display_name}",
            color=member.color if member.color != discord.Color.default() else Colors.INFO,
        )
        embed.set_image(url=member.display_avatar.url)
        embed.add_field(
            name="Liens",
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
        embed = discord.Embed(
            title=f"🎭 @{role.name}",
            color=role.color,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="🆔 ID",              value=str(role.id),          inline=True)
        embed.add_field(name="🎨 Couleur",          value=str(role.color),       inline=True)
        embed.add_field(name="📊 Position",         value=str(role.position),    inline=True)
        embed.add_field(name="🔔 Mentionnable",     value="✅" if role.mentionable else "❌", inline=True)
        embed.add_field(name="📌 Affiché séparé",   value="✅" if role.hoist     else "❌", inline=True)
        embed.add_field(name="⚙️ Géré Discord",     value="✅" if role.managed   else "❌", inline=True)
        embed.add_field(name="👥 Membres",           value=str(len(role.members)), inline=True)
        embed.add_field(name="📅 Créé le",           value=discord.utils.format_dt(role.created_at, 'D'), inline=True)
        await interaction.response.send_message(embed=embed)

    # ── /help ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="help", description="Affiche l'aide avec toutes les commandes")
    async def help(self, interaction: discord.Interaction):
        embed = _build_help_embed("home")
        view  = HelpView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Info(bot))
