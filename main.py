import asyncio
import os
import sys
import traceback

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

from database.db import Database
from utils.i18n import t

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
    "cogs.owner",
]


class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        owner_id = os.getenv("OWNER_ID")
        super().__init__(
            command_prefix=commands.when_mentioned_or("+"),
            intents=intents,
            help_command=None,
            owner_id=int(owner_id) if owner_id else None,
        )
        self.db = Database()
        self._presence_index = 0

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

        self.rotate_presence.start()

    async def on_ready(self):
        print(f"\n🤖 Bot connecté : {self.user} (ID: {self.user.id})")
        print(f"📡 Sur {len(self.guilds)} serveur(s)\n")

    @tasks.loop(seconds=20)
    async def rotate_presence(self):
        member_count = sum(g.member_count or 0 for g in self.guilds)
        presences = [
            (discord.ActivityType.watching, f"{len(self.guilds)} serveur(s) | /help"),
            (discord.ActivityType.watching, f"{member_count} membres"),
            (discord.ActivityType.listening, "/help"),
        ]
        activity_type, name = presences[self._presence_index % len(presences)]
        self._presence_index += 1
        await self.change_presence(activity=discord.Activity(type=activity_type, name=name))

    @rotate_presence.before_loop
    async def before_rotate_presence(self):
        await self.wait_until_ready()

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        # Prefix commands (+...) are owner-only utilities. Stay silent for anyone
        # else so the "+" prefix doesn't reveal that hidden commands even exist.
        if isinstance(error, (commands.CommandNotFound, commands.CheckFailure)):
            return
        if await self.is_owner(ctx.author):
            await ctx.send(f"❌ `{error}`")
        print(f"[ERREUR prefix] {error}", file=sys.stderr)
        traceback.print_exc()

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if interaction.response.is_done():
            send = interaction.followup.send
        else:
            send = interaction.response.send_message

        lang = await self.db.get_guild_lang(interaction.guild_id) if interaction.guild_id else "fr"

        if isinstance(error, app_commands.MissingPermissions):
            await send(t(lang, "err.missing_permissions"), ephemeral=True)
        elif isinstance(error, app_commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            await send(t(lang, "err.bot_missing_permissions", missing=missing), ephemeral=True)
        elif isinstance(error, app_commands.CommandOnCooldown):
            await send(t(lang, "err.on_cooldown", seconds=f"{error.retry_after:.1f}"), ephemeral=True)
        elif isinstance(error, app_commands.NoPrivateMessage):
            await send(t(lang, "err.no_private_message"), ephemeral=True)
        else:
            print(f"[ERREUR] {error}", file=sys.stderr)
            traceback.print_exc()
            await send(t(lang, "err.unexpected", error=error), ephemeral=True)

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
