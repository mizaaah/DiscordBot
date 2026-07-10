import discord
from discord import app_commands
from discord.ext import commands
from utils.colors import Colors

# Stockage en mémoire
snipes = {}
edit_snipes = {}

class Snipe(commands.Cog):
    """Cog pour les commandes snipe et editsnipe"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot:
            return
            
        snipes[message.channel.id] = {
            "content": message.content,
            "author": message.author,
            "time": message.created_at,
            "attachments": [a.url for a in message.attachments]
        }

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or before.content == after.content:
            return
            
        edit_snipes[before.channel.id] = {
            "before": before.content,
            "after": after.content,
            "author": before.author,
            "time": after.edited_at or discord.utils.utcnow()
        }

    @app_commands.command(name="snipe", description="Affiche le dernier message supprimé dans ce salon")
    @app_commands.default_permissions(manage_messages=True)
    async def snipe(self, interaction: discord.Interaction):
        data = snipes.get(interaction.channel_id)
        if not data:
            return await interaction.response.send_message("❌ Aucun message récemment supprimé ici.", ephemeral=True)
            
        embed = discord.Embed(
            description=data["content"] or "*Aucun texte*",
            color=Colors.ERROR.value,
            timestamp=data["time"]
        )
        embed.set_author(name=data["author"].name, icon_url=data["author"].display_avatar.url)
        embed.set_footer(text="Message supprimé")
        
        if data["attachments"]:
            embed.set_image(url=data["attachments"][0])
            
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="editsnipe", description="Affiche le dernier message modifié dans ce salon")
    @app_commands.default_permissions(manage_messages=True)
    async def editsnipe(self, interaction: discord.Interaction):
        data = edit_snipes.get(interaction.channel_id)
        if not data:
            return await interaction.response.send_message("❌ Aucun message récemment modifié ici.", ephemeral=True)
            
        embed = discord.Embed(
            color=Colors.WARNING.value,
            timestamp=data["time"]
        )
        embed.set_author(name=data["author"].name, icon_url=data["author"].display_avatar.url)
        embed.add_field(name="Avant", value=data["before"] or "*Aucun texte*", inline=False)
        embed.add_field(name="Après", value=data["after"] or "*Aucun texte*", inline=False)
        embed.set_footer(text="Message modifié")
            
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Snipe(bot))
