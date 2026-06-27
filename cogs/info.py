import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone


class Info(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /userinfo ─────────────────────────────────────────────────────────────

    @app_commands.command(name="userinfo", description="Affiche les informations d'un membre")
    @app_commands.describe(membre="Le membre dont voir les infos (toi-même si vide)")
    async def userinfo(self, interaction: discord.Interaction, membre: discord.Member = None):
        member = membre or interaction.user
        embed = discord.Embed(
            title=f"Informations sur {member}",
            color=member.color if member.color != discord.Color.default() else discord.Color.blurple()
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(name="Nom complet", value=str(member), inline=True)
        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.add_field(name="Bot", value="✅" if member.bot else "❌", inline=True)
        embed.add_field(name="Compte créé", value=discord.utils.format_dt(member.created_at, 'D'), inline=True)
        embed.add_field(name="A rejoint", value=discord.utils.format_dt(member.joined_at, 'D'), inline=True)

        if member.is_timed_out():
            embed.add_field(name="Muté jusqu'à", value=discord.utils.format_dt(member.communication_disabled_until, 'R'), inline=True)

        status_map = {
            discord.Status.online: "🟢 En ligne",
            discord.Status.idle: "🟡 Absent",
            discord.Status.dnd: "🔴 Ne pas déranger",
            discord.Status.offline: "⚫ Hors ligne"
        }
        embed.add_field(name="Statut", value=status_map.get(member.status, "Inconnu"), inline=True)

        roles = [r.mention for r in reversed(member.roles) if r != interaction.guild.default_role]
        if roles:
            roles_str = " ".join(roles[:15])
            if len(roles) > 15:
                roles_str += f" +{len(roles) - 15} autres"
            embed.add_field(name=f"Rôles ({len(roles)})", value=roles_str, inline=False)

        embed.add_field(name="Rôle le plus haut", value=member.top_role.mention, inline=True)
        embed.add_field(name="Permissions clés", value=self._key_perms(member), inline=False)
        await interaction.response.send_message(embed=embed)

    def _key_perms(self, member: discord.Member) -> str:
        perms = member.guild_permissions
        checks = {
            "Administrateur": perms.administrator,
            "Gérer le serveur": perms.manage_guild,
            "Gérer les membres": perms.manage_guild,
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
            title=guild.name,
            color=discord.Color.blurple()
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        if guild.banner:
            embed.set_image(url=guild.banner.url)

        embed.add_field(name="ID", value=str(guild.id), inline=True)
        embed.add_field(name="Propriétaire", value=guild.owner.mention if guild.owner else "Inconnu", inline=True)
        embed.add_field(name="Créé le", value=discord.utils.format_dt(guild.created_at, 'D'), inline=True)

        total = guild.member_count
        bots = sum(1 for m in guild.members if m.bot)
        embed.add_field(name="Membres", value=f"{total} ({total - bots} humains, {bots} bots)", inline=True)

        text_ch = len(guild.text_channels)
        voice_ch = len(guild.voice_channels)
        cat = len(guild.categories)
        embed.add_field(name="Salons", value=f"{text_ch} texte | {voice_ch} vocal | {cat} catégories", inline=True)
        embed.add_field(name="Rôles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Emojis", value=f"{len(guild.emojis)}/{guild.emoji_limit}", inline=True)

        level_map = {
            discord.VerificationLevel.none: "Aucune",
            discord.VerificationLevel.low: "Faible",
            discord.VerificationLevel.medium: "Moyenne",
            discord.VerificationLevel.high: "Élevée",
            discord.VerificationLevel.highest: "Très élevée"
        }
        embed.add_field(name="Vérification", value=level_map.get(guild.verification_level, "Inconnue"), inline=True)
        embed.add_field(name="Boosts", value=f"{guild.premium_subscription_count} (Niveau {guild.premium_tier})", inline=True)
        await interaction.response.send_message(embed=embed)

    # ── /botinfo ──────────────────────────────────────────────────────────────

    @app_commands.command(name="botinfo", description="Affiche les informations du bot")
    async def botinfo(self, interaction: discord.Interaction):
        bot = self.bot
        embed = discord.Embed(
            title=f"Informations sur {bot.user.name}",
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=bot.user.display_avatar.url)
        embed.add_field(name="ID", value=str(bot.user.id), inline=True)
        embed.add_field(name="Serveurs", value=str(len(bot.guilds)), inline=True)
        embed.add_field(name="Membres", value=str(sum(g.member_count for g in bot.guilds)), inline=True)
        embed.add_field(name="Latence", value=f"{round(bot.latency * 1000)} ms", inline=True)
        embed.add_field(name="Version discord.py", value=discord.__version__, inline=True)
        embed.add_field(name="Commandes", value=str(len(bot.tree.get_commands())), inline=True)
        await interaction.response.send_message(embed=embed)

    # ── /avatar ───────────────────────────────────────────────────────────────

    @app_commands.command(name="avatar", description="Affiche l'avatar d'un membre")
    @app_commands.describe(membre="Le membre dont voir l'avatar (toi-même si vide)")
    async def avatar(self, interaction: discord.Interaction, membre: discord.Member = None):
        member = membre or interaction.user
        embed = discord.Embed(
            title=f"Avatar de {member.display_name}",
            color=discord.Color.blurple()
        )
        embed.set_image(url=member.display_avatar.url)
        embed.add_field(
            name="Liens",
            value=f"[PNG]({member.display_avatar.with_format('png').url}) | "
                  f"[JPG]({member.display_avatar.with_format('jpg').url}) | "
                  f"[WebP]({member.display_avatar.with_format('webp').url})"
        )
        await interaction.response.send_message(embed=embed)

    # ── /roleinfo ─────────────────────────────────────────────────────────────

    @app_commands.command(name="roleinfo", description="Affiche les informations d'un rôle")
    @app_commands.describe(role="Le rôle dont voir les infos")
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role):
        embed = discord.Embed(
            title=f"Informations sur @{role.name}",
            color=role.color
        )
        embed.add_field(name="ID", value=str(role.id), inline=True)
        embed.add_field(name="Couleur", value=str(role.color), inline=True)
        embed.add_field(name="Position", value=str(role.position), inline=True)
        embed.add_field(name="Mentionnable", value="✅" if role.mentionable else "❌", inline=True)
        embed.add_field(name="Affiché séparément", value="✅" if role.hoist else "❌", inline=True)
        embed.add_field(name="Géré par Discord", value="✅" if role.managed else "❌", inline=True)
        embed.add_field(name="Membres", value=str(len(role.members)), inline=True)
        embed.add_field(name="Créé le", value=discord.utils.format_dt(role.created_at, 'D'), inline=True)
        await interaction.response.send_message(embed=embed)

    # ── /help ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="help", description="Liste toutes les commandes disponibles")
    async def help(self, interaction: discord.Interaction):
        e = discord.Embed(
            title="📋 Commandes du bot",
            description="Toutes les commandes utilisent les slash commands (`/`).",
            color=discord.Color.blurple()
        )
        e.add_field(
            name="🛡️ Modération",
            value=(
                "`/kick` `/ban` `/unban` `/mute` `/unmute`\n"
                "`/warn` `/unwarn` `/warnings` `/clearwarnings`\n"
                "`/clear [membre] [bots] [images] [contient]` `/slowmode` `/lock` `/unlock`"
            ),
            inline=False
        )
        e.add_field(
            name="🤖 Auto-sanctions",
            value="`/autosanction add` `/autosanction remove` `/autosanction list`",
            inline=False
        )
        e.add_field(
            name="🚨 Signalements",
            value="`/report @user raison` `/setreport #salon`",
            inline=False
        )
        e.add_field(
            name="🔇 AutoMod",
            value=(
                "`/automod status` `/automod toggle` `/automod spam` `/automod flood`\n"
                "`/automod invites` `/automod caps` `/automod mentions` `/automod bypass`\n"
                "`/ghostping true/false`"
            ),
            inline=False
        )
        e.add_field(
            name="🛡️ Anti-Raid",
            value="`/antiraid status` `/antiraid toggle` `/antiraid config` `/antiraid lockdown` `/antiraid unlock`",
            inline=False
        )
        e.add_field(
            name="⭐ Système XP",
            value=(
                "`/rank` `/leaderboard` `/setxp` `/addxp` `/resetxp`\n"
                "`/xprole add` `/xprole remove` `/xprole list`"
            ),
            inline=False
        )
        e.add_field(
            name="🎫 Tickets",
            value="`/ticket setup` `/ticket categories` `/ticket couleur` `/ticket message`\n`/tadd` `/tremove` `/tclaim` `/tunclaim`",
            inline=False
        )
        e.add_field(
            name="🎭 Rôles réactifs",
            value="`/rr create` `/rr add` `/rr remove` `/rr delete` `/rr list`",
            inline=False
        )
        e.add_field(
            name="🎙️ Salons vocaux temporaires",
            value="`/tempvoice setup` `/tempvoice config` `/tempvoice status`",
            inline=False
        )
        e.add_field(
            name="🖼️ Constructeur d'embeds",
            value="`/embed create` `/embed edit`",
            inline=False
        )
        e.add_field(
            name="💜 Boost Rewards",
            value="`/boost setup` `/boost message` `/boost status`",
            inline=False
        )
        e.add_field(
            name="🔐 Permissions commandes",
            value="`/cmdperm allow-role` `/cmdperm deny-role` `/cmdperm channel` `/cmdperm reset` `/cmdperm list`",
            inline=False
        )
        e.add_field(
            name="ℹ️ Informations",
            value="`/userinfo` `/serverinfo` `/botinfo` `/avatar` `/roleinfo`",
            inline=False
        )
        e.add_field(
            name="⚙️ Configuration",
            value="`/config` `/setlogs` `/setwelcome` `/setgoodbye` `/setautorole` `/setreport`",
            inline=False
        )
        e.set_footer(text="Utilise /config pour configurer le bot • Les admins sont exemptés des restrictions /cmdperm")
        await interaction.response.send_message(embed=e)


async def setup(bot: commands.Bot):
    await bot.add_cog(Info(bot))
