import asyncio
import os
import sys
import traceback
import logging
import logging.handlers
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

from database.db import Database
from utils.i18n import t

load_dotenv()

try:
    from cogs.systems.tickets import _open_ticket
except ImportError:
    _open_ticket = None

class ErrorHelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.button(label="🆘 Demander de l'aide", style=discord.ButtonStyle.danger, custom_id="error_help_ticket")
    async def help_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if _open_ticket:
            await _open_ticket(interaction.client, interaction, category="Support")
        else:
            await interaction.response.send_message("Le système de tickets n'est pas disponible pour le moment.", ephemeral=True)

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
        logging.info("✅ Base de données connectée.")

        cogs_dir = Path("cogs")
        for file in cogs_dir.rglob("*.py"):
            if file.name.startswith("_"):
                continue
            cog_path = ".".join(file.parts).replace(".py", "")
            try:
                await self.load_extension(cog_path)
                logging.info(f"✅ Cog chargé : {cog_path}")
            except Exception as e:
                logging.error(f"❌ Erreur lors du chargement de {cog_path} : {e}", exc_info=True)

        await self.tree.sync()
        logging.info("✅ Slash commands synchronisées.")

        self.rotate_presence.start()

    async def on_ready(self):
        logging.info(f"🤖 Bot connecté : {self.user} (ID: {self.user.id})")
        logging.info(f"📡 Sur {len(self.guilds)} serveur(s)")

    @tasks.loop(seconds=20)
    async def rotate_presence(self):
        member_count = sum(g.member_count or 0 for g in self.guilds)
        presences = [
            (discord.ActivityType.playing, f"✨ Avec {member_count} membres"),
            (discord.ActivityType.watching, f"🌍 {len(self.guilds)} serveurs | /help"),
            (discord.ActivityType.listening, "🎵 Vos requêtes | /help"),
            (discord.ActivityType.competing, "🏆 Pour être le meilleur bot !"),
        ]
        activity_type, name = presences[self._presence_index % len(presences)]
        self._presence_index += 1
        await self.change_presence(
            status=discord.Status.dnd,
            activity=discord.Activity(type=activity_type, name=name)
        )

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
        logging.error(f"[ERREUR prefix] {error}", exc_info=True)

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if interaction.response.is_done():
            send = interaction.followup.send
        else:
            send = interaction.response.send_message

        lang = await self.db.get_guild_lang(interaction.guild_id) if interaction.guild_id else "fr"

        if isinstance(error, app_commands.MissingPermissions):
            await send(t(lang, "err.missing_permissions"), view=ErrorHelpView(), ephemeral=True)
        elif isinstance(error, app_commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            await send(t(lang, "err.bot_missing_permissions", missing=missing), ephemeral=True)
        elif isinstance(error, app_commands.CommandOnCooldown):
            await send(t(lang, "err.on_cooldown", seconds=f"{error.retry_after:.1f}"), ephemeral=True)
        elif isinstance(error, app_commands.NoPrivateMessage):
            await send(t(lang, "err.no_private_message"), ephemeral=True)
        else:
            logging.error(f"[ERREUR] {error}", exc_info=True)
            await send(t(lang, "err.unexpected", error=error), ephemeral=True)

    async def close(self):
        await self.db.close()
        await super().close()


async def main():
    logger = logging.getLogger('discord')
    logger.setLevel(logging.INFO)
    handler = logging.handlers.RotatingFileHandler(
        filename='discord.log',
        encoding='utf-8',
        maxBytes=32 * 1024 * 1024,  # 32 MiB
        backupCount=5,
    )
    dt_fmt = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', dt_fmt, style='{')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logging.error("❌ DISCORD_TOKEN manquant dans le fichier .env")
        sys.exit(1)

    bot = Bot()
    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
