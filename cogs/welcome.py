import discord
from discord.ext import commands
from utils.i18n import t


class WelcomeView(discord.ui.View):
    def __init__(self, lang: str = "fr"):
        super().__init__(timeout=None)
        self.lang = lang
        self.children[0].label = t(lang, "welcome.profile_btn")

    @discord.ui.button(label="👤 Mon profil", style=discord.ButtonStyle.secondary, custom_id="welcome_profile_persistent")
    async def show_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang   = await interaction.client.db.get_guild_lang(interaction.guild_id)
        member = interaction.user
        age    = (discord.utils.utcnow() - member.created_at).days
        color  = member.color if member.color != discord.Color.default() else discord.Color.blurple()
        embed  = discord.Embed(title=t(lang, "welcome.profile_title", member=member.display_name), color=color)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name=t(lang, "welcome.account_created"), value=t(lang, "welcome.account_age", days=age),              inline=True)
        embed.add_field(name=t(lang, "welcome.joined_at"),        value=discord.utils.format_dt(member.joined_at, 'D'),        inline=True)
        roles = [r.mention for r in reversed(member.roles) if r != interaction.guild.default_role]
        if roles:
            embed.add_field(name=t(lang, "welcome.roles", count=len(roles)), value=" ".join(roles[:10]), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(WelcomeView())

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
        lang     = settings.get("language") or "fr"

        autorole_id = settings.get("autorole_id")
        if autorole_id:
            role = member.guild.get_role(autorole_id)
            if role and member.guild.me.guild_permissions.manage_roles and role < member.guild.me.top_role:
                try:
                    await member.add_roles(role, reason="Rôle automatique à l'arrivée")
                except discord.Forbidden:
                    pass

        welcome_channel_id = settings.get("welcome_channel_id")
        if not welcome_channel_id:
            return
        channel = member.guild.get_channel(welcome_channel_id)
        if not channel or not channel.permissions_for(member.guild.me).send_messages:
            return

        template = settings.get("welcome_message") or t(lang, "welcome.join_default")
        message  = self._format_message(template, member)
        age      = (discord.utils.utcnow() - member.created_at).days

        embed = discord.Embed(
            title=t(lang, "welcome.join_title", server=member.guild.name),
            description=message,
            color=0x57F287,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=member.display_avatar.url)
        footer_text = t(lang, "welcome.footer_join", count=member.guild.member_count, days=age)
        embed.set_footer(text=footer_text, icon_url=member.guild.icon.url if member.guild.icon else None)
        embed.add_field(name=t(lang, "welcome.account_created_field"), value=discord.utils.format_dt(member.created_at, 'D'), inline=True)
        embed.add_field(name=t(lang, "welcome.members_field"),         value=str(member.guild.member_count),                  inline=True)

        await channel.send(embed=embed, view=WelcomeView(lang))

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        settings = await self.bot.db.get_guild_settings(member.guild.id)
        lang     = settings.get("language") or "fr"

        goodbye_channel_id = settings.get("goodbye_channel_id")
        if not goodbye_channel_id:
            return
        channel = member.guild.get_channel(goodbye_channel_id)
        if not channel or not channel.permissions_for(member.guild.me).send_messages:
            return

        template = settings.get("goodbye_message") or t(lang, "welcome.leave_default")
        message  = self._format_message(template, member)

        embed = discord.Embed(
            title=t(lang, "welcome.leave_title"),
            description=message,
            color=0xED4245,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=member.display_avatar.url)
        footer_text = t(lang, "welcome.footer_leave", count=member.guild.member_count)
        embed.set_footer(text=footer_text, icon_url=member.guild.icon.url if member.guild.icon else None)

        await channel.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
