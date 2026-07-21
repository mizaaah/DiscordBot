import discord
from discord.ext import commands, tasks
import asyncio

class Stats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.stats_updater.start()

    async def cog_unload(self):
        self.stats_updater.cancel()

    async def create_stats_channels(self, guild: discord.Guild):
        # Création de la catégorie
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=False)
        }
        category = await guild.create_category("📊 STATISTIQUES", overwrites=overwrites, position=0)
        
        # Calculate stats
        members = guild.member_count
        bots = len([m for m in guild.members if m.bot])
        online = len([m for m in guild.members if m.status != discord.Status.offline])
        
        # Create channels
        ch_members = await guild.create_voice_channel(f"👥 Membres : {members}", category=category)
        ch_online = await guild.create_voice_channel(f"🟢 En Ligne : {online}", category=category)
        ch_bots = await guild.create_voice_channel(f"🤖 Bots : {bots}", category=category)
        
        # Save to DB
        await self.bot.db.set_stats_channels(guild.id, category.id, ch_members.id, ch_online.id, ch_bots.id)
        
    @tasks.loop(minutes=10)
    async def stats_updater(self):
        # Attendre que le bot soit prêt et la DB connectée
        await self.bot.wait_until_ready()
        
        channels = await self.bot.db.get_all_stats_channels()
        for row in channels:
            guild = self.bot.get_guild(row["guild_id"])
            if not guild:
                continue
                
            try:
                # Update logic
                members = guild.member_count
                bots = len([m for m in guild.members if m.bot])
                online = len([m for m in guild.members if m.status != discord.Status.offline])
                
                # Fetch channels
                ch_members = guild.get_channel(row["members_channel_id"])
                ch_online = guild.get_channel(row["online_channel_id"])
                ch_bots = guild.get_channel(row["bots_channel_id"])
                
                # We need to edit only if name changed
                if ch_members and ch_members.name != f"👥 Membres : {members}":
                    try: await ch_members.edit(name=f"👥 Membres : {members}")
                    except discord.HTTPException: pass
                    
                if ch_online and ch_online.name != f"🟢 En Ligne : {online}":
                    try: await ch_online.edit(name=f"🟢 En Ligne : {online}")
                    except discord.HTTPException: pass
                    
                if ch_bots and ch_bots.name != f"🤖 Bots : {bots}":
                    try: await ch_bots.edit(name=f"🤖 Bots : {bots}")
                    except discord.HTTPException: pass
                    
            except Exception as e:
                import logging
                logging.error(f"Error updating stats for guild {guild.id}: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Stats(bot))
