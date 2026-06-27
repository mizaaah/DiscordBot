import discord
from discord import app_commands
from discord.ext import commands


class XPRoles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_level_up(self, member: discord.Member, new_level: int):
        roles = await self.bot.db.get_xp_roles(member.guild.id)
        for row in roles:
            if row["level"] <= new_level:
                role = member.guild.get_role(row["role_id"])
                if role and role not in member.roles:
                    try:
                        await member.add_roles(role, reason=f"XP Niveau {new_level}")
                    except discord.Forbidden:
                        pass

    xprole_group = app_commands.Group(name="xprole", description="Rôles automatiques par niveau XP")

    @xprole_group.command(name="add", description="Attribue un rôle quand un membre atteint un niveau")
    @app_commands.describe(niveau="Niveau requis", role="Rôle à attribuer")
    @app_commands.default_permissions(manage_guild=True)
    async def xpr_add(self, interaction: discord.Interaction, niveau: app_commands.Range[int, 1], role: discord.Role):
        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message("❌ Ce rôle est au-dessus du mien.", ephemeral=True)
        if role.managed:
            return await interaction.response.send_message("❌ Ce rôle est géré par une intégration.", ephemeral=True)
        await self.bot.db.add_xp_role(interaction.guild.id, niveau, role.id)
        await interaction.response.send_message(
            f"✅ {role.mention} sera attribué au niveau **{niveau}**."
        )

    @xprole_group.command(name="remove", description="Supprime un rôle de niveau")
    @app_commands.describe(niveau="Le niveau à supprimer")
    @app_commands.default_permissions(manage_guild=True)
    async def xpr_remove(self, interaction: discord.Interaction, niveau: int):
        deleted = await self.bot.db.remove_xp_role(interaction.guild.id, niveau)
        if deleted:
            await interaction.response.send_message(f"✅ Rôle du niveau **{niveau}** supprimé.")
        else:
            await interaction.response.send_message(f"❌ Aucun rôle pour le niveau **{niveau}**.", ephemeral=True)

    @xprole_group.command(name="list", description="Liste les rôles attribués par niveau")
    async def xpr_list(self, interaction: discord.Interaction):
        rows = await self.bot.db.get_xp_roles(interaction.guild.id)
        embed = discord.Embed(title="⭐ Rôles par niveau XP", color=discord.Color.gold())
        if not rows:
            embed.description = "Aucun rôle de niveau configuré.\nUtilise `/xprole add` pour en ajouter."
        else:
            lines = []
            for row in rows:
                role = interaction.guild.get_role(row["role_id"])
                role_str = role.mention if role else f"~~rôle supprimé ({row['role_id']})~~"
                lines.append(f"**Niveau {row['level']}** → {role_str}")
            embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(XPRoles(bot))
