"""
Notifications sociales — Twitch (live) & TikTok (posts).

• Twitch : utilise l'API Helix (nécessite TWITCH_CLIENT_ID + TWITCH_CLIENT_SECRET dans .env)
• TikTok : scrape le flux RSS via RSSHub (aucune clé nécessaire, mais moins fiable)

Commandes :
  /notifications setup <salon>           — Définir le salon de notifications
  /notifications twitch <nom>            — Ajouter un streamer Twitch
  /notifications tiktok <nom>            — Ajouter un compte TikTok
  /notifications remove <plateforme> <nom> — Retirer un suivi
  /notifications list                    — Voir les comptes suivis
  /notifications message <plateforme> <texte> — Personnaliser le message
"""

import logging
import os
import re
from datetime import datetime, timezone

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.embeds import error_embed, success_embed, info_embed
from utils.i18n import t

log = logging.getLogger("discord")

TWITCH_COLOR = discord.Color.from_str("#9146FF")
TIKTOK_COLOR = discord.Color.from_str("#FE2C55")

# ── Twitch helpers ────────────────────────────────────────────────────────────

class TwitchAPI:
    """Thin wrapper around Twitch Helix, handling OAuth app tokens."""

    BASE = "https://api.twitch.tv/helix"

    def __init__(self):
        self.client_id: str | None = os.getenv("TWITCH_CLIENT_ID")
        self.client_secret: str | None = os.getenv("TWITCH_CLIENT_SECRET")
        self._token: str | None = None
        self._session: aiohttp.ClientSession | None = None

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get_token(self):
        await self._ensure_session()
        async with self._session.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
        ) as r:
            data = await r.json()
            self._token = data.get("access_token")

    async def _headers(self) -> dict:
        if not self._token:
            await self._get_token()
        return {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self._token}",
        }

    async def get_streams(self, logins: list[str]) -> list[dict]:
        """Retourne les streams *en ligne* pour les logins donnés."""
        if not logins or not self.configured:
            return []
        await self._ensure_session()
        params = [("user_login", l) for l in logins[:100]]
        try:
            async with self._session.get(
                f"{self.BASE}/streams", params=params, headers=await self._headers()
            ) as r:
                if r.status == 401:
                    # Token expiré → refresh
                    await self._get_token()
                    async with self._session.get(
                        f"{self.BASE}/streams", params=params, headers=await self._headers()
                    ) as r2:
                        data = await r2.json()
                else:
                    data = await r.json()
            return data.get("data", [])
        except Exception as e:
            log.error(f"[Notifications] Twitch API error: {e}")
            return []

    async def get_users(self, logins: list[str]) -> list[dict]:
        """Récupère les infos de profil Twitch (avatar, etc.)."""
        if not logins or not self.configured:
            return []
        await self._ensure_session()
        params = [("login", l) for l in logins[:100]]
        try:
            async with self._session.get(
                f"{self.BASE}/users", params=params, headers=await self._headers()
            ) as r:
                if r.status == 401:
                    await self._get_token()
                    async with self._session.get(
                        f"{self.BASE}/users", params=params, headers=await self._headers()
                    ) as r2:
                        data = await r2.json()
                else:
                    data = await r.json()
            return data.get("data", [])
        except Exception as e:
            log.error(f"[Notifications] Twitch Users API error: {e}")
            return []


# ── TikTok RSS helper ─────────────────────────────────────────────────────────

class TikTokRSS:
    """Scrape les posts TikTok via RSSHub (instance publique)."""

    RSSHUB_BASES = [
        "https://rsshub.app",
        "https://rsshub.rssforever.com",
    ]

    def __init__(self):
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_latest_post(self, username: str) -> dict | None:
        """
        Retourne le dernier post TikTok d'un utilisateur via RSS.
        Format retourné : {"title": ..., "link": ..., "pubDate": ...}
        Retourne None si indisponible.
        """
        username = username.lstrip("@")
        await self._ensure_session()

        for base in self.RSSHUB_BASES:
            url = f"{base}/tiktok/user/@{username}"
            try:
                async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status != 200:
                        continue
                    text = await r.text()

                    # Parse simple XML — on cherche le premier <item>
                    item_match = re.search(r"<item>(.*?)</item>", text, re.DOTALL)
                    if not item_match:
                        continue

                    item = item_match.group(1)
                    title = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>", item)
                    link = re.search(r"<link>(.*?)</link>", item)
                    pub = re.search(r"<pubDate>(.*?)</pubDate>", item)

                    if not title:
                        title = re.search(r"<title>(.*?)</title>", item)

                    return {
                        "title": title.group(1) if title else "Nouveau post TikTok",
                        "link": link.group(1) if link else f"https://www.tiktok.com/@{username}",
                        "pubDate": pub.group(1) if pub else None,
                    }
            except Exception as e:
                log.warning(f"[Notifications] TikTok RSS error ({base}): {e}")
                continue

        return None


