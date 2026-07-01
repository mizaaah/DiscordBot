import discord
from discord import app_commands
from discord.ext import commands
from utils.colors import Colors
from utils.i18n import t


class AntiGhostping(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot  = bot
        self._cache: dict[int, dict[int, discord.Message]] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if not message.mentions and not message.role_mentions:
            return
        gc = self._cache.setdefault(message.guild.id, {})
        gc[message.id] = message
        if len(gc) > 500:
            gc.pop(next(iter(gc)))

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        gc = self._cache.get(message.guild.id, {})
        if message.id not in gc:
            return
        del gc[message.id]

        age = (discord.utils.utcnow() - message.created_at).total_seconds()
        if age > 30:
            return

        settings = await self.bot.db.get_guild_settings(message.guild.id)
        if not settings.get("ghostping_enabled", 1):
            return

        logs = self.bot.get_cog("Logs")
        if not logs:
            return

        lang = await self.bot.db.get_guild_lang(message.guild.id)

        mentions   = " ".join(m.mention for m in message.mentions[:10])
        role_pings = " ".join(r.mention for r in message.role_mentions[:5])
        all_m      = " ".join(filter(None, [mentions, role_pings]))

        embed = discord.Embed(
            title=t(lang, "ghost.detected_title"),
            color=Colors.DANGER,
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        embed.add_field(name=t(lang, "ghost.author"),     value=message.author.mention,  inline=True)
        embed.add_field(name=t(lang, "ghost.channel"),    value=message.channel.mention, inline=True)
        embed.add_field(name=t(lang, "ghost.mentioned"),  value=all_m or "?",            inline=True)
        if message.content:
            embed.add_field(name=t(lang, "ghost.deleted_message"), value=message.content[:500], inline=False)
        embed.set_footer(text=t(lang, "ghost.footer", id=message.author.id, age=int(age)))
        await logs.send_log(message.guild, embed)

    @app_commands.command(name="ghostping", description="Active/désactive la détection des ghost pings")
    @app_commands.describe(activer="Activer ou désactiver")
    @app_commands.default_permissions(manage_guild=True)
    async def ghostping_toggle(self, interaction: discord.Interaction, activer: bool):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        await self.bot.db.update_guild_setting(interaction.guild.id, "ghostping_enabled", int(activer))
        state = t(lang, "ghost.enabled") if activer else t(lang, "ghost.disabled")
        await interaction.response.send_message(t(lang, "ghost.toggle_result", state=state))


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiGhostping(bot))
