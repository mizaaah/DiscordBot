import discord
from discord.ext import commands
from datetime import datetime, timezone
from utils.i18n import t
from utils.colors import Colors


class Logs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def send_log(self, guild: discord.Guild, embed: discord.Embed):
        settings = await self.bot.db.get_guild_settings(guild.id)
        channel_id = settings.get("log_channel_id")
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if channel and channel.permissions_for(guild.me).send_messages:
            await channel.send(embed=embed)

    async def _lang(self, guild: discord.Guild) -> str:
        return await self.bot.db.get_guild_lang(guild.id)

    def _base_embed(self, title: str, color: discord.Color, description: str = None) -> discord.Embed:
        embed = discord.Embed(title=title, color=color, timestamp=datetime.now(timezone.utc))
        if description:
            embed.description = description
        return embed

    # ── Moderation logs ───────────────────────────────────────────────────────

    async def log_kick(self, guild, target, moderator, reason):
        lang  = await self._lang(guild)
        embed = self._base_embed(t(lang, "logs.kick_title"), Colors.WARNING)
        embed.add_field(name=t(lang, "logs.label_member"),    value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name=t(lang, "logs.label_moderator"), value=moderator.mention, inline=True)
        embed.add_field(name=t(lang, "logs.label_reason"),    value=reason, inline=False)
        embed.set_thumbnail(url=target.display_avatar.url)
        await self.send_log(guild, embed)

    async def log_ban(self, guild, target, moderator, reason, duration=None):
        lang  = await self._lang(guild)
        title = t(lang, "logs.ban_temp_title", duration=duration) if duration else t(lang, "logs.ban_title")
        embed = self._base_embed(title, Colors.ERROR)
        embed.add_field(name=t(lang, "logs.label_member"),    value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name=t(lang, "logs.label_moderator"), value=moderator.mention, inline=True)
        embed.add_field(name=t(lang, "logs.label_reason"),    value=reason, inline=False)
        embed.set_thumbnail(url=target.display_avatar.url)
        await self.send_log(guild, embed)

    async def log_unban(self, guild, target, moderator, reason):
        lang  = await self._lang(guild)
        embed = self._base_embed(t(lang, "logs.unban_title"), Colors.SUCCESS)
        embed.add_field(name=t(lang, "logs.label_member"),    value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name=t(lang, "logs.label_moderator"), value=moderator.mention, inline=True)
        embed.add_field(name=t(lang, "logs.label_reason"),    value=reason, inline=False)
        embed.set_thumbnail(url=target.display_avatar.url)
        await self.send_log(guild, embed)

    async def log_mute(self, guild, target, moderator, reason, duration):
        lang  = await self._lang(guild)
        embed = self._base_embed(t(lang, "logs.mute_title"), Colors.WARNING)
        embed.add_field(name=t(lang, "logs.label_member"),    value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name=t(lang, "logs.label_moderator"), value=moderator.mention, inline=True)
        embed.add_field(name=t(lang, "logs.label_duration"),  value=duration, inline=True)
        embed.add_field(name=t(lang, "logs.label_reason"),    value=reason, inline=False)
        embed.set_thumbnail(url=target.display_avatar.url)
        await self.send_log(guild, embed)

    async def log_unmute(self, guild, target, moderator, reason):
        lang  = await self._lang(guild)
        embed = self._base_embed(t(lang, "logs.unmute_title"), Colors.SUCCESS)
        embed.add_field(name=t(lang, "logs.label_member"),    value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name=t(lang, "logs.label_moderator"), value=moderator.mention, inline=True)
        embed.add_field(name=t(lang, "logs.label_reason"),    value=reason, inline=False)
        embed.set_thumbnail(url=target.display_avatar.url)
        await self.send_log(guild, embed)

    async def log_warn(self, guild, target, moderator, reason, warn_id, total):
        lang  = await self._lang(guild)
        embed = self._base_embed(t(lang, "logs.warn_title"), Colors.CAUTION)
        embed.add_field(name=t(lang, "logs.label_member"),    value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name=t(lang, "logs.label_moderator"), value=moderator.mention, inline=True)
        embed.add_field(name=t(lang, "logs.warn_total"),      value=str(total), inline=True)
        embed.add_field(name=t(lang, "logs.label_reason"),    value=reason, inline=False)
        embed.set_footer(text=t(lang, "logs.warn_id_footer", id=warn_id))
        embed.set_thumbnail(url=target.display_avatar.url)
        await self.send_log(guild, embed)

    async def log_clear(self, guild, channel, moderator, count):
        lang  = await self._lang(guild)
        embed = self._base_embed(t(lang, "logs.clear_title"), Colors.INFO)
        embed.add_field(name=t(lang, "logs.label_salon"),     value=channel.mention, inline=True)
        embed.add_field(name=t(lang, "logs.label_moderator"), value=moderator.mention, inline=True)
        embed.add_field(name=t(lang, "logs.clear_quantity"),  value=str(count), inline=True)
        await self.send_log(guild, embed)

    async def log_lock(self, guild, channel, moderator, reason, locked):
        lang  = await self._lang(guild)
        title = t(lang, "logs.lock_title") if locked else t(lang, "logs.unlock_title")
        color = Colors.ERROR if locked else Colors.SUCCESS
        embed = self._base_embed(title, color)
        embed.add_field(name=t(lang, "logs.label_salon"),     value=channel.mention, inline=True)
        embed.add_field(name=t(lang, "logs.label_moderator"), value=moderator.mention, inline=True)
        embed.add_field(name=t(lang, "logs.label_reason"),    value=reason, inline=False)
        await self.send_log(guild, embed)

    # ── Configuration / permissions logs ─────────────────────────────────────

    async def log_config_change(self, guild, moderator, setting, value):
        lang  = await self._lang(guild)
        embed = self._base_embed(t(lang, "logs.config_change_title"), Colors.INFO)
        embed.add_field(name=t(lang, "logs.config_change_setting"), value=setting, inline=True)
        embed.add_field(name=t(lang, "logs.label_moderator"), value=moderator.mention, inline=True)
        embed.add_field(name=t(lang, "logs.config_change_value"), value=str(value)[:1024], inline=False)
        await self.send_log(guild, embed)

    # ── Discord events ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        lang  = await self._lang(member.guild)
        embed = self._base_embed(t(lang, "logs.member_join_title"), Colors.SUCCESS)
        embed.description = t(lang, "logs.member_join_desc", member=member.mention)
        embed.add_field(name=t(lang, "logs.member_join_account"), value=discord.utils.format_dt(member.created_at, 'R'), inline=True)
        embed.add_field(name=t(lang, "logs.member_join_id"),      value=str(member.id), inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await self.send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        lang  = await self._lang(member.guild)
        embed = self._base_embed(t(lang, "logs.member_leave_title"), Colors.ERROR)
        embed.description = t(lang, "logs.member_leave_desc", member=str(member))
        embed.add_field(name=t(lang, "logs.member_leave_id"), value=str(member.id), inline=True)
        roles = [r.mention for r in member.roles if r != member.guild.default_role]
        if roles:
            embed.add_field(name=t(lang, "logs.member_leave_roles"), value=" ".join(roles[:10]), inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        await self.send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        lang  = await self._lang(message.guild)
        embed = self._base_embed(t(lang, "logs.msg_delete_title"), Colors.DANGER)
        embed.add_field(name=t(lang, "logs.msg_delete_author"),  value=f"{message.author.mention} (`{message.author.id}`)", inline=True)
        embed.add_field(name=t(lang, "logs.msg_delete_channel"), value=message.channel.mention, inline=True)
        if message.content:
            embed.add_field(name=t(lang, "logs.msg_delete_content"), value=message.content[:1024], inline=False)
        await self.send_log(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        lang  = await self._lang(before.guild)
        embed = self._base_embed(t(lang, "logs.msg_edit_title"), Colors.INFO)
        embed.add_field(name=t(lang, "logs.msg_edit_author"),  value=f"{before.author.mention} (`{before.author.id}`)", inline=True)
        embed.add_field(name=t(lang, "logs.msg_edit_channel"), value=before.channel.mention, inline=True)
        embed.add_field(name=t(lang, "logs.msg_edit_before"),  value=before.content[:512] or "*vide*", inline=False)
        embed.add_field(name=t(lang, "logs.msg_edit_after"),   value=after.content[:512]  or "*vide*", inline=False)
        embed.add_field(name=t(lang, "logs.msg_edit_link"),    value=f"[{t(lang, 'logs.msg_edit_link_text')}]({after.jump_url})", inline=False)
        await self.send_log(before.guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        lang = await self._lang(after.guild)
        if before.nick != after.nick:
            embed = self._base_embed(t(lang, "logs.nick_change_title"), Colors.INFO)
            embed.add_field(name=t(lang, "logs.nick_change_member"), value=after.mention, inline=True)
            embed.add_field(name=t(lang, "logs.nick_change_before"), value=before.nick or before.name, inline=True)
            embed.add_field(name=t(lang, "logs.nick_change_after"),  value=after.nick  or after.name,  inline=True)
            await self.send_log(after.guild, embed)

        added   = [r for r in after.roles   if r not in before.roles]
        removed = [r for r in before.roles  if r not in after.roles]
        if added or removed:
            embed = self._base_embed(t(lang, "logs.roles_change_title"), Colors.INFO)
            embed.add_field(name=t(lang, "logs.roles_change_member"), value=after.mention, inline=False)
            if added:
                embed.add_field(name=t(lang, "logs.roles_added"),   value=" ".join(r.mention for r in added),   inline=True)
            if removed:
                embed.add_field(name=t(lang, "logs.roles_removed"), value=" ".join(r.mention for r in removed), inline=True)
            await self.send_log(after.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        lang  = await self._lang(channel.guild)
        embed = self._base_embed(t(lang, "logs.channel_create_title"), Colors.SUCCESS)
        embed.add_field(name=t(lang, "logs.label_name"), value=channel.mention, inline=True)
        embed.add_field(name=t(lang, "logs.label_type"), value=str(channel.type).replace("_", " ").title(), inline=True)
        await self.send_log(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        lang  = await self._lang(channel.guild)
        embed = self._base_embed(t(lang, "logs.channel_delete_title"), Colors.ERROR)
        embed.add_field(name=t(lang, "logs.label_name"), value=f"#{channel.name}", inline=True)
        embed.add_field(name=t(lang, "logs.label_type"), value=str(channel.type).replace("_", " ").title(), inline=True)
        await self.send_log(channel.guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))
