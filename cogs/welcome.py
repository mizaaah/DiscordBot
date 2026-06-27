import discord
from discord.ext import commands


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
        if welcome_channel_id:
            channel = member.guild.get_channel(welcome_channel_id)
            if channel and channel.permissions_for(member.guild.me).send_messages:
                template = settings.get("welcome_message") or "Bienvenue {mention} sur **{server}** !"
                message = self._format_message(template, member)

                embed = discord.Embed(
                    description=message,
                    color=discord.Color.green()
                )
                embed.set_author(name=str(member), icon_url=member.display_avatar.url)
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.add_field(name="Membre #", value=str(member.guild.member_count), inline=True)
                embed.add_field(name="Compte créé", value=discord.utils.format_dt(member.created_at, 'R'), inline=True)
                await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        settings = await self.bot.db.get_guild_settings(member.guild.id)
        goodbye_channel_id = settings.get("goodbye_channel_id")
        if not goodbye_channel_id:
            return
        channel = member.guild.get_channel(goodbye_channel_id)
        if channel and channel.permissions_for(member.guild.me).send_messages:
            template = settings.get("goodbye_message") or "Au revoir **{name}**, bonne continuation !"
            message = self._format_message(template, member)

            embed = discord.Embed(
                description=message,
                color=discord.Color.red()
            )
            embed.set_author(name=str(member), icon_url=member.display_avatar.url)
            embed.set_thumbnail(url=member.display_avatar.url)
            await channel.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
