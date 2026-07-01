import asyncio
import os
import sys
import traceback

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from database.db import Database

load_dotenv()

COGS = [
    "cogs.logs",
    "cogs.moderation",
    "cogs.automod",
    "cogs.antiraid",
    "cogs.tickets",
    "cogs.reactionroles",
    "cogs.embedbuilder",
    "cogs.info",
    "cogs.xp",
    "cogs.xproles",
    "cogs.tempvoice",
    "cogs.autosanctions",
    "cogs.report",
    "cogs.antighostping",
    "cogs.boost",
    "cogs.cmdperms",
    "cogs.welcome",
    "cogs.config",
    "cogs.starboard",
    "cogs.afk",
    "cogs.giveaway",
]


class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents, help_command=None)
        self.db = Database()

    async def setup_hook(self):
        await self.db.connect()
        print("✅ Base de données connectée.")

        for cog in COGS:
            try:
                await self.load_extension(cog)
                print(f"✅ Cog chargé : {cog}")
            except Exception as e:
                print(f"❌ Erreur lors du chargement de {cog} : {e}")
                traceback.print_exc()

        await self.tree.sync()
        print("✅ Slash commands synchronisées.")

    async def on_ready(self):
        print(f"\n🤖 Bot connecté : {self.user} (ID: {self.user.id})")
        print(f"📡 Sur {len(self.guilds)} serveur(s)\n")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.guilds)} serveur(s) | /help"
            )
        )

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if interaction.response.is_done():
            send = interaction.followup.send
        else:
            send = interaction.response.send_message

        if isinstance(error, app_commands.MissingPermissions):
            await send("❌ Tu n'as pas les permissions nécessaires pour cette commande.", ephemeral=True)
        elif isinstance(error, app_commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            await send(f"❌ Je n'ai pas les permissions nécessaires : `{missing}`.", ephemeral=True)
        elif isinstance(error, app_commands.CommandOnCooldown):
            await send(f"⏳ Commande en cooldown. Réessaie dans {error.retry_after:.1f}s.", ephemeral=True)
        elif isinstance(error, app_commands.NoPrivateMessage):
            await send("❌ Cette commande ne peut pas être utilisée en message privé.", ephemeral=True)
        else:
            print(f"[ERREUR] {error}", file=sys.stderr)
            traceback.print_exc()
            await send(f"❌ Une erreur inattendue s'est produite : `{error}`", ephemeral=True)

    async def close(self):
        await self.db.close()
        await super().close()


async def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ DISCORD_TOKEN manquant dans le fichier .env")
        sys.exit(1)

    bot = Bot()
    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
