import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from utils.colors import Colors
from utils.i18n import t


# ══════════════════════════════════════════════════════════════════════════════
#  Help data
# ══════════════════════════════════════════════════════════════════════════════

# Order of pages, and for each: how many (name, value, inline) fields it has.
HELP_PAGE_ORDER = [
    "home", "moderation", "automod", "xp", "tickets", "roles", "vocal",
    "embeds", "giveaways", "starboard_afk", "community", "permissions", "config",
]

HELP_PAGE_FIELDS = {
    "home":          [True] * 12,
    "moderation":    [False, False, False, False],
    "automod":       [False, False, False],
    "xp":            [False, False, False],
    "tickets":       [False, False],
    "roles":         [False, False],
    "vocal":         [False, False],
    "embeds":        [False],
    "giveaways":     [False],
    "starboard_afk": [False, False],
    "community":     [False, False],
    "permissions":   [False, False],
    "config":        [False, False],
}

# Maps a top-level command/group name to the help page it's documented on,
# used by /help commande:<autocomplete> to jump straight to the right page.
COMMAND_PAGE_MAP = {
    "kick": "moderation", "ban": "moderation", "unban": "moderation", "mute": "moderation",
    "unmute": "moderation", "warn": "moderation", "unwarn": "moderation", "warnings": "moderation",
    "clearwarnings": "moderation", "history": "moderation", "clear": "moderation",
    "slowmode": "moderation", "lock": "moderation", "unlock": "moderation",
    "automod": "automod", "antiraid": "automod", "ghostping": "automod",
    "rank": "xp", "leaderboard": "xp", "setxp": "xp", "addxp": "xp", "resetxp": "xp", "xprole": "xp",
    "ticket": "tickets", "tadd": "tickets", "tremove": "tickets", "tclaim": "tickets", "tunclaim": "tickets",
    "rr": "roles", "autosanction": "roles",
    "tempvoice": "vocal",
    "embed": "embeds",
    "giveaway": "giveaways",
    "starboard": "starboard_afk", "afk": "starboard_afk",
    "boost": "community", "report": "community", "setreport": "community",
    "cmdperm": "permissions",
    "setup": "config", "config": "config", "setlanguage": "config", "setlogs": "config",
    "setwelcome": "config", "setgoodbye": "config", "setautorole": "config",
    "userinfo": "config", "serverinfo": "config", "botinfo": "config", "avatar": "config", "roleinfo": "config",
}


def _build_help_pages(lang: str) -> dict:
    pages = {}
    for key in HELP_PAGE_ORDER:
        inlines = HELP_PAGE_FIELDS[key]
        fields = [
            (t(lang, f"help.{key}.f{i+1}.name"), t(lang, f"help.{key}.f{i+1}.value"), inline)
            for i, inline in enumerate(inlines)
        ]
        pages[key] = {
            "label": t(lang, f"help.{key}.label"),
            "color": HELP_PAGE_COLORS[key],
            "title": t(lang, f"help.{key}.title"),
            "description": t(lang, f"help.{key}.desc"),
            "fields": fields,
        }
    return pages


HELP_PAGE_COLORS = {
    "home":          0x5865F2,
    "moderation":    0xED4245,
    "giveaways":     0xFFD700,
    "starboard_afk": 0xFFD700,
    "automod":       0xFF6B35,
    "xp":            0xFFD700,
    "tickets":       0x00B0F4,
    "roles":         0xEB459E,
    "vocal":         0x57F287,
    "embeds":        0x9B59B6,
    "community":     0xF47FFF,
    "permissions":   0xFEE75C,
    "config":        0x95A5A6,
}


def _build_help_embed(lang: str, page_key: str, guild: discord.Guild) -> discord.Embed:
    pages = _build_help_pages(lang)
    page = pages.get(page_key, pages["home"])
    embed = discord.Embed(
        title=page["title"],
        description=page.get("description", ""),
        color=page["color"],
    )
    for name, value, inline in page.get("fields", []):
        embed.add_field(name=name, value=value, inline=inline)
    if guild and guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(text=t(lang, "help.footer"), icon_url=guild.icon.url if guild and guild.icon else None)
    return embed


# ══════════════════════════════════════════════════════════════════════════════
#  Help UI
# ══════════════════════════════════════════════════════════════════════════════

