import discord
from discord.ext import commands
from datetime import datetime, timezone


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

    def _base_embed(self, title: str, color: discord.Color, description: str = None) -> discord.Embed:
        embed = discord.Embed(title=title, color=color, timestamp=datetime.now(timezone.utc))
        if description:
            embed.description = description
        return embed

    # ── Moderation logs (called by moderation cog) ──────────────────────────

    async def log_kick(self, guild: discord.Guild, target: discord.Member, moderator: discord.Member, reason: str):
        embed = self._base_embed("👢 Membre expulsé", discord.Color.orange())
        embed.add_field(name="Membre", value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name="Modérateur", value=moderator.mention, inline=True)
        embed.add_field(name="Raison", value=reason, inline=False)
        embed.set_thumbnail(url=target.display_avatar.url)
        await self.send_log(guild, embed)

    async def log_ban(self, guild: discord.Guild, target: discord.User, moderator: discord.Member, reason: str, duration: str = None):
        label = f"⏱️ Ban temporaire ({duration})" if duration else "🔨 Membre banni"
        embed = self._base_embed(label, discord.Color.red())
        embed.add_field(name="Membre", value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name="Modérateur", value=moderator.mention, inline=True)
        embed.add_field(name="Raison", value=reason, inline=False)
        embed.set_thumbnail(url=target.display_avatar.url)
        await self.send_log(guild, embed)

    async def log_unban(self, guild: discord.Guild, target: discord.User, moderator: discord.Member, reason: str):
        embed = self._base_embed("✅ Membre débanni", discord.Color.green())
        embed.add_field(name="Membre", value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name="Modérateur", value=moderator.mention, inline=True)
        embed.add_field(name="Raison", value=reason, inline=False)
        embed.set_thumbnail(url=target.display_avatar.url)
        await self.send_log(guild, embed)

    async def log_mute(self, guild: discord.Guild, target: discord.Member, moderator: discord.Member, reason: str, duration: str):
        embed = self._base_embed("🔇 Membre muté", discord.Color.dark_orange())
        embed.add_field(name="Membre", value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name="Modérateur", value=moderator.mention, inline=True)
        embed.add_field(name="Durée", value=duration, inline=True)
        embed.add_field(name="Raison", value=reason, inline=False)
        embed.set_thumbnail(url=target.display_avatar.url)
        await self.send_log(guild, embed)

    async def log_unmute(self, guild: discord.Guild, target: discord.Member, moderator: discord.Member, reason: str):
        embed = self._base_embed("🔊 Membre démuté", discord.Color.green())
        embed.add_field(name="Membre", value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name="Modérateur", value=moderator.mention, inline=True)
        embed.add_field(name="Raison", value=reason, inline=False)
        embed.set_thumbnail(url=target.display_avatar.url)
        await self.send_log(guild, embed)

    async def log_warn(self, guild: discord.Guild, target: discord.Member, moderator: discord.Member, reason: str, warn_id: int, total: int):
        embed = self._base_embed("⚠️ Avertissement", discord.Color.yellow())
        embed.add_field(name="Membre", value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name="Modérateur", value=moderator.mention, inline=True)
        embed.add_field(name="Total warns", value=str(total), inline=True)
        embed.add_field(name="Raison", value=reason, inline=False)
        embed.set_footer(text=f"ID du warn : #{warn_id}")
        embed.set_thumbnail(url=target.display_avatar.url)
        await self.send_log(guild, embed)

    async def log_clear(self, guild: discord.Guild, channel: discord.TextChannel, moderator: discord.Member, count: int):
        embed = self._base_embed("🗑️ Messages supprimés", discord.Color.blurple())
        embed.add_field(name="Salon", value=channel.mention, inline=True)
        embed.add_field(name="Modérateur", value=moderator.mention, inline=True)
        embed.add_field(name="Quantité", value=str(count), inline=True)
        await self.send_log(guild, embed)

    async def log_lock(self, guild: discord.Guild, channel: discord.TextChannel, moderator: discord.Member, reason: str, locked: bool):
        label = "🔒 Salon verrouillé" if locked else "🔓 Salon déverrouillé"
        color = discord.Color.red() if locked else discord.Color.green()
        embed = self._base_embed(label, color)
        embed.add_field(name="Salon", value=channel.mention, inline=True)
        embed.add_field(name="Modérateur", value=moderator.mention, inline=True)
        embed.add_field(name="Raison", value=reason, inline=False)
        await self.send_log(guild, embed)

    # ── Discord events ───────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = self._base_embed("📥 Membre rejoint", discord.Color.green())
        embed.description = f"{member.mention} a rejoint le serveur."
        embed.add_field(name="Compte créé le", value=discord.utils.format_dt(member.created_at, 'R'), inline=True)
        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await self.send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = self._base_embed("📤 Membre parti", discord.Color.red())
        embed.description = f"**{member}** a quitté le serveur."
        embed.add_field(name="ID", value=str(member.id), inline=True)
        roles = [r.mention for r in member.roles if r != member.guild.default_role]
        if roles:
            embed.add_field(name="Rôles", value=" ".join(roles[:10]), inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        await self.send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        embed = self._base_embed("🗑️ Message supprimé", discord.Color.dark_red())
        embed.add_field(name="Auteur", value=f"{message.author.mention} (`{message.author.id}`)", inline=True)
        embed.add_field(name="Salon", value=message.channel.mention, inline=True)
        if message.content:
            embed.add_field(name="Contenu", value=message.content[:1024], inline=False)
        await self.send_log(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        embed = self._base_embed("✏️ Message modifié", discord.Color.blue())
        embed.add_field(name="Auteur", value=f"{before.author.mention} (`{before.author.id}`)", inline=True)
        embed.add_field(name="Salon", value=before.channel.mention, inline=True)
        embed.add_field(name="Avant", value=before.content[:512] or "*vide*", inline=False)
        embed.add_field(name="Après", value=after.content[:512] or "*vide*", inline=False)
        embed.add_field(name="Lien", value=f"[Voir le message]({after.jump_url})", inline=False)
        await self.send_log(before.guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.nick != after.nick:
            embed = self._base_embed("📝 Pseudo modifié", discord.Color.blurple())
            embed.add_field(name="Membre", value=after.mention, inline=True)
            embed.add_field(name="Avant", value=before.nick or before.name, inline=True)
            embed.add_field(name="Après", value=after.nick or after.name, inline=True)
            await self.send_log(after.guild, embed)

        added = [r for r in after.roles if r not in before.roles]
        removed = [r for r in before.roles if r not in after.roles]
        if added or removed:
            embed = self._base_embed("🎭 Rôles modifiés", discord.Color.blurple())
            embed.add_field(name="Membre", value=after.mention, inline=False)
            if added:
                embed.add_field(name="Rôles ajoutés", value=" ".join(r.mention for r in added), inline=True)
            if removed:
                embed.add_field(name="Rôles retirés", value=" ".join(r.mention for r in removed), inline=True)
            await self.send_log(after.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        embed = self._base_embed("📢 Salon créé", discord.Color.green())
        embed.add_field(name="Nom", value=channel.mention, inline=True)
        embed.add_field(name="Type", value=str(channel.type).replace("_", " ").title(), inline=True)
        await self.send_log(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        embed = self._base_embed("🗑️ Salon supprimé", discord.Color.red())
        embed.add_field(name="Nom", value=f"#{channel.name}", inline=True)
        embed.add_field(name="Type", value=str(channel.type).replace("_", " ").title(), inline=True)
        await self.send_log(channel.guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))
