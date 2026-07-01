import discord
from discord import app_commands
from discord.ext import commands
from utils.embeds import error_embed
from utils.i18n import t

DEFAULT_MSG = "🚀 {mention} vient de booster **{server}** ! Merci infiniment ! 🎉"


class BoostView(discord.ui.View):
    def __init__(self, booster_id: int, lang: str):
        super().__init__(timeout=None)
        self.booster_id = booster_id
        self.lang = lang
        self.children[0].label = t(lang, "boost.thank_you_btn")

    @discord.ui.button(label="💜 Merci !", style=discord.ButtonStyle.secondary)
    async def thank_you(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang    = await interaction.client.db.get_guild_lang(interaction.guild_id)
        booster = interaction.guild.get_member(self.booster_id)
        name    = booster.display_name if booster else t(lang, "boost.this_member")
        await interaction.response.send_message(
            t(lang, "boost.thanks_msg", user=interaction.user.mention, name=name),
            allowed_mentions=discord.AllowedMentions(users=False),
        )


def _fmt(text: str, member: discord.Member) -> str:
    return (text
        .replace("{mention}", member.mention)
        .replace("{user}",    member.display_name)
        .replace("{username}", str(member))
        .replace("{server}",  member.guild.name)
        .replace("{count}",   str(member.guild.premium_subscription_count))
    )


class Boost(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.premium_since == after.premium_since:
            return

        config = await self.bot.db.get_boost_config(after.guild.id)

        if before.premium_since is None and after.premium_since is not None:
            # Nouveau boost — donner le rôle
            if role_id := config.get("reward_role_id"):
                role = after.guild.get_role(role_id)
                if role:
                    try:
                        await after.add_roles(role, reason="Server boost")
                    except discord.Forbidden:
                        pass

            # Envoyer le message
            if ch_id := config.get("channel_id"):
                ch = after.guild.get_channel(ch_id)
                if ch:
                    lang = await self.bot.db.get_guild_lang(after.guild.id)
                    msg = config.get("message") or DEFAULT_MSG
                    embed = discord.Embed(
                        description=_fmt(msg, after),
                        color=discord.Color.from_str("#f47fff")
                    )
                    embed.set_thumbnail(url=after.display_avatar.url)
                    embed.set_footer(text=t(lang, "boost.footer", count=after.guild.premium_subscription_count))
                    try:
                        await ch.send(embed=embed, view=BoostView(after.id, lang))
                    except discord.Forbidden:
                        pass

        elif before.premium_since is not None and after.premium_since is None:
            # Fin du boost — retirer le rôle
            if role_id := config.get("reward_role_id"):
                role = after.guild.get_role(role_id)
                if role and role in after.roles:
                    try:
                        await after.remove_roles(role, reason="Boost terminé")
                    except discord.Forbidden:
                        pass

    # ── Commands ──────────────────────────────────────────────────────────────

    boost_group = app_commands.Group(name="boost", description="Récompenses pour les boosters du serveur")

    @boost_group.command(name="setup", description="Configure le rôle et le salon des boosts")
    @app_commands.describe(role="Rôle donné aux boosters", salon="Salon d'annonce des boosts")
    @app_commands.default_permissions(manage_guild=True)
    async def boost_setup(self, interaction: discord.Interaction, role: discord.Role, salon: discord.TextChannel):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(embed=error_embed(t(lang, "boost.role_too_high")), ephemeral=True)
        db  = self.bot.db
        gid = interaction.guild.id
        await db.update_boost_config(gid, "reward_role_id", role.id)
        await db.update_boost_config(gid, "channel_id",     salon.id)
        embed = discord.Embed(title=t(lang, "boost.setup_success_title"), color=discord.Color.from_str("#f47fff"))
        embed.add_field(name=t(lang, "boost.role_field"),    value=role.mention,  inline=True)
        embed.add_field(name=t(lang, "boost.channel_field"), value=salon.mention, inline=True)
        embed.set_footer(text=t(lang, "boost.setup_footer"))
        await interaction.response.send_message(embed=embed)

    @boost_group.command(name="message", description="Personnalise le message de boost")
    @app_commands.describe(texte="Variables dispo : {mention} {user} {server} {count}")
    @app_commands.default_permissions(manage_guild=True)
    async def boost_message(self, interaction: discord.Interaction, texte: str):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        await self.bot.db.update_boost_config(interaction.guild.id, "message", texte)
        await interaction.response.send_message(
            t(lang, "boost.message_updated", text=texte), ephemeral=True
        )

    @boost_group.command(name="status", description="Affiche la configuration des boost rewards")
    @app_commands.default_permissions(manage_guild=True)
    async def boost_status(self, interaction: discord.Interaction):
        lang    = await self.bot.db.get_guild_lang(interaction.guild_id)
        config  = await self.bot.db.get_boost_config(interaction.guild.id)
        role    = interaction.guild.get_role(config.get("reward_role_id") or 0)
        channel = interaction.guild.get_channel(config.get("channel_id")  or 0)
        embed   = discord.Embed(title=t(lang, "boost.status_title"), color=discord.Color.from_str("#f47fff"))
        embed.add_field(name=t(lang, "boost.role_field"),    value=role.mention    if role    else t(lang, "boost.not_configured"), inline=True)
        embed.add_field(name=t(lang, "boost.channel_field"), value=channel.mention if channel else t(lang, "boost.not_configured"), inline=True)
        embed.add_field(name=t(lang, "boost.current_count_field"), value=str(interaction.guild.premium_subscription_count),  inline=True)
        embed.add_field(name=t(lang, "boost.message_field"), value=config.get("message") or DEFAULT_MSG,              inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Boost(bot))