class HelpSelect(discord.ui.Select):
    def __init__(self, lang: str, default_page: str = "home"):
        self.lang = lang
        pages = _build_help_pages(lang)
        options = [
            discord.SelectOption(label=data["label"], value=key, default=(key == default_page))
            for key, data in pages.items()
        ]
        super().__init__(
            placeholder=t(lang, "help.select_placeholder"),
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        embed = _build_help_embed(self.lang, self.values[0], interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self, lang: str, default_page: str = "home"):
        super().__init__(timeout=300)
        self.add_item(HelpSelect(lang, default_page))

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

        embed.add_field(name=t(lang, "info.id"),          value=str(member.id),                                    inline=True)
        embed.add_field(name=t(lang, "info.bot"),          value="✅" if member.bot else "❌",                      inline=True)
        embed.add_field(name="​",           value="​",                                         inline=True)
        embed.add_field(name=t(lang, "info.account_created"),  value=discord.utils.format_dt(member.created_at, 'D'),  inline=True)
        embed.add_field(name=t(lang, "info.joined"),     value=discord.utils.format_dt(member.joined_at, 'D'),   inline=True)
        embed.add_field(name="​",           value="​",                                         inline=True)

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
        embed.add_field(name=t(lang, "info.status"), value=status_map.get(member.status, t(lang, "info.status_unknown")), inline=True)
        embed.add_field(name=t(lang, "info.top_role"),   value=member.top_role.mention, inline=True)
        embed.add_field(name=t(lang, "info.key_perms"), value=self._key_perms(lang, member), inline=False)

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

        embed.add_field(name=t(lang, "info.id"),          value=str(guild.id),                                       inline=True)
        embed.add_field(name=t(lang, "info.owner"), value=guild.owner.mention if guild.owner else t(lang, "info.unknown"),   inline=True)
        embed.add_field(name=t(lang, "info.created_on"),      value=discord.utils.format_dt(guild.created_at, 'D'),      inline=True)

        total = guild.member_count
        bots  = sum(1 for m in guild.members if m.bot)
        embed.add_field(name=t(lang, "info.members"),  value=t(lang, "info.members_value", total=total, humans=total - bots, bots=bots),  inline=True)
        embed.add_field(name=t(lang, "info.channels"),   value=t(lang, "info.channels_value", text=len(guild.text_channels), voice=len(guild.voice_channels)), inline=True)
        embed.add_field(name=t(lang, "info.roles"),    value=str(len(guild.roles)),                                   inline=True)
        embed.add_field(name=t(lang, "info.emojis"),   value=f"{len(guild.emojis)}/{guild.emoji_limit}",              inline=True)
        embed.add_field(name=t(lang, "info.boosts"),   value=t(lang, "info.boosts_value", count=guild.premium_subscription_count, tier=guild.premium_tier), inline=True)

        level_map = {
            discord.VerificationLevel.none:    t(lang, "info.verif_none"),
            discord.VerificationLevel.low:     t(lang, "info.verif_low"),
            discord.VerificationLevel.medium:  t(lang, "info.verif_medium"),
            discord.VerificationLevel.high:    t(lang, "info.verif_high"),
            discord.VerificationLevel.highest: t(lang, "info.verif_highest"),
        }
        embed.add_field(name=t(lang, "info.verification"), value=level_map.get(guild.verification_level, t(lang, "info.unknown")), inline=True)
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
        embed.add_field(name=t(lang, "info.id"),               value=str(bot.user.id),                        inline=True)
        embed.add_field(name=t(lang, "info.servers"),          value=str(len(bot.guilds)),                    inline=True)
        embed.add_field(name=t(lang, "info.total_members"),    value=str(sum(g.member_count for g in bot.guilds)), inline=True)
        embed.add_field(name=t(lang, "info.latency"),           value=f"{round(bot.latency * 1000)} ms",       inline=True)
        embed.add_field(name=t(lang, "info.discordpy"),        value=discord.__version__,                     inline=True)
        embed.add_field(name=t(lang, "info.commands"),         value=str(len(bot.tree.get_commands())),        inline=True)
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
        embed.add_field(name=t(lang, "info.id"),              value=str(role.id),          inline=True)
        embed.add_field(name=t(lang, "info.color"),          value=str(role.color),       inline=True)
        embed.add_field(name=t(lang, "info.position"),         value=str(role.position),    inline=True)
        embed.add_field(name=t(lang, "info.mentionable"),     value="✅" if role.mentionable else "❌", inline=True)
        embed.add_field(name=t(lang, "info.hoisted"),   value="✅" if role.hoist     else "❌", inline=True)
        embed.add_field(name=t(lang, "info.managed"),     value="✅" if role.managed   else "❌", inline=True)
        embed.add_field(name=t(lang, "info.members"),           value=str(len(role.members)), inline=True)
        embed.add_field(name=t(lang, "info.created_on"),           value=discord.utils.format_dt(role.created_at, 'D'), inline=True)
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

    @app_commands.command(name="help", description="Affiche l'aide avec toutes les commandes")
    @app_commands.describe(commande="Aller directement à la section d'une commande précise (optionnel)")
    @app_commands.autocomplete(commande=_cmd_autocomplete)
    async def help(self, interaction: discord.Interaction, commande: str = None):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        page = "home"
        if commande:
            page = COMMAND_PAGE_MAP.get(commande.split()[0].lower(), "home")
        embed = _build_help_embed(lang, page, interaction.guild)
        view  = HelpView(lang, page)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Info(bot))
