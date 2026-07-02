import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from utils.embeds import info_embed, success_embed
from utils.i18n import t


def _fmt_duration(seconds: int, lang: str) -> str:
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        m = seconds // 60
        return f"{m} min"
    elif seconds < 86400:
        h = seconds // 3600
        return f"{h}h"
    else:
        d = seconds // 86400
        return f"{d}j" if lang == "fr" else f"{d}d"


class AFK(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /afk ──────────────────────────────────────────────────────────────────

    @app_commands.command(name="afk", description="Définir ou retirer ton statut AFK")
    @app_commands.describe(raison="Raison de ton absence (optionnel)")
    async def afk(self, interaction: discord.Interaction, raison: str = None):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)

        existing = await self.bot.db.get_afk(interaction.guild_id, interaction.user.id)
        if existing:
            # Toggle off
            await self.bot.db.remove_afk(interaction.guild_id, interaction.user.id)
            try:
                nick = interaction.user.display_name
                if nick.startswith("[AFK] "):
                    nick = nick[len("[AFK] "):]
                await interaction.user.edit(nick=nick)
            except discord.Forbidden:
                pass
            since_dt = datetime.fromisoformat(existing["since"]).replace(tzinfo=timezone.utc)
            elapsed = (discord.utils.utcnow() - since_dt).total_seconds()
            duration_str = _fmt_duration(int(elapsed), lang)
            await interaction.response.send_message(
                embed=info_embed(t(lang, "afk.back", member=interaction.user.mention, duration=duration_str)),
                ephemeral=True,
            )
            return

        if raison is None:
            raison = t(lang, "afk.set_default_reason")

        await self.bot.db.set_afk(interaction.guild_id, interaction.user.id, raison)

        try:
            new_nick = f"[AFK] {interaction.user.display_name}"
            if len(new_nick) <= 32:
                await interaction.user.edit(nick=new_nick)
        except discord.Forbidden:
            pass

        await interaction.response.send_message(
            embed=success_embed(t(lang, "afk.set_success", reason=raison)),
            ephemeral=True,
        )

    # ── on_message ────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        lang = await self.bot.db.get_guild_lang(message.guild.id)

        # ── Author returning from AFK ─────────────────────────────────────────
        afk_data = await self.bot.db.get_afk(message.guild.id, message.author.id)
        if afk_data:
            await self.bot.db.remove_afk(message.guild.id, message.author.id)

            since_dt = datetime.fromisoformat(afk_data["since"]).replace(tzinfo=timezone.utc)
            elapsed = (discord.utils.utcnow() - since_dt).total_seconds()
            duration_str = _fmt_duration(int(elapsed), lang)

            try:
                nick = message.author.display_name
                if nick.startswith("[AFK] "):
                    nick = nick[len("[AFK] "):]
                await message.author.edit(nick=nick)
            except discord.Forbidden:
                pass

            await message.channel.send(
                embed=info_embed(t(lang, "afk.back", member=message.author.mention, duration=duration_str)),
                delete_after=10,
            )
            return  # Don't also check mentions in the same message

        # ── Mentions of AFK users ─────────────────────────────────────────────
        notified = 0
        for member in message.mentions[:3]:
            if member.bot or member.id == message.author.id:
                continue
            afk_info = await self.bot.db.get_afk(message.guild.id, member.id)
            if not afk_info:
                continue

            since_dt = datetime.fromisoformat(afk_info["since"]).replace(tzinfo=timezone.utc)
            elapsed = (discord.utils.utcnow() - since_dt).total_seconds()
            duration_str = _fmt_duration(int(elapsed), lang)

            await message.channel.send(
                embed=info_embed(t(
                    lang,
                    "afk.ping_notify",
                    member=member.display_name,
                    reason=afk_info["reason"],
                    duration=duration_str,
                )),
                delete_after=10,
            )
            notified += 1
            if notified >= 3:
                break


async def setup(bot: commands.Bot):
    await bot.add_cog(AFK(bot))
