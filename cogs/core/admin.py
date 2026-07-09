import discord
from discord import app_commands
from discord.ext import commands
from utils.colors import Colors

class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if await self.bot.db.is_blacklisted(member.guild.id, member.id):
            try:
                await member.send("Tu as été blacklisté(e) de ce serveur.")
            except discord.HTTPException:
                pass
            try:
                await member.ban(reason="Blacklisted from server")
            except discord.Forbidden:
                pass

    wl_group = app_commands.Group(name="wl", description="Commandes de Whitelist", default_permissions=discord.Permissions(manage_guild=True))
    bl_group = app_commands.Group(name="bl", description="Commandes de Blacklist", default_permissions=discord.Permissions(manage_guild=True))

    @wl_group.command(name="add", description="Ajoute un membre à la Whitelist (Bypass AutoMod/Anti-Raid)")
    async def wl_add(self, interaction: discord.Interaction, membre: discord.User):
        await self.bot.db.add_whitelist(interaction.guild_id, membre.id)
        embed = discord.Embed(description=f"✅ {membre.mention} a été ajouté à la **Whitelist**.", color=Colors.SUCCESS.value)
        await interaction.response.send_message(embed=embed)

    @wl_group.command(name="remove", description="Retire un membre de la Whitelist")
    async def wl_remove(self, interaction: discord.Interaction, membre: discord.User):
        removed = await self.bot.db.remove_whitelist(interaction.guild_id, membre.id)
        if removed:
            embed = discord.Embed(description=f"✅ {membre.mention} a été retiré de la **Whitelist**.", color=Colors.SUCCESS.value)
        else:
            embed = discord.Embed(description=f"❌ {membre.mention} n'est pas dans la Whitelist.", color=Colors.ERROR.value)
        await interaction.response.send_message(embed=embed)

    @wl_group.command(name="list", description="Affiche la liste des membres Whitelist")
    async def wl_list(self, interaction: discord.Interaction):
        users = await self.bot.db.get_whitelist(interaction.guild_id)
        if not users:
            return await interaction.response.send_message("La Whitelist est vide.", ephemeral=True)
        
        desc = "\\n".join([f"- <@{u['user_id']}>" for u in users])
        embed = discord.Embed(title="🛡️ Whitelist", description=desc, color=Colors.INFO.value)
        await interaction.response.send_message(embed=embed)


    @bl_group.command(name="add", description="Ajoute un membre à la Blacklist (Banni du bot et du serveur)")
    async def bl_add(self, interaction: discord.Interaction, membre: discord.User):
        if membre.id == interaction.guild.owner_id or membre.id == self.bot.user.id:
            return await interaction.response.send_message("❌ Vous ne pouvez pas blacklist ce membre.", ephemeral=True)
            
        await self.bot.db.add_blacklist(interaction.guild_id, membre.id)
        embed = discord.Embed(description=f"✅ {membre.mention} a été ajouté à la **Blacklist** et sera banni du serveur.", color=Colors.SUCCESS.value)
        await interaction.response.send_message(embed=embed)
        
        member_obj = interaction.guild.get_member(membre.id)
        if member_obj:
            try:
                await member_obj.send("Tu as été blacklisté(e) de ce serveur.")
            except discord.HTTPException:
                pass
            try:
                await member_obj.ban(reason="Blacklisted by admin")
            except discord.Forbidden:
                pass

    @bl_group.command(name="remove", description="Retire un membre de la Blacklist")
    async def bl_remove(self, interaction: discord.Interaction, membre: discord.User):
        removed = await self.bot.db.remove_blacklist(interaction.guild_id, membre.id)
        if removed:
            embed = discord.Embed(description=f"✅ {membre.mention} a été retiré de la **Blacklist**.", color=Colors.SUCCESS.value)
            try:
                await interaction.guild.unban(membre, reason="Removed from blacklist")
            except (discord.NotFound, discord.Forbidden):
                pass
        else:
            embed = discord.Embed(description=f"❌ {membre.mention} n'est pas dans la Blacklist.", color=Colors.ERROR.value)
        await interaction.response.send_message(embed=embed)

    @bl_group.command(name="list", description="Affiche la liste des membres Blacklist")
    async def bl_list(self, interaction: discord.Interaction):
        users = await self.bot.db.get_blacklist(interaction.guild_id)
        if not users:
            return await interaction.response.send_message("La Blacklist est vide.", ephemeral=True)
        
        desc = "\\n".join([f"- <@{u['user_id']}>" for u in users])
        embed = discord.Embed(title="☠️ Blacklist", description=desc, color=Colors.ERROR.value)
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