# ── Cog principal ─────────────────────────────────────────────────────────────

class Notifications(commands.Cog):
    """Système de notifications sociales (Twitch + TikTok)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.twitch = TwitchAPI()
        self.tiktok = TikTokRSS()
        # État local : guild_id -> { "twitch": {login: bool_was_live}, "tiktok": {user: last_link} }
        self._state: dict[int, dict] = {}

    async def cog_load(self):
        self.check_feeds.start()

    async def cog_unload(self):
        self.check_feeds.cancel()
        await self.twitch.close()
        await self.tiktok.close()

    # ── Background check loop ────────────────────────────────────────────────

    @tasks.loop(seconds=90)
    async def check_feeds(self):
        """Vérifie tous les feeds Twitch & TikTok périodiquement."""
        try:
            all_feeds = await self.bot.db.get_all_notification_feeds()
        except Exception as e:
            log.error(f"[Notifications] DB error: {e}")
            return

        # Regrouper par guild
        guilds: dict[int, list[dict]] = {}
        for feed in all_feeds:
            guilds.setdefault(feed["guild_id"], []).append(feed)

        # ── Twitch ────────────────────────────────────────────────────────
        twitch_logins = [f["username"] for f in all_feeds if f["platform"] == "twitch"]
        live_streams = {}
        if twitch_logins:
            streams = await self.twitch.get_streams(list(set(twitch_logins)))
            for s in streams:
                live_streams[s["user_login"].lower()] = s

        # Récupérer les avatars Twitch des streamers live
        twitch_users = {}
        if live_streams:
            users = await self.twitch.get_users(list(live_streams.keys()))
            for u in users:
                twitch_users[u["login"].lower()] = u

        for guild_id, feeds in guilds.items():
            guild_state = self._state.setdefault(guild_id, {"twitch": {}, "tiktok": {}})
            lang = await self.bot.db.get_guild_lang(guild_id)

            for feed in feeds:
                platform = feed["platform"]
                username = feed["username"]
                channel_id = feed["channel_id"]
                custom_msg = feed.get("message")

                channel = self.bot.get_channel(channel_id)
                if not channel:
                    continue

                if platform == "twitch":
                    was_live = guild_state["twitch"].get(username, False)
                    is_live = username.lower() in live_streams

                    if is_live and not was_live:
                        # Vient de passer en live !
                        stream = live_streams[username.lower()]
                        user_info = twitch_users.get(username.lower(), {})
                        await self._send_twitch_notification(
                            channel, stream, user_info, custom_msg, lang, feed
                        )

                    guild_state["twitch"][username] = is_live

                elif platform == "tiktok":
                    post = await self.tiktok.get_latest_post(username)
                    if post:
                        last_link = guild_state["tiktok"].get(username)
                        if last_link is None:
                            # Première vérification — on sauvegarde sans notifier
                            guild_state["tiktok"][username] = post["link"]
                        elif post["link"] != last_link:
                            # Nouveau post !
                            guild_state["tiktok"][username] = post["link"]
                            await self._send_tiktok_notification(
                                channel, username, post, custom_msg, lang, feed
                            )

    @check_feeds.before_loop
    async def before_check_feeds(self):
        await self.bot.wait_until_ready()
        # Initialiser l'état pour ne pas spam au démarrage
        try:
            all_feeds = await self.bot.db.get_all_notification_feeds()
        except Exception:
            return

        twitch_logins = [f["username"] for f in all_feeds if f["platform"] == "twitch"]
        if twitch_logins:
            streams = await self.twitch.get_streams(list(set(twitch_logins)))
            live_set = {s["user_login"].lower() for s in streams}
        else:
            live_set = set()

        for feed in all_feeds:
            guild_state = self._state.setdefault(feed["guild_id"], {"twitch": {}, "tiktok": {}})

            if feed["platform"] == "twitch":
                guild_state["twitch"][feed["username"]] = feed["username"].lower() in live_set

            elif feed["platform"] == "tiktok":
                post = await self.tiktok.get_latest_post(feed["username"])
                if post:
                    guild_state["tiktok"][feed["username"]] = post["link"]

    # ── Notification senders ─────────────────────────────────────────────────

    async def _send_twitch_notification(
        self, channel: discord.TextChannel, stream: dict, user_info: dict,
        custom_msg: str | None, lang: str, feed: dict
    ):
        login = stream["user_login"]
        display = stream.get("user_name", login)
        title = stream.get("title", "")
        game = stream.get("game_name", t(lang, "notif.no_game"))
        viewers = stream.get("viewer_count", 0)
        url = f"https://twitch.tv/{login}"

        # Thumbnail du stream (remplacer les placeholders Twitch)
        thumbnail = stream.get("thumbnail_url", "")
        if thumbnail:
            thumbnail = thumbnail.replace("{width}", "440").replace("{height}", "248")

        if custom_msg:
            description = (custom_msg
                .replace("{user}", display)
                .replace("{url}", url)
                .replace("{game}", game)
                .replace("{title}", title)
            )
        else:
            description = t(lang, "notif.twitch_live_desc", user=display, url=url)

        embed_color = TWITCH_COLOR
        if feed.get("embed_color"):
            try:
                embed_color = discord.Color.from_str(feed["embed_color"])
            except ValueError:
                pass

        embed = discord.Embed(
            title=f"🔴 {display} {t(lang, 'notif.is_live')}",
            url=url,
            description=description,
            color=embed_color,
            timestamp=datetime.now(timezone.utc),
        )

        if title:
            embed.add_field(name=t(lang, "notif.stream_title"), value=title, inline=False)
        embed.add_field(name=t(lang, "notif.game"), value=game, inline=True)
        embed.add_field(name=t(lang, "notif.viewers"), value=f"👀 {viewers:,}", inline=True)

        if thumbnail:
            embed.set_image(url=thumbnail)

        avatar = user_info.get("profile_image_url")
        if avatar:
            embed.set_thumbnail(url=avatar)

        embed.set_footer(text="Twitch", icon_url="https://brand.twitch.tv/assets/logos/svg/glitch-logo-purple.svg")

        content = f"🔴 **{display}** est en live !"
        if feed.get("ping_role_id"):
            content = f"<@&{feed['ping_role_id']}> {content}"

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label=t(lang, "notif.watch_live"), url=url, style=discord.ButtonStyle.link, emoji="📺"))

        try:
            await channel.send(content=content, embed=embed, view=view)
        except discord.Forbidden:
            log.warning(f"[Notifications] Can't send to #{channel.name} ({channel.guild.id})")

    async def _send_tiktok_notification(
        self, channel: discord.TextChannel, username: str, post: dict,
        custom_msg: str | None, lang: str, feed: dict
    ):
        clean_user = username.lstrip("@")
        url = post.get("link", f"https://www.tiktok.com/@{clean_user}")
        title_text = post.get("title", "")

        if custom_msg:
            description = (custom_msg
                .replace("{user}", clean_user)
                .replace("{url}", url)
                .replace("{title}", title_text)
            )
        else:
            description = t(lang, "notif.tiktok_new_post_desc", user=clean_user, url=url)

        embed_color = TIKTOK_COLOR
        if feed.get("embed_color"):
            try:
                embed_color = discord.Color.from_str(feed["embed_color"])
            except ValueError:
                pass

        embed = discord.Embed(
            title=f"🎵 {clean_user} {t(lang, 'notif.new_tiktok')}",
            url=url,
            description=description,
            color=embed_color,
            timestamp=datetime.now(timezone.utc),
        )

        if title_text:
            embed.add_field(name=t(lang, "notif.post_title"), value=title_text[:256], inline=False)

        embed.set_footer(text="TikTok")

        content = f"🎵 **{clean_user}** a posté une nouvelle vidéo !"
        if feed.get("ping_role_id"):
            content = f"<@&{feed['ping_role_id']}> {content}"

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label=t(lang, "notif.watch_video"), url=url, style=discord.ButtonStyle.link, emoji="🎵"))

        try:
            await channel.send(content=content, embed=embed, view=view)
        except discord.Forbidden:
            log.warning(f"[Notifications] Can't send to #{channel.name} ({channel.guild.id})")

    # ── UI & Command ──────────────────────────────────────────────────────────

    @app_commands.command(name="notifications", description="Ouvrir le panneau de gestion des notifications Twitch & TikTok")
    @app_commands.default_permissions(manage_guild=True)
    async def notif_dashboard_cmd(self, interaction: discord.Interaction):
        view = NotifDashboardView(self)
        await view.init(interaction)


class NotifDashboardView(discord.ui.View):
    def __init__(self, cog: Notifications):
        super().__init__(timeout=300)
        self.cog = cog

    async def init(self, interaction: discord.Interaction):
        lang = await self.cog.bot.db.get_guild_lang(interaction.guild_id)
        channel_id = await self.cog.bot.db.get_notification_channel(interaction.guild_id)
        feeds = await self.cog.bot.db.get_notification_feeds(interaction.guild_id)

        embed = discord.Embed(
            title="🔔 Notifications Sociales",
            description="Configurez vos alertes pour Twitch et TikTok.",
            color=discord.Color.from_str("#5865F2")
        )
        if channel_id:
            embed.add_field(name="Salon par défaut", value=f"<#{channel_id}>", inline=False)
        else:
            embed.add_field(name="Salon par défaut", value="⚠️ Aucun salon défini. Sélectionnez-en un ci-dessous.", inline=False)
        
        twitch_feeds = [f for f in feeds if f["platform"] == "twitch"]
        tiktok_feeds = [f for f in feeds if f["platform"] == "tiktok"]
        
        embed.add_field(name="<:twitch:11200> Twitch", value=f"{len(twitch_feeds)} suivis", inline=True)
        embed.add_field(name="🎵 TikTok", value=f"{len(tiktok_feeds)} suivis", inline=True)

        self.clear_items()
        
        channel_select = discord.ui.ChannelSelect(placeholder="Définir le salon par défaut...", channel_types=[discord.ChannelType.text], row=0)
        async def channel_callback(inter: discord.Interaction):
            await self.cog.bot.db.set_notification_channel(inter.guild_id, channel_select.values[0].id)
            await self.init(inter)
        channel_select.callback = channel_callback
        self.add_item(channel_select)

        btn_twitch = discord.ui.Button(label="Ajouter Twitch", style=discord.ButtonStyle.primary, row=1)
        async def twitch_callback(inter: discord.Interaction):
            await inter.response.send_modal(AddFeedModal(self.cog, "twitch", self))
        btn_twitch.callback = twitch_callback
        self.add_item(btn_twitch)

        btn_tiktok = discord.ui.Button(label="Ajouter TikTok", style=discord.ButtonStyle.danger, emoji="🎵", row=1)
        async def tiktok_callback(inter: discord.Interaction):
            await inter.response.send_modal(AddFeedModal(self.cog, "tiktok", self))
        btn_tiktok.callback = tiktok_callback
        self.add_item(btn_tiktok)

        if feeds:
            opts = []
            for f in feeds[:25]:
                emoji = "🟣" if f["platform"] == "twitch" else "🎵"
                opts.append(discord.SelectOption(label=f["username"], value=str(f["id"]), emoji=emoji, description=f["platform"].capitalize()))
            feed_select = discord.ui.Select(placeholder="Gérer un compte suivi...", options=opts, row=2)
            async def feed_callback(inter: discord.Interaction):
                feed_id = int(feed_select.values[0])
                feed = next(f for f in feeds if f["id"] == feed_id)
                view = FeedEditView(self.cog, feed)
                await view.init(inter)
            feed_select.callback = feed_callback
            self.add_item(feed_select)

        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.send_message(embed=embed, view=self, ephemeral=True)


class AddFeedModal(discord.ui.Modal):
    def __init__(self, cog: Notifications, platform: str, dashboard_view: NotifDashboardView):
        super().__init__(title="Ajouter Twitch" if platform == "twitch" else "Ajouter TikTok")
        self.cog = cog
        self.platform = platform
        self.dashboard_view = dashboard_view
        self.username = discord.ui.TextInput(
            label="Nom d'utilisateur",
            style=discord.TextStyle.short,
            required=True
        )
        self.add_item(self.username)

    async def on_submit(self, interaction: discord.Interaction):
        nom = self.username.value.lower().strip().lstrip("@")
        lang = await self.cog.bot.db.get_guild_lang(interaction.guild_id)

        channel_id = await self.cog.bot.db.get_notification_channel(interaction.guild_id)
        if not channel_id:
            return await interaction.response.send_message(embed=error_embed(t(lang, "notif.no_channel")), ephemeral=True)

        if self.platform == "twitch":
            if not self.cog.twitch.configured:
                return await interaction.response.send_message(embed=error_embed(t(lang, "notif.twitch_not_configured")), ephemeral=True)
            users = await self.cog.twitch.get_users([nom])
            if not users:
                return await interaction.response.send_message(embed=error_embed(t(lang, "notif.twitch_user_not_found", user=nom)), ephemeral=True)
        else:
            await interaction.response.defer(ephemeral=True)
            post = await self.cog.tiktok.get_latest_post(nom)

        existing = await self.cog.bot.db.get_notification_feeds(interaction.guild_id)
        for f in existing:
            if f["platform"] == self.platform and f["username"] == nom:
                msg = error_embed(t(lang, "notif.already_tracking", user=nom, platform=self.platform.capitalize()))
                return await interaction.followup.send(embed=msg) if interaction.response.is_done() else await interaction.response.send_message(embed=msg, ephemeral=True)

        await self.cog.bot.db.add_notification_feed(interaction.guild_id, channel_id, self.platform, nom)

        guild_state = self.cog._state.setdefault(interaction.guild_id, {"twitch": {}, "tiktok": {}})
        if self.platform == "twitch":
            streams = await self.cog.twitch.get_streams([nom])
            guild_state["twitch"][nom] = bool(streams)
        else:
            if post:
                guild_state["tiktok"][nom] = post["link"]

        if not interaction.response.is_done():
            await interaction.response.defer()
            
        await self.dashboard_view.init(interaction)


class FeedEditView(discord.ui.View):
    def __init__(self, cog: Notifications, feed: dict):
        super().__init__(timeout=300)
        self.cog = cog
        self.feed = feed

    async def init(self, interaction: discord.Interaction):
        feeds = await self.cog.bot.db.get_notification_feeds(interaction.guild_id)
        try:
            self.feed = next(f for f in feeds if f["id"] == self.feed["id"])
        except StopIteration:
            view = NotifDashboardView(self.cog)
            return await view.init(interaction)

        embed = discord.Embed(
            title=f"Configuration de {self.feed['username']} ({self.feed['platform'].capitalize()})",
            color=discord.Color.from_str(self.feed.get("embed_color") or ("#9146FF" if self.feed["platform"]=="twitch" else "#FE2C55"))
        )
        embed.add_field(name="Salon", value=f"<#{self.feed['channel_id']}>", inline=True)
        embed.add_field(name="Ping Rôle", value=f"<@&{self.feed['ping_role_id']}>" if self.feed.get("ping_role_id") else "Aucun", inline=True)
        embed.add_field(name="Couleur", value=self.feed.get("embed_color") or "Par défaut", inline=True)
        
        msg = self.feed.get("message") or "Par défaut"
        embed.add_field(name="Message", value=f"```{msg}```" if len(msg) < 1000 else "Message trop long...", inline=False)

        self.clear_items()

        btn_back = discord.ui.Button(label="Retour", style=discord.ButtonStyle.secondary, row=0, emoji="🔙")
        async def back_cb(inter: discord.Interaction):
            view = NotifDashboardView(self.cog)
            await view.init(inter)
        btn_back.callback = back_cb
        self.add_item(btn_back)

        btn_delete = discord.ui.Button(label="Supprimer le suivi", style=discord.ButtonStyle.danger, row=0, emoji="🗑️")
        async def del_cb(inter: discord.Interaction):
            await self.cog.bot.db.remove_notification_feed(inter.guild_id, self.feed["platform"], self.feed["username"])
            guild_state = self.cog._state.get(inter.guild_id, {})
            guild_state.get(self.feed["platform"], {}).pop(self.feed["username"], None)
            view = NotifDashboardView(self.cog)
            await view.init(inter)
        btn_delete.callback = del_cb
        self.add_item(btn_delete)

        btn_msg = discord.ui.Button(label="Message", style=discord.ButtonStyle.primary, row=1, emoji="📝")
        async def msg_cb(inter: discord.Interaction):
            await inter.response.send_modal(EditMessageModal(self.cog, self.feed, self))
        btn_msg.callback = msg_cb
        self.add_item(btn_msg)

        btn_color = discord.ui.Button(label="Couleur", style=discord.ButtonStyle.primary, row=1, emoji="🎨")
        async def color_cb(inter: discord.Interaction):
            await inter.response.send_modal(EditColorModal(self.cog, self.feed, self))
        btn_color.callback = color_cb
        self.add_item(btn_color)

        channel_select = discord.ui.ChannelSelect(placeholder="Changer le salon de ce suivi...", channel_types=[discord.ChannelType.text], row=2)
        async def ch_cb(inter: discord.Interaction):
            await self.cog.bot.db.update_notification_channel(inter.guild_id, self.feed["platform"], self.feed["username"], channel_select.values[0].id)
            await self.init(inter)
        channel_select.callback = ch_cb
        self.add_item(channel_select)

        role_select = discord.ui.RoleSelect(placeholder="Changer le rôle à ping...", row=3)
        async def role_cb(inter: discord.Interaction):
            await self.cog.bot.db.update_notification_role(inter.guild_id, self.feed["platform"], self.feed["username"], role_select.values[0].id)
            await self.init(inter)
        role_select.callback = role_cb
        self.add_item(role_select)
        
        if self.feed.get("ping_role_id"):
            btn_rm_role = discord.ui.Button(label="Retirer le ping", style=discord.ButtonStyle.secondary, row=4)
            async def rm_role_cb(inter: discord.Interaction):
                await self.cog.bot.db.update_notification_role(inter.guild_id, self.feed["platform"], self.feed["username"], None)
                await self.init(inter)
            btn_rm_role.callback = rm_role_cb
            self.add_item(btn_rm_role)

        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.send_message(embed=embed, view=self, ephemeral=True)


class EditMessageModal(discord.ui.Modal, title="Modifier le message"):
    msg = discord.ui.TextInput(label="Message", style=discord.TextStyle.paragraph, required=False, max_length=2000)

    def __init__(self, cog: Notifications, feed: dict, edit_view: FeedEditView):
        super().__init__()
        self.cog = cog
        self.feed = feed
        self.edit_view = edit_view
        if feed.get("message"):
            self.msg.default = feed["message"]

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.bot.db.update_notification_message(self.feed["id"], self.msg.value.strip() or None)
        await self.edit_view.init(interaction)

class EditColorModal(discord.ui.Modal, title="Modifier la couleur"):
    color = discord.ui.TextInput(label="Couleur Hex (#FFFFFF)", style=discord.TextStyle.short, required=False, max_length=7)

    def __init__(self, cog: Notifications, feed: dict, edit_view: FeedEditView):
        super().__init__()
        self.cog = cog
        self.feed = feed
        self.edit_view = edit_view
        if feed.get("embed_color"):
            self.color.default = feed["embed_color"]

    async def on_submit(self, interaction: discord.Interaction):
        val = self.color.value.strip() or None
        if val and not val.startswith("#"):
            val = "#" + val
        if val:
            try:
                discord.Color.from_str(val)
            except ValueError:
                return await interaction.response.send_message("❌ Couleur invalide.", ephemeral=True)
                
        await self.cog.bot.db.update_notification_color(interaction.guild_id, self.feed["platform"], self.feed["username"], val)
        await self.edit_view.init(interaction)


async def setup(bot: commands.Bot):
    await bot.add_cog(Notifications(bot))
