import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from utils.colors import Colors
from utils.i18n import t



# ══════════════════════════════════════════════════════════════════════════════
#  Help UI (V2)
# ══════════════════════════════════════════════════════════════════════════════

HELP_CATEGORIES = {
    "home": {
        "title": "📚 Centre d'Aide",
        "desc": "Sélectionnez une catégorie ci-dessous pour voir les commandes associées.",
        "emoji": "🏠"
    },
    "moderation": {
        "title": "🛡️ Modération",
        "desc": "Commandes pour gérer les membres et les salons.\n\n"
                "- `/kick` : Expulser un membre\n"
                "- `/ban` / `/unban` : Bannir ou débannir un membre\n"
                "- `/mute` / `/unmute` : Rendre muet un membre\n"
                "- `/warn` / `/warnings` / `/clearwarnings` : Gérer les avertissements\n"
                "- `/clear` : Effacer des messages\n"
                "- `/slowmode` : Activer le mode lent\n"
                "- `/lock` / `/unlock` : Verrouiller un salon\n"
                "- `/snipe` / `/editsnipe` : Voir les messages supprimés/modifiés",
        "emoji": "🛡️"
    },
    "automod": {
        "title": "🤖 AutoMod & Anti-Raid",
        "desc": "Systèmes de protection automatiques du serveur.\n\n"
                "- `/config` (Puis AutoMod / AntiRaid) : Configurer les systèmes\n"
                "- `/ghostping` : Activer/Désactiver la détection de ghost pings",
        "emoji": "🤖"
    },
    "xp": {
        "title": "📈 Système de Niveaux",
        "desc": "Commandes liées à l'expérience et aux niveaux.\n\n"
                "- `/rank` : Voir son niveau ou celui d'un membre\n"
                "- `/leaderboard` : Afficher le classement du serveur\n"
                "- `/setxp` / `/addxp` / `/resetxp` : Gérer l'XP des membres (Admin)\n"
                "- `/xprole add` / `remove` / `list` : Récompenses de rôles par niveau",
        "emoji": "📈"
    },
    "tickets": {
        "title": "🎟️ Système de Tickets",
        "desc": "Commandes pour le support et les tickets.\n\n"
                "- `/ticket setup` : Créer un panel de tickets (V2)",
        "emoji": "🎟️"
    },
    "roles": {
        "title": "🎭 Rôles & Sanctions",
        "desc": "Gestion avancée des rôles et sanctions automatiques.\n\n"
                "- `/rr setup` / `/rr add` / `/rr remove` : Reaction Roles (Boutons)\n"
                "- `/autosanction add` / `remove` / `list` : Sanctions automatiques selon les warns",
        "emoji": "🎭"
    },
    "community": {
        "title": "🎁 Communauté & Vocaux",
        "desc": "Outils d'interaction pour la communauté.\n\n"
                "- `/tempvoice` : Créer un panel de vocaux temporaires\n"
                "- `/giveaway start` / `reroll` / `end` / `list` : Gérer les giveaways\n"
                "- `/starboard` : Configurer le starboard\n"
                "- `/afk set` : Se mettre en mode AFK",
        "emoji": "🎁"
    },
    "config": {
        "title": "⚙️ Configuration & Infos",
        "desc": "Paramétrage global et commandes d'informations.\n\n"
                "- `/config` : Ouvrir le panel V2 (Logs, Bienvenue, Auto-Rôle, etc.)\n"
                "- `/embed create` / `edit` / `button` : Créateur d'embeds interactifs\n"
                "- `/cmdperm` : Restreindre certaines commandes\n"
                "- `/userinfo` / `/serverinfo` / `/botinfo` / `/avatar` / `/roleinfo` : Informations utiles",
        "emoji": "⚙️"
    }
}

class HelpCategorySelect(discord.ui.Select):
    def __init__(self, current_page: str):
        options = [
            discord.SelectOption(
                label=data["title"].split(" ", 1)[1] if " " in data["title"] else data["title"],
                value=key,
                emoji=data["emoji"],
                default=(key == current_page)
            ) for key, data in HELP_CATEGORIES.items()
        ]
        super().__init__(placeholder="Choisissez une catégorie d'aide...", options=options)

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_page(interaction, self.values[0])

class HelpViewV2(discord.ui.LayoutView):
    def __init__(self, default_page="home"):
        super().__init__(timeout=300)
        self.current_page = default_page

    async def show_page(self, interaction: discord.Interaction, page_key: str):
        self.current_page = page_key
        self.clear_items()
        
        cont = discord.ui.Container(accent_color=Colors.INFO.value)
        
        # Build Section
        data = HELP_CATEGORIES.get(page_key, HELP_CATEGORIES["home"])
        cont.add_item(discord.ui.TextDisplay(f"# {data['title']}\n{data['desc']}"))
        
        cont.add_item(discord.ui.ActionRow(HelpCategorySelect(page_key)))
        
        row2 = discord.ui.ActionRow(
            discord.ui.Button(label="Serveur Support", url="https://discord.gg/support", emoji="🛠️", style=discord.ButtonStyle.link),
            discord.ui.Button(label="Inviter le Bot", url="https://discord.com/api/oauth2/authorize?client_id=123456789&permissions=8&scope=bot%20applications.commands", emoji="🔗", style=discord.ButtonStyle.link)
        )
        cont.add_item(row2)
        
        self.add_item(cont)
        
        if interaction.response.is_done():
            await interaction.edit_original_response(view=self, embed=None)
        else:
            await interaction.response.edit_message(view=self, embed=None)

    async def send_initial(self, interaction: discord.Interaction):
        self.clear_items()
        
        cont = discord.ui.Container(accent_color=Colors.INFO.value)
        data = HELP_CATEGORIES.get(self.current_page, HELP_CATEGORIES["home"])
        cont.add_item(discord.ui.TextDisplay(f"# {data['title']}\n{data['desc']}"))
        cont.add_item(discord.ui.ActionRow(HelpCategorySelect(self.current_page)))
        
        row2 = discord.ui.ActionRow(
            discord.ui.Button(label="Serveur Support", url="https://discord.gg/support", emoji="🛠️", style=discord.ButtonStyle.link),
            discord.ui.Button(label="Inviter le Bot", url="https://discord.com/api/oauth2/authorize?client_id=123456789&permissions=8&scope=bot%20applications.commands", emoji="🔗", style=discord.ButtonStyle.link)
        )
        cont.add_item(row2)
        
        self.add_item(cont)
        
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
        # Pour faire correspondre la commande à une page, on garde un petit mapping simple
        cmd_map = {
            "kick": "moderation", "ban": "moderation", "warn": "moderation", "mute": "moderation", "clear": "moderation", "slowmode": "moderation", "lock": "moderation",
            "snipe": "moderation", "editsnipe": "moderation",
            "automod": "automod", "antiraid": "automod", "ghostping": "automod",
            "rank": "xp", "leaderboard": "xp", "setxp": "xp", "xprole": "xp",
            "ticket": "tickets",
            "rr": "roles", "autosanction": "roles",
            "tempvoice": "community", "giveaway": "community", "starboard": "community", "afk": "community",
            "config": "config", "embed": "config", "cmdperm": "config", "userinfo": "config", "serverinfo": "config"
        }
        
        page = "home"
        if commande:
            base_cmd = commande.split()[0].lower()
            page = cmd_map.get(base_cmd, "home")
            
        view = HelpViewV2(default_page=page)
        await view.send_initial(interaction)


async def setup(bot: commands.Bot):
    await bot.add_cog(Info(bot))
