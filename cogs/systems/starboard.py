import discord
from discord import app_commands
from discord.ext import commands

from utils.i18n import t
from utils.colors import Colors
from utils.embeds import success_embed


class Starboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /starboard group ──────────────────────────────────────────────────────

    starboard_group = app_commands.Group(
        name="starboard",
        description="Gestion du tableau des messages étoilés",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @starboard_group.command(name="setup", description="Configure le starboard")
    @app_commands.describe(
        salon="Salon où poster les messages étoilés",
        seuil="Nombre d'étoiles requis (défaut : 3)",
    )
    async def setup(
        self,
        interaction: discord.Interaction,
        salon: discord.TextChannel,
        seuil: int = 3,
    ):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        await self.bot.db.update_starboard_config(interaction.guild_id, salon.id, seuil)
        await interaction.response.send_message(
            embed=success_embed(t(lang, "star.config_success", threshold=seuil, channel=salon.mention)),
            ephemeral=True,
        )

    @starboard_group.command(name="disable", description="Désactive le starboard")
    async def disable(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        await self.bot.db.disable_starboard(interaction.guild_id)
        await interaction.response.send_message(
            embed=success_embed(t(lang, "star.disable_success")),
            ephemeral=True,
        )

    @starboard_group.command(name="status", description="Affiche la configuration actuelle du starboard")
    async def status(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        config = await self.bot.db.get_starboard_config(interaction.guild_id)

        embed = discord.Embed(
            title=t(lang, "star.status_title"),
            color=Colors.GOLD.value,
        )

        if not config or not config.get("enabled"):
            embed.description = t(lang, "star.not_configured")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        channel_id = config.get("channel_id")
        channel = interaction.guild.get_channel(channel_id) if channel_id else None
        channel_str = channel.mention if channel else f"`{channel_id}`"

        embed.add_field(
            name=t(lang, "star.enabled_label"),
            value="✅" if config.get("enabled") else "❌",
            inline=True,
        )
        embed.add_field(
            name=t(lang, "star.threshold_label"),
            value=str(config.get("threshold", 3)),
            inline=True,
        )
        embed.add_field(
            name=t(lang, "star.channel_label"),
            value=channel_str,
            inline=True,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _handle_reaction(self, payload: discord.RawReactionActionEvent):
        if str(payload.emoji) != "⭐":
            return
        if not payload.guild_id:
            return

        channel = self.bot.get_channel(payload.channel_id)
        if channel is None:
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

        # Don't star bot messages
        if message.author.bot:
            return

        config = await self.bot.db.get_starboard_config(payload.guild_id)
        if not config or not config.get("enabled") or not config.get("channel_id"):
            return

        threshold = config.get("threshold", 3)
        starboard_channel_id = config["channel_id"]

        # Don't star messages posted in the starboard channel itself
        if channel.id == starboard_channel_id:
            return

        starboard_channel = self.bot.get_channel(starboard_channel_id)
        if starboard_channel is None:
            return

        count = next((r.count for r in message.reactions if str(r.emoji) == "⭐"), 0)
        lang = await self.bot.db.get_guild_lang(payload.guild_id)
        existing = await self.bot.db.get_starboard_post(payload.message_id)

        if count >= threshold:
            embed = discord.Embed(
                description=message.content or "",
                color=Colors.GOLD.value,
                timestamp=message.created_at,
            )
            embed.set_author(
                name=message.author.display_name,
                icon_url=message.author.display_avatar.url,
            )
            if message.attachments:
                img = next(
                    (
                        a
                        for a in message.attachments
                        if a.content_type and a.content_type.startswith("image/")
                    ),
                    None,
                )
                if img:
                    embed.set_image(url=img.url)
            embed.add_field(
                name=t(lang, "star.jump_label"),
                value=f"[→]({message.jump_url})",
                inline=True,
            )
            embed.set_footer(text=f"#{message.channel.name}")

            header = t(lang, "star.pinned_header", count=count, channel=message.channel.mention)

            if existing is None:
                try:
                    star_msg = await starboard_channel.send(content=header, embed=embed)
                    await self.bot.db.upsert_starboard_post(
                        payload.message_id, payload.guild_id, star_msg.id, count
                    )
                except (discord.Forbidden, discord.HTTPException):
                    pass
            else:
                try:
                    star_msg = await starboard_channel.fetch_message(existing["star_msg_id"])
                    await star_msg.edit(content=header, embed=embed)
                    await self.bot.db.upsert_starboard_post(
                        payload.message_id, payload.guild_id, existing["star_msg_id"], count
                    )
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass

        else:
            if existing:
                try:
                    star_msg = await starboard_channel.fetch_message(existing["star_msg_id"])
                    await star_msg.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
                await self.bot.db.delete_starboard_post(payload.message_id)

    # ── Event listeners ───────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await self._handle_reaction(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await self._handle_reaction(payload)


async def setup(bot: commands.Bot):
    await bot.add_cog(Starboard(bot))
