import discord
from discord.ext import commands


class WelcomeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="👤 Mon profil", style=discord.ButtonStyle.secondary)
    async def show_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        account_age = (discord.utils.utcnow() - member.created_at).days
        embed = discord.Embed(
            title=f"👤 {member.display_name}",
            color=member.color if member.color != discord.Color.default() else discord.Color.blurple(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="📅 Compte créé",  value=f"il y a **{account_age}** jours",                    inline=True)
        embed.add_field(name="📥 A rejoint le", value=discord.utils.format_dt(member.joined_at, 'D'),        inline=True)
        roles = [r.mention for r in reversed(member.roles) if r != interaction.guild.default_role]
        if roles:
            embed.add_field(name=f"🎭 Rôles ({len(roles)})", value=" ".join(roles[:10]), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _format_message(self, template: str, member: discord.Member) -> str:
        return (
            template
            .replace("{mention}", member.mention)
            .replace("{name}", str(member))
            .replace("{username}", member.name)
            .replace("{server}", member.guild.name)
            .replace("{count}", str(member.guild.member_count))
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        settings = await self.bot.db.get_guild_settings(member.guild.id)

        # Auto-role
        autorole_id = settings.get("autorole_id")
        if autorole_id:
            role = member.guild.get_role(autorole_id)
            if role and member.guild.me.guild_permissions.manage_roles and role < member.guild.me.top_role:
                try:
                    await member.add_roles(role, reason="Rôle automatique à l'arrivée")
                except discord.Forbidden:
                    pass

        # Welcome message
        welcome_channel_id = settings.get("welcome_channel_id")
        if not welcome_channel_id:
            return
        channel = member.guild.get_channel(welcome_channel_id)
        if not channel or not channel.permissions_for(member.guild.me).send_messages:
            return

        template = settings.get("welcome_message") or "Bienvenue {mention} sur **{server}** !"
        message  = self._format_message(template, member)

        account_age = (discord.utils.utcnow() - member.created_at).days

        embed = discord.Embed(
            title=f"👋 Bienvenue sur {member.guild.name} !",
            description=message,
            color=0x57F287,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=member.display_avatar.url)

        if member.guild.icon:
            embed.set_footer(
                text=f"Membre #{member.guild.member_count}  •  Compte créé il y a {account_age} jours",
                icon_url=member.guild.icon.url,
            )
        else:
            embed.set_footer(
                text=f"Membre #{member.guild.member_count}  •  Compte créé il y a {account_age} jours"
            )

        embed.add_field(
            name="📅 Compte créé le",
            value=discord.utils.format_dt(member.created_at, 'D'),
            inline=True,
        )
        embed.add_field(
            name="👥 Membres",
            value=str(member.guild.member_count),
            inline=True,
        )

        await channel.send(embed=embed, view=WelcomeView())

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        settings = await self.bot.db.get_guild_settings(member.guild.id)
        goodbye_channel_id = settings.get("goodbye_channel_id")
        if not goodbye_channel_id:
            return
        channel = member.guild.get_channel(goodbye_channel_id)
        if not channel or not channel.permissions_for(member.guild.me).send_messages:
            return

        template = settings.get("goodbye_message") or "Au revoir **{name}**, bonne continuation !"
        message  = self._format_message(template, member)

        embed = discord.Embed(
            title="👋 Départ d'un membre",
            description=message,
            color=0xED4245,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=member.display_avatar.url)

        if member.guild.icon:
            embed.set_footer(
                text=f"Il reste {member.guild.member_count} membres",
                icon_url=member.guild.icon.url,
            )
        else:
            embed.set_footer(text=f"Il reste {member.guild.member_count} membres")

        await channel.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
