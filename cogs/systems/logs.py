import discord
from discord.ext import commands
from datetime import datetime, timezone
from utils.i18n import t
from utils.colors import Colors


class Logs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def send_log(self, guild: discord.Guild, embed: discord.Embed, log_type: str = None):
        settings = await self.bot.db.get_guild_settings(guild.id)
        
        # Determine specific channel ID based on log_type
        channel_id = None
        if log_type:
            channel_id = settings.get(f"log_{log_type}_id")
            
        # Fallback to the global log_channel_id if the specific one isn't set
        if not channel_id:
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
        embed.set_footer(text="Système de Logs • 17th", icon_url=None)
        return embed

    # ══════════════════════════════════════════════════════════════════════════
    #  MODERATION LOGS (log_type="mod")
    # ══════════════════════════════════════════════════════════════════════════

    async def log_kick(self, guild, target, moderator, reason):
        lang  = await self._lang(guild)
        embed = self._base_embed(f"👢 {t(lang, 'logs.kick_title')}", Colors.WARNING)
        embed.add_field(name="👤 Membre",     value=f"{target.mention}\n`{target.id}`", inline=True)
        embed.add_field(name="🛡️ Modérateur", value=f"{moderator.mention}", inline=True)
        embed.add_field(name="​", value="​", inline=True)
        embed.add_field(name="📝 Raison",     value=f"```{reason}```", inline=False)
        embed.set_thumbnail(url=target.display_avatar.url)
        await self.send_log(guild, embed, log_type="mod")

    async def log_ban(self, guild, target, moderator, reason, duration=None):
        lang  = await self._lang(guild)
        if duration:
            title = f"⛔ {t(lang, 'logs.ban_temp_title', duration=duration)}"
        else:
            title = f"⛔ {t(lang, 'logs.ban_title')}"
        embed = self._base_embed(title, Colors.ERROR)
        embed.add_field(name="👤 Membre",     value=f"{target.mention}\n`{target.id}`", inline=True)
        embed.add_field(name="🛡️ Modérateur", value=f"{moderator.mention}", inline=True)
        embed.add_field(name="​", value="​", inline=True)
        if duration:
            embed.add_field(name="⏳ Durée", value=f"`{duration}`", inline=True)
        embed.add_field(name="📝 Raison",     value=f"```{reason}```", inline=False)
        embed.set_thumbnail(url=target.display_avatar.url)
        await self.send_log(guild, embed, log_type="mod")

    async def log_unban(self, guild, target, moderator, reason):
        lang  = await self._lang(guild)
        embed = self._base_embed(f"✅ {t(lang, 'logs.unban_title')}", Colors.SUCCESS)
        embed.add_field(name="👤 Membre",     value=f"{target.mention}\n`{target.id}`", inline=True)
        embed.add_field(name="🛡️ Modérateur", value=f"{moderator.mention}", inline=True)
        embed.add_field(name="​", value="​", inline=True)
        embed.add_field(name="📝 Raison",     value=f"```{reason}```", inline=False)
        embed.set_thumbnail(url=target.display_avatar.url)
        await self.send_log(guild, embed, log_type="mod")

    async def log_mute(self, guild, target, moderator, reason, duration):
        lang  = await self._lang(guild)
        embed = self._base_embed(f"🔇 {t(lang, 'logs.mute_title')}", Colors.WARNING)
        embed.add_field(name="👤 Membre",     value=f"{target.mention}\n`{target.id}`", inline=True)
        embed.add_field(name="🛡️ Modérateur", value=f"{moderator.mention}", inline=True)
        embed.add_field(name="⏳ Durée",      value=f"`{duration}`", inline=True)
        embed.add_field(name="📝 Raison",     value=f"```{reason}```", inline=False)
        embed.set_thumbnail(url=target.display_avatar.url)
        await self.send_log(guild, embed, log_type="mod")

    async def log_unmute(self, guild, target, moderator, reason):
        lang  = await self._lang(guild)
        embed = self._base_embed(f"🔊 {t(lang, 'logs.unmute_title')}", Colors.SUCCESS)
        embed.add_field(name="👤 Membre",     value=f"{target.mention}\n`{target.id}`", inline=True)
        embed.add_field(name="🛡️ Modérateur", value=f"{moderator.mention}", inline=True)
        embed.add_field(name="​", value="​", inline=True)
        embed.add_field(name="📝 Raison",     value=f"```{reason}```", inline=False)
        embed.set_thumbnail(url=target.display_avatar.url)
        await self.send_log(guild, embed, log_type="mod")

    async def log_warn(self, guild, target, moderator, reason, warn_id, total):
        lang  = await self._lang(guild)
        embed = self._base_embed(f"⚠️ {t(lang, 'logs.warn_title')}", Colors.CAUTION)
        embed.add_field(name="👤 Membre",     value=f"{target.mention}\n`{target.id}`", inline=True)
        embed.add_field(name="🛡️ Modérateur", value=f"{moderator.mention}", inline=True)
        embed.add_field(name="📊 Total",      value=f"`{total}` avertissement(s)", inline=True)
        embed.add_field(name="📝 Raison",     value=f"```{reason}```", inline=False)
        embed.set_footer(text=f"ID Warn : #{warn_id} • Système de Logs • 17th")
        embed.set_thumbnail(url=target.display_avatar.url)
        await self.send_log(guild, embed, log_type="mod")

    async def log_clear(self, guild, channel, moderator, count):
        lang  = await self._lang(guild)
        embed = self._base_embed(f"🧹 {t(lang, 'logs.clear_title')}", Colors.INFO)
        embed.add_field(name="📍 Salon",       value=f"{channel.mention}", inline=True)
        embed.add_field(name="🛡️ Modérateur",  value=f"{moderator.mention}", inline=True)
        embed.add_field(name="🗑️ Messages",    value=f"`{count}` supprimé(s)", inline=True)
        await self.send_log(guild, embed, log_type="mod")

    async def log_lock(self, guild, channel, moderator, reason, locked):
        lang  = await self._lang(guild)
        if locked:
            title = f"🔒 {t(lang, 'logs.lock_title')}"
            color = Colors.ERROR
        else:
            title = f"🔓 {t(lang, 'logs.unlock_title')}"
            color = Colors.SUCCESS
        embed = self._base_embed(title, color)
        embed.add_field(name="📍 Salon",      value=f"{channel.mention}", inline=True)
        embed.add_field(name="🛡️ Modérateur", value=f"{moderator.mention}", inline=True)
        embed.add_field(name="📝 Raison",     value=f"```{reason}```", inline=False)
        await self.send_log(guild, embed, log_type="mod")

    # ══════════════════════════════════════════════════════════════════════════
    #  CONFIGURATION LOGS (log_type="mod")
    # ══════════════════════════════════════════════════════════════════════════

    async def log_config_change(self, guild, moderator, setting, value):
        lang  = await self._lang(guild)
        embed = self._base_embed(f"⚙️ {t(lang, 'logs.config_change_title')}", Colors.INFO)
        embed.add_field(name="🔧 Paramètre",  value=f"`{setting}`", inline=True)
        embed.add_field(name="🛡️ Modérateur", value=f"{moderator.mention}", inline=True)
        embed.add_field(name="📝 Valeur",     value=f"```{str(value)[:1024]}```", inline=False)
        await self.send_log(guild, embed, log_type="mod")

    # ══════════════════════════════════════════════════════════════════════════
    #  MEMBER LOGS (log_type="members")
    # ══════════════════════════════════════════════════════════════════════════

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        lang  = await self._lang(member.guild)

        # Calculate account age
        now = datetime.now(timezone.utc)
        age = now - member.created_at
        if age.days < 7:
            age_warning = f"⚠️ **Compte récent** ({age.days}j)"
        else:
            age_warning = f"✅ {age.days} jours"

        embed = self._base_embed(f"📥 {t(lang, 'logs.member_join_title')}", Colors.SUCCESS)
        embed.description = f"**{member.mention}** vient de rejoindre le serveur !"
        embed.add_field(name="🏷️ Tag",           value=f"`{member}` (`{member.id}`)", inline=True)
        embed.add_field(name="📅 Création",       value=discord.utils.format_dt(member.created_at, 'R'), inline=True)
        embed.add_field(name="🛡️ Âge du compte", value=age_warning, inline=True)
        embed.add_field(name="👥 Membres",        value=f"`{member.guild.member_count}` total", inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await self.send_log(member.guild, embed, log_type="members")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        lang  = await self._lang(member.guild)

        # Calculate time spent on server
        if member.joined_at:
            stay = datetime.now(timezone.utc) - member.joined_at
            stay_str = f"{stay.days}j {stay.seconds // 3600}h"
        else:
            stay_str = "Inconnue"

        embed = self._base_embed(f"📤 {t(lang, 'logs.member_leave_title')}", Colors.ERROR)
        embed.description = f"**{member}** a quitté le serveur."
        embed.add_field(name="🏷️ Tag",        value=f"`{member}` (`{member.id}`)", inline=True)
        embed.add_field(name="📅 Rejoint le",  value=discord.utils.format_dt(member.joined_at, 'D') if member.joined_at else "Inconnu", inline=True)
        embed.add_field(name="⏱️ Durée",       value=f"`{stay_str}`", inline=True)

        roles = [r.mention for r in member.roles if r != member.guild.default_role]
        if roles:
            embed.add_field(name=f"🎭 Rôles ({len(roles)})", value=" ".join(roles[:15]) + (f" *+{len(roles)-15}*" if len(roles) > 15 else ""), inline=False)

        embed.add_field(name="👥 Membres",     value=f"`{member.guild.member_count}` restants", inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await self.send_log(member.guild, embed, log_type="members")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        lang = await self._lang(after.guild)

        # Nickname change
        if before.nick != after.nick:
            embed = self._base_embed("🏷️ Changement de Pseudo", Colors.INFO)
            embed.add_field(name="👤 Membre", value=f"{after.mention} (`{after.id}`)", inline=False)
            embed.add_field(name="📝 Avant",  value=f"`{before.nick or before.name}`", inline=True)
            embed.add_field(name="➡️ Après",  value=f"`{after.nick or after.name}`", inline=True)
            embed.set_thumbnail(url=after.display_avatar.url)
            await self.send_log(after.guild, embed, log_type="members")

        # Role changes
        added   = [r for r in after.roles   if r not in before.roles]
        removed = [r for r in before.roles  if r not in after.roles]
        if added or removed:
            if added and not removed:
                embed = self._base_embed("🎭 Rôle(s) Ajouté(s)", Colors.SUCCESS)
            elif removed and not added:
                embed = self._base_embed("🎭 Rôle(s) Retiré(s)", Colors.ERROR)
            else:
                embed = self._base_embed("🎭 Modification de Rôles", Colors.INFO)

            embed.add_field(name="👤 Membre", value=f"{after.mention} (`{after.id}`)", inline=False)
            if added:
                embed.add_field(name="➕ Ajouté(s)",  value=" ".join(r.mention for r in added),   inline=True)
            if removed:
                embed.add_field(name="➖ Retiré(s)",  value=" ".join(r.mention for r in removed), inline=True)
            embed.set_thumbnail(url=after.display_avatar.url)
            await self.send_log(after.guild, embed, log_type="members")

        # Timeout detection
        before_timeout = before.communication_disabled_until
        after_timeout = after.communication_disabled_until
        if before_timeout != after_timeout:
            if after_timeout and after_timeout > datetime.now(timezone.utc):
                embed = self._base_embed("⏱️ Membre Mis en Sourdine (Timeout)", Colors.WARNING)
                embed.add_field(name="👤 Membre",     value=f"{after.mention} (`{after.id}`)", inline=True)
                embed.add_field(name="⏰ Expire",     value=discord.utils.format_dt(after_timeout, 'R'), inline=True)
                embed.set_thumbnail(url=after.display_avatar.url)
                await self.send_log(after.guild, embed, log_type="members")
            elif before_timeout and (not after_timeout or after_timeout <= datetime.now(timezone.utc)):
                embed = self._base_embed("✅ Sourdine Retirée (Timeout)", Colors.SUCCESS)
                embed.add_field(name="👤 Membre",     value=f"{after.mention} (`{after.id}`)", inline=True)
                embed.set_thumbnail(url=after.display_avatar.url)
                await self.send_log(after.guild, embed, log_type="members")

    # ══════════════════════════════════════════════════════════════════════════
    #  MESSAGE LOGS (log_type="messages")
    # ══════════════════════════════════════════════════════════════════════════

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        lang  = await self._lang(message.guild)

        embed = self._base_embed(f"🗑️ {t(lang, 'logs.msg_delete_title')}", Colors.DANGER)
        embed.add_field(name="👤 Auteur",  value=f"{message.author.mention} (`{message.author.id}`)", inline=True)
        embed.add_field(name="📍 Salon",   value=f"{message.channel.mention}", inline=True)
        embed.add_field(name="​", value="​", inline=True)

        if message.content:
            content = message.content[:1000]
            embed.add_field(name="📝 Contenu supprimé", value=f"```{content}```", inline=False)

        # Log attachments
        if message.attachments:
            att_list = "\n".join(f"📎 [{a.filename}]({a.url})" for a in message.attachments[:5])
            embed.add_field(name=f"📂 Pièces jointes ({len(message.attachments)})", value=att_list, inline=False)

        embed.set_thumbnail(url=message.author.display_avatar.url)
        await self.send_log(message.guild, embed, log_type="messages")

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]):
        if not messages:
            return
        guild = messages[0].guild
        if not guild:
            return
        channel = messages[0].channel

        embed = self._base_embed("🧹 Suppression en Masse", Colors.DANGER)
        embed.add_field(name="📍 Salon",    value=f"{channel.mention}", inline=True)
        embed.add_field(name="🗑️ Messages", value=f"`{len(messages)}` supprimé(s)", inline=True)

        # List unique authors
        authors = set()
        for m in messages:
            if m.author:
                authors.add(m.author.mention)
        if authors:
            embed.add_field(name=f"👥 Auteurs ({len(authors)})", value=" ".join(list(authors)[:10]), inline=False)

        await self.send_log(guild, embed, log_type="messages")

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        lang  = await self._lang(before.guild)

        embed = self._base_embed(f"✏️ {t(lang, 'logs.msg_edit_title')}", Colors.INFO)
        embed.add_field(name="👤 Auteur",  value=f"{before.author.mention} (`{before.author.id}`)", inline=True)
        embed.add_field(name="📍 Salon",   value=f"{before.channel.mention}", inline=True)
        embed.add_field(name="🔗 Lien",    value=f"[Aller au message]({after.jump_url})", inline=True)

        before_text = before.content[:500] or "*vide*"
        after_text = after.content[:500] or "*vide*"
        embed.add_field(name="📝 Avant", value=f"```{before_text}```", inline=False)
        embed.add_field(name="✏️ Après", value=f"```{after_text}```", inline=False)

        embed.set_thumbnail(url=before.author.display_avatar.url)
        await self.send_log(before.guild, embed, log_type="messages")

    # ══════════════════════════════════════════════════════════════════════════
    #  SERVER LOGS (log_type="server")
    # ══════════════════════════════════════════════════════════════════════════

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        type_map = {
            "text": "💬 Textuel",
            "voice": "🔊 Vocal",
            "category": "📁 Catégorie",
            "forum": "📋 Forum",
            "stage_voice": "🎤 Stage",
            "news": "📢 Annonces",
        }
        ch_type = type_map.get(str(channel.type), str(channel.type).replace("_", " ").title())

        embed = self._base_embed("📁 Salon Créé", Colors.SUCCESS)
        embed.add_field(name="📍 Salon",    value=f"{channel.mention} (`{channel.id}`)", inline=True)
        embed.add_field(name="📂 Type",     value=ch_type, inline=True)
        if hasattr(channel, 'category') and channel.category:
            embed.add_field(name="🗂️ Catégorie", value=f"`{channel.category.name}`", inline=True)
        await self.send_log(channel.guild, embed, log_type="server")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        type_map = {
            "text": "💬 Textuel",
            "voice": "🔊 Vocal",
            "category": "📁 Catégorie",
            "forum": "📋 Forum",
            "stage_voice": "🎤 Stage",
            "news": "📢 Annonces",
        }
        ch_type = type_map.get(str(channel.type), str(channel.type).replace("_", " ").title())

        embed = self._base_embed("🗑️ Salon Supprimé", Colors.ERROR)
        embed.add_field(name="📍 Nom",   value=f"`#{channel.name}` (`{channel.id}`)", inline=True)
        embed.add_field(name="📂 Type",  value=ch_type, inline=True)
        if hasattr(channel, 'category') and channel.category:
            embed.add_field(name="🗂️ Catégorie", value=f"`{channel.category.name}`", inline=True)
        await self.send_log(channel.guild, embed, log_type="server")

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        changes = []
        if before.name != after.name:
            changes.append(f"🏷️ **Nom** : `{before.name}` ➔ `{after.name}`")
        if hasattr(before, 'topic') and hasattr(after, 'topic') and before.topic != after.topic:
            changes.append(f"📝 **Sujet** : `{before.topic or 'Aucun'}` ➔ `{after.topic or 'Aucun'}`")
        if hasattr(before, 'slowmode_delay') and hasattr(after, 'slowmode_delay') and before.slowmode_delay != after.slowmode_delay:
            changes.append(f"🐌 **Slowmode** : `{before.slowmode_delay}s` ➔ `{after.slowmode_delay}s`")
        if hasattr(before, 'nsfw') and hasattr(after, 'nsfw') and before.nsfw != after.nsfw:
            changes.append(f"🔞 **NSFW** : `{before.nsfw}` ➔ `{after.nsfw}`")

        if not changes:
            return

        embed = self._base_embed("🔧 Salon Modifié", Colors.INFO)
        embed.add_field(name="📍 Salon", value=f"{after.mention} (`{after.id}`)", inline=False)
        embed.add_field(name="📋 Modifications", value="\n".join(changes), inline=False)
        await self.send_log(after.guild, embed, log_type="server")

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        embed = self._base_embed("🎭 Rôle Créé", Colors.SUCCESS)
        embed.add_field(name="🏷️ Rôle",    value=f"{role.mention} (`{role.id}`)", inline=True)
        embed.add_field(name="🎨 Couleur",  value=f"`{role.color}`" if role.color != discord.Color.default() else "`Par défaut`", inline=True)
        embed.add_field(name="📊 Position", value=f"`{role.position}`", inline=True)
        await self.send_log(role.guild, embed, log_type="server")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        embed = self._base_embed("🗑️ Rôle Supprimé", Colors.ERROR)
        embed.add_field(name="🏷️ Rôle",    value=f"`@{role.name}` (`{role.id}`)", inline=True)
        embed.add_field(name="🎨 Couleur",  value=f"`{role.color}`" if role.color != discord.Color.default() else "`Par défaut`", inline=True)
        embed.add_field(name="👥 Membres",  value=f"`{len(role.members)}`", inline=True)
        await self.send_log(role.guild, embed, log_type="server")

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        changes = []
        if before.name != after.name:
            changes.append(f"🏷️ **Nom** : `{before.name}` ➔ `{after.name}`")
        if before.color != after.color:
            changes.append(f"🎨 **Couleur** : `{before.color}` ➔ `{after.color}`")
        if before.hoist != after.hoist:
            changes.append(f"📌 **Affiché séparément** : `{before.hoist}` ➔ `{after.hoist}`")
        if before.mentionable != after.mentionable:
            changes.append(f"🔔 **Mentionnable** : `{before.mentionable}` ➔ `{after.mentionable}`")
        if before.permissions != after.permissions:
            changes.append(f"🔐 **Permissions modifiées**")

        if not changes:
            return

        embed = self._base_embed("🔧 Rôle Modifié", Colors.INFO)
        embed.add_field(name="🎭 Rôle", value=f"{after.mention} (`{after.id}`)", inline=False)
        embed.add_field(name="📋 Modifications", value="\n".join(changes), inline=False)
        await self.send_log(after.guild, embed, log_type="server")

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        changes = []
        if before.name != after.name:
            changes.append(f"🏷️ **Nom** : `{before.name}` ➔ `{after.name}`")
        if before.icon != after.icon:
            changes.append(f"🖼️ **Icône du serveur** modifiée")
        if before.banner != after.banner:
            changes.append(f"🎨 **Bannière** modifiée")
        if before.verification_level != after.verification_level:
            changes.append(f"🔒 **Niveau de vérification** : `{before.verification_level}` ➔ `{after.verification_level}`")
        if before.default_notifications != after.default_notifications:
            changes.append(f"🔔 **Notifications** modifiées")
        if before.vanity_url_code != after.vanity_url_code:
            changes.append(f"🔗 **URL Vanity** : `{before.vanity_url_code}` ➔ `{after.vanity_url_code}`")

        if not changes:
            return

        embed = self._base_embed("🏰 Serveur Modifié", Colors.INFO)
        embed.add_field(name="📋 Modifications", value="\n".join(changes), inline=False)
        if after.icon:
            embed.set_thumbnail(url=after.icon.url)
        await self.send_log(after, embed, log_type="server")

    # ══════════════════════════════════════════════════════════════════════════
    #  VOICE LOGS (log_type="voice")
    # ══════════════════════════════════════════════════════════════════════════

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # Channel changes (join/leave/move)
        if before.channel != after.channel:
            if before.channel is None and after.channel is not None:
                embed = self._base_embed("🟢 Connexion Vocale", Colors.SUCCESS)
                embed.add_field(name="👤 Membre", value=f"{member.mention} (`{member.id}`)", inline=True)
                embed.add_field(name="🔊 Salon",  value=f"{after.channel.mention}", inline=True)
                embed.add_field(name="👥 Dans le salon", value=f"`{len(after.channel.members)}` membre(s)", inline=True)
                embed.set_thumbnail(url=member.display_avatar.url)
                await self.send_log(member.guild, embed, log_type="voice")

            elif before.channel is not None and after.channel is None:
                embed = self._base_embed("🔴 Déconnexion Vocale", Colors.ERROR)
                embed.add_field(name="👤 Membre", value=f"{member.mention} (`{member.id}`)", inline=True)
                embed.add_field(name="🔊 Salon",  value=f"{before.channel.mention}", inline=True)
                embed.add_field(name="👥 Restants", value=f"`{len(before.channel.members)}` membre(s)", inline=True)
                embed.set_thumbnail(url=member.display_avatar.url)
                await self.send_log(member.guild, embed, log_type="voice")

            else:
                embed = self._base_embed("🔄 Changement de Salon Vocal", Colors.INFO)
                embed.add_field(name="👤 Membre",   value=f"{member.mention} (`{member.id}`)", inline=False)
                embed.add_field(name="📤 Quitté",   value=f"{before.channel.mention}", inline=True)
                embed.add_field(name="➡️",          value="​", inline=True)
                embed.add_field(name="📥 Rejoint",  value=f"{after.channel.mention}", inline=True)
                embed.set_thumbnail(url=member.display_avatar.url)
                await self.send_log(member.guild, embed, log_type="voice")

        # Server mute / deafen
        if before.mute != after.mute:
            if after.mute:
                embed = self._base_embed("🔇 Mute Serveur", Colors.WARNING)
                embed.description = f"{member.mention} a été **rendu muet** par le serveur."
            else:
                embed = self._base_embed("🔈 Unmute Serveur", Colors.SUCCESS)
                embed.description = f"{member.mention} a été **démuté** par le serveur."
            embed.set_thumbnail(url=member.display_avatar.url)
            await self.send_log(member.guild, embed, log_type="voice")

        if before.deaf != after.deaf:
            if after.deaf:
                embed = self._base_embed("🔇 Sourdine Serveur", Colors.WARNING)
                embed.description = f"{member.mention} a été **mis en sourdine** par le serveur."
            else:
                embed = self._base_embed("🔈 Sourdine Retirée", Colors.SUCCESS)
                embed.description = f"{member.mention} n'est **plus en sourdine** serveur."
            embed.set_thumbnail(url=member.display_avatar.url)
            await self.send_log(member.guild, embed, log_type="voice")

    # ══════════════════════════════════════════════════════════════════════════
    #  INVITE LOGS (log_type="server")
    # ══════════════════════════════════════════════════════════════════════════

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if not invite.guild:
            return
        embed = self._base_embed("🔗 Invitation Créée", Colors.SUCCESS)
        embed.add_field(name="🔗 Code",       value=f"`{invite.code}`", inline=True)
        embed.add_field(name="👤 Créateur",   value=f"{invite.inviter.mention}" if invite.inviter else "Inconnu", inline=True)
        embed.add_field(name="📍 Salon",      value=f"{invite.channel.mention}" if invite.channel else "Inconnu", inline=True)
        if invite.max_uses:
            embed.add_field(name="🔢 Utilisations max", value=f"`{invite.max_uses}`", inline=True)
        if invite.max_age:
            embed.add_field(name="⏳ Expire dans", value=f"`{invite.max_age // 3600}h`" if invite.max_age >= 3600 else f"`{invite.max_age // 60}min`", inline=True)
        else:
            embed.add_field(name="⏳ Expire", value="`Jamais`", inline=True)
        await self.send_log(invite.guild, embed, log_type="server")

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        if not invite.guild:
            return
        embed = self._base_embed("🔗 Invitation Supprimée", Colors.ERROR)
        embed.add_field(name="🔗 Code",   value=f"`{invite.code}`", inline=True)
        embed.add_field(name="📍 Salon",  value=f"{invite.channel.mention}" if invite.channel else "Inconnu", inline=True)
        if invite.uses is not None:
            embed.add_field(name="🔢 Utilisations", value=f"`{invite.uses}`", inline=True)
        await self.send_log(invite.guild, embed, log_type="server")


async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))
