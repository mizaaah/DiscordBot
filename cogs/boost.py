import discord
from discord import app_commands
from discord.ext import commands
from utils.embeds import error_embed

DEFAULT_MSG = "🚀 {mention} vient de booster **{server}** ! Merci infiniment ! 🎉"


class BoostView(discord.ui.View):
    def __init__(self, booster_id: int):
        super().__init__(timeout=None)
        self.booster_id = booster_id

    @discord.ui.button(label="💜 Merci !", style=discord.ButtonStyle.secondary)
    async def thank_you(self, interaction: discord.Interaction, button: discord.ui.Button):
        booster = interaction.guild.get_member(self.booster_id)
        name    = booster.display_name if booster else "ce membre"
        await interaction.response.send_message(
            f"💜 {interaction.user.mention} remercie **{name}** pour son boost !",
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
                    msg = config.get("message") or DEFAULT_MSG
                    embed = discord.Embed(
                        description=_fmt(msg, after),
                        color=discord.Color.from_str("#f47fff")
                    )
                    embed.set_thumbnail(url=after.display_avatar.url)
                    embed.set_footer(text=f"Le serveur a maintenant {after.guild.premium_subscription_count} boost(s)")
                    try:
                        await ch.send(embed=embed, view=BoostView(after.id))
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
        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(embed=error_embed("❌ Ce rôle est au-dessus du mien."), ephemeral=True)
        db  = self.bot.db
        gid = interaction.guild.id
        await db.update_boost_config(gid, "reward_role_id", role.id)
        await db.update_boost_config(gid, "channel_id",     salon.id)
        embed = discord.Embed(title="✅ Boost rewards configuré", color=discord.Color.from_str("#f47fff"))
        embed.add_field(name="🎁 Rôle boost", value=role.mention,  inline=True)
        embed.add_field(name="📢 Salon",       value=salon.mention, inline=True)
        embed.set_footer(text="Utilise /boost message pour personnaliser le message.")
        await interaction.response.send_message(embed=embed)

    @boost_group.command(name="message", description="Personnalise le message de boost")
    @app_commands.describe(texte="Variables dispo : {mention} {user} {server} {count}")
    @app_commands.default_permissions(manage_guild=True)
    async def boost_message(self, interaction: discord.Interaction, texte: str):
        await self.bot.db.update_boost_config(interaction.guild.id, "message", texte)
        await interaction.response.send_message(
            f"✅ Message de boost mis à jour :\n> {texte}", ephemeral=True
        )

    @boost_group.command(name="status", description="Affiche la configuration des boost rewards")
    @app_commands.default_permissions(manage_guild=True)
    async def boost_status(self, interaction: discord.Interaction):
        config  = await self.bot.db.get_boost_config(interaction.guild.id)
        role    = interaction.guild.get_role(config.get("reward_role_id") or 0)
        channel = interaction.guild.get_channel(config.get("channel_id")  or 0)
        embed   = discord.Embed(title="💜 Boost Rewards", color=discord.Color.from_str("#f47fff"))
        embed.add_field(name="🎁 Rôle",           value=role.mention    if role    else "❌ Non configuré", inline=True)
        embed.add_field(name="📢 Salon",           value=channel.mention if channel else "❌ Non configuré", inline=True)
        embed.add_field(name="🔢 Boosts actuels", value=str(interaction.guild.premium_subscription_count),  inline=True)
        embed.add_field(name="💬 Message",         value=config.get("message") or DEFAULT_MSG,              inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Boost(bot))
