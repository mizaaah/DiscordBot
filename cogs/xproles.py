import discord
from discord import app_commands
from discord.ext import commands
from utils.i18n import t
from utils.colors import Colors


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
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(t(lang, "xproles.role_too_high"), ephemeral=True)
        if role.managed:
            return await interaction.response.send_message(t(lang, "xproles.role_managed"), ephemeral=True)
        await self.bot.db.add_xp_role(interaction.guild.id, niveau, role.id)
        await interaction.response.send_message(t(lang, "xproles.add_success", role=role.mention, level=niveau))

    async def _level_autocomplete(self, interaction: discord.Interaction, current: str):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        rows = await self.bot.db.get_xp_roles(interaction.guild.id)
        choices = []
        for row in rows:
            role = interaction.guild.get_role(row["role_id"])
            label = t(lang, "xproles.autocomplete_entry", level=row["level"], role=role.name if role else "???")
            if current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label[:100], value=row["level"]))
        return choices[:25]

    @xprole_group.command(name="remove", description="Supprime un rôle de niveau")
    @app_commands.describe(niveau="Le niveau à supprimer")
    @app_commands.autocomplete(niveau=_level_autocomplete)
    @app_commands.default_permissions(manage_guild=True)
    async def xpr_remove(self, interaction: discord.Interaction, niveau: int):
        lang    = await self.bot.db.get_guild_lang(interaction.guild_id)
        deleted = await self.bot.db.remove_xp_role(interaction.guild.id, niveau)
        if deleted:
            await interaction.response.send_message(t(lang, "xproles.remove_success", level=niveau))
        else:
            await interaction.response.send_message(t(lang, "xproles.remove_not_found", level=niveau), ephemeral=True)

    @xprole_group.command(name="list", description="Liste les rôles attribués par niveau")
    async def xpr_list(self, interaction: discord.Interaction):
        lang  = await self.bot.db.get_guild_lang(interaction.guild_id)
        rows  = await self.bot.db.get_xp_roles(interaction.guild.id)
        embed = discord.Embed(title=t(lang, "xproles.list_title"), color=Colors.GOLD)
        if not rows:
            embed.description = t(lang, "xproles.list_empty")
        else:
            lines = []
            for row in rows:
                role = interaction.guild.get_role(row["role_id"])
                role_str = role.mention if role else t(lang, "xproles.deleted_role", id=row["role_id"])
                lines.append(f"**Niveau {row['level']}** → {role_str}")
            embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(XPRoles(bot))
