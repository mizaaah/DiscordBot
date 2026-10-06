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

    # ── Slash commands ────────────────────────────────────────────────────────

    notif_group = app_commands.Group(
        name="notifications",
        description="Notifications Twitch & TikTok",
    )

    @notif_group.command(name="setup", description="Définir le salon de notifications")
    @app_commands.describe(salon="Le salon où envoyer les notifications")
    @app_commands.default_permissions(manage_guild=True)
    async def notif_setup(self, interaction: discord.Interaction, salon: discord.TextChannel):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        await self.bot.db.set_notification_channel(interaction.guild_id, salon.id)
        embed = discord.Embed(
            title=t(lang, "notif.setup_title"),
            description=t(lang, "notif.setup_desc", channel=salon.mention),
            color=discord.Color.from_str("#5865F2"),
        )
        embed.set_footer(text=t(lang, "notif.setup_footer"))
        await interaction.response.send_message(embed=embed)

    @notif_group.command(name="twitch", description="Ajouter un streamer Twitch à suivre")
    @app_commands.describe(nom="Le nom du streamer Twitch (login)")
    @app_commands.default_permissions(manage_guild=True)
    async def notif_twitch(self, interaction: discord.Interaction, nom: str):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)

        if not self.twitch.configured:
            return await interaction.response.send_message(
                embed=error_embed(t(lang, "notif.twitch_not_configured")), ephemeral=True
            )

        # Vérifier que le salon est configuré
        channel_id = await self.bot.db.get_notification_channel(interaction.guild_id)
        if not channel_id:
            return await interaction.response.send_message(
                embed=error_embed(t(lang, "notif.no_channel")), ephemeral=True
            )

        nom = nom.lower().strip().lstrip("@")

        # Vérifier que le streamer existe
        users = await self.twitch.get_users([nom])
        if not users:
            return await interaction.response.send_message(
                embed=error_embed(t(lang, "notif.twitch_user_not_found", user=nom)), ephemeral=True
            )

        # Vérifier les doublons
        existing = await self.bot.db.get_notification_feeds(interaction.guild_id)
        for f in existing:
            if f["platform"] == "twitch" and f["username"] == nom:
                return await interaction.response.send_message(
                    embed=error_embed(t(lang, "notif.already_tracking", user=nom, platform="Twitch")),
                    ephemeral=True,
                )

        await self.bot.db.add_notification_feed(interaction.guild_id, channel_id, "twitch", nom)

        # Init l'état
        guild_state = self._state.setdefault(interaction.guild_id, {"twitch": {}, "tiktok": {}})
        streams = await self.twitch.get_streams([nom])
        guild_state["twitch"][nom] = bool(streams)

        user_info = users[0]
        embed = discord.Embed(
            title=t(lang, "notif.twitch_added_title"),
            description=t(lang, "notif.twitch_added_desc", user=user_info.get("display_name", nom)),
            color=TWITCH_COLOR,
        )
        if user_info.get("profile_image_url"):
            embed.set_thumbnail(url=user_info["profile_image_url"])
        embed.set_footer(text=t(lang, "notif.check_interval"))

        await interaction.response.send_message(embed=embed)

    @notif_group.command(name="tiktok", description="Ajouter un compte TikTok à suivre")
    @app_commands.describe(nom="Le nom d'utilisateur TikTok")
    @app_commands.default_permissions(manage_guild=True)
    async def notif_tiktok(self, interaction: discord.Interaction, nom: str):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)

        channel_id = await self.bot.db.get_notification_channel(interaction.guild_id)
        if not channel_id:
            return await interaction.response.send_message(
                embed=error_embed(t(lang, "notif.no_channel")), ephemeral=True
            )

        nom = nom.lower().strip().lstrip("@")

        # Vérifier les doublons
        existing = await self.bot.db.get_notification_feeds(interaction.guild_id)
        for f in existing:
            if f["platform"] == "tiktok" and f["username"] == nom:
                return await interaction.response.send_message(
                    embed=error_embed(t(lang, "notif.already_tracking", user=nom, platform="TikTok")),
                    ephemeral=True,
                )

        await interaction.response.defer()

        # Tester que le RSS fonctionne
        post = await self.tiktok.get_latest_post(nom)

        await self.bot.db.add_notification_feed(interaction.guild_id, channel_id, "tiktok", nom)

        # Init l'état
        guild_state = self._state.setdefault(interaction.guild_id, {"twitch": {}, "tiktok": {}})
        if post:
            guild_state["tiktok"][nom] = post["link"]

        embed = discord.Embed(
            title=t(lang, "notif.tiktok_added_title"),
            description=t(lang, "notif.tiktok_added_desc", user=nom),
            color=TIKTOK_COLOR,
        )

        if not post:
            embed.add_field(
                name="⚠️",
                value=t(lang, "notif.tiktok_rss_warning"),
                inline=False,
            )

        embed.set_footer(text=t(lang, "notif.check_interval"))
        await interaction.followup.send(embed=embed)

    @notif_group.command(name="remove", description="Retirer un suivi de notifications")
    @app_commands.describe(plateforme="twitch ou tiktok", nom="Le nom d'utilisateur")
    @app_commands.choices(plateforme=[
        app_commands.Choice(name="Twitch", value="twitch"),
        app_commands.Choice(name="TikTok", value="tiktok"),
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def notif_remove(self, interaction: discord.Interaction, plateforme: str, nom: str):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        nom = nom.lower().strip().lstrip("@")

        removed = await self.bot.db.remove_notification_feed(interaction.guild_id, plateforme, nom)
        if not removed:
            return await interaction.response.send_message(
                embed=error_embed(t(lang, "notif.not_tracking", user=nom, platform=plateforme.capitalize())),
                ephemeral=True,
            )

        # Clean state
        guild_state = self._state.get(interaction.guild_id, {})
        guild_state.get(plateforme, {}).pop(nom, None)

        await interaction.response.send_message(
            embed=success_embed(t(lang, "notif.removed", user=nom, platform=plateforme.capitalize()))
        )

    @notif_group.command(name="list", description="Voir les comptes suivis")
    @app_commands.default_permissions(manage_guild=True)
    async def notif_list(self, interaction: discord.Interaction):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        feeds = await self.bot.db.get_notification_feeds(interaction.guild_id)

        if not feeds:
            return await interaction.response.send_message(
                embed=info_embed(t(lang, "notif.empty_list")), ephemeral=True
            )

        twitch_feeds = [f for f in feeds if f["platform"] == "twitch"]
        tiktok_feeds = [f for f in feeds if f["platform"] == "tiktok"]

        embed = discord.Embed(
            title=t(lang, "notif.list_title"),
            color=discord.Color.from_str("#5865F2"),
        )

        if twitch_feeds:
            lines = []
            for f in twitch_feeds:
                ch = interaction.guild.get_channel(f["channel_id"])
                ch_text = ch.mention if ch else f"<#{f['channel_id']}>"
                status = self._state.get(interaction.guild_id, {}).get("twitch", {}).get(f["username"])
                indicator = "🔴" if status else "⚫"
                lines.append(f"{indicator} [`{f['username']}`](https://twitch.tv/{f['username']}) → {ch_text}")
            embed.add_field(
                name=f"<:twitch:> Twitch ({len(twitch_feeds)})",
                value="\n".join(lines),
                inline=False,
            )

        if tiktok_feeds:
            lines = []
            for f in tiktok_feeds:
                ch = interaction.guild.get_channel(f["channel_id"])
                ch_text = ch.mention if ch else f"<#{f['channel_id']}>"
                lines.append(f"🎵 [`@{f['username']}`](https://tiktok.com/@{f['username']}) → {ch_text}")
            embed.add_field(
                name=f"🎵 TikTok ({len(tiktok_feeds)})",
                value="\n".join(lines),
                inline=False,
            )

        embed.set_footer(text=t(lang, "notif.check_interval"))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @notif_group.command(name="message", description="Personnaliser le message de notification")
    @app_commands.describe(
        plateforme="twitch ou tiktok",
        texte="Variables : {user} {url} {title} {game} (Twitch seulement)"
    )
    @app_commands.choices(plateforme=[
        app_commands.Choice(name="Twitch", value="twitch"),
        app_commands.Choice(name="TikTok", value="tiktok"),
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def notif_message(self, interaction: discord.Interaction, plateforme: str, texte: str):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)

        feeds = await self.bot.db.get_notification_feeds(interaction.guild_id)
        platform_feeds = [f for f in feeds if f["platform"] == plateforme]

        if not platform_feeds:
            return await interaction.response.send_message(
                embed=error_embed(t(lang, "notif.no_feeds_for_platform", platform=plateforme.capitalize())),
                ephemeral=True,
            )

        # Appliquer à tous les feeds de cette plateforme
        for f in platform_feeds:
            await self.bot.db.update_notification_message(f["id"], texte)

        await interaction.response.send_message(
            embed=success_embed(t(lang, "notif.message_updated", platform=plateforme.capitalize(), text=texte)),
            ephemeral=True,
        )

    @notif_group.command(name="channel", description="Changer le salon d'un suivi spécifique")
    @app_commands.describe(
        plateforme="twitch ou tiktok",
        nom="Le nom d'utilisateur",
        salon="Le nouveau salon",
    )
    @app_commands.choices(plateforme=[
        app_commands.Choice(name="Twitch", value="twitch"),
        app_commands.Choice(name="TikTok", value="tiktok"),
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def notif_channel(self, interaction: discord.Interaction, plateforme: str, nom: str, salon: discord.TextChannel):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        nom = nom.lower().strip().lstrip("@")

        updated = await self.bot.db.update_notification_channel(interaction.guild_id, plateforme, nom, salon.id)
        if not updated:
            return await interaction.response.send_message(
                embed=error_embed(t(lang, "notif.not_tracking", user=nom, platform=plateforme.capitalize())),
                ephemeral=True,
            )

        await interaction.response.send_message(
            embed=success_embed(t(lang, "notif.channel_updated", user=nom, channel=salon.mention))
        )

    @notif_group.command(name="role", description="Ajouter ou retirer un rôle à ping pour un suivi")
    @app_commands.describe(
        plateforme="twitch ou tiktok",
        nom="Le nom d'utilisateur",
        role="Le rôle à ping (laisse vide pour retirer le ping)"
    )
    @app_commands.choices(plateforme=[
        app_commands.Choice(name="Twitch", value="twitch"),
        app_commands.Choice(name="TikTok", value="tiktok"),
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def notif_role(self, interaction: discord.Interaction, plateforme: str, nom: str, role: discord.Role = None):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        nom = nom.lower().strip().lstrip("@")

        updated = await self.bot.db.update_notification_role(interaction.guild_id, plateforme, nom, role.id if role else None)
        if not updated:
            return await interaction.response.send_message(
                embed=error_embed(t(lang, "notif.not_tracking", user=nom, platform=plateforme.capitalize())),
                ephemeral=True,
            )

        if role:
            await interaction.response.send_message(
                embed=success_embed(t(lang, "notif.role_updated", user=nom, role=role.mention))
            )
        else:
            await interaction.response.send_message(
                embed=success_embed(t(lang, "notif.role_removed", user=nom))
            )

    @notif_group.command(name="color", description="Modifier la couleur de l'embed pour un suivi")
    @app_commands.describe(
        plateforme="twitch ou tiktok",
        nom="Le nom d'utilisateur",
        couleur="Code couleur Hex (ex: #FF0000, laisse vide pour reset)"
    )
    @app_commands.choices(plateforme=[
        app_commands.Choice(name="Twitch", value="twitch"),
        app_commands.Choice(name="TikTok", value="tiktok"),
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def notif_color(self, interaction: discord.Interaction, plateforme: str, nom: str, couleur: str = None):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        nom = nom.lower().strip().lstrip("@")
        
        if couleur and not couleur.startswith("#"):
            couleur = f"#{couleur}"

        # Validate color
        if couleur:
            try:
                discord.Color.from_str(couleur)
            except ValueError:
                return await interaction.response.send_message(
                    embed=error_embed(t(lang, "notif.invalid_color", color=couleur)),
                    ephemeral=True
                )

        updated = await self.bot.db.update_notification_color(interaction.guild_id, plateforme, nom, couleur)
        if not updated:
            return await interaction.response.send_message(
                embed=error_embed(t(lang, "notif.not_tracking", user=nom, platform=plateforme.capitalize())),
                ephemeral=True,
            )

        if couleur:
            await interaction.response.send_message(
                embed=success_embed(t(lang, "notif.color_updated", user=nom, color=couleur))
            )
        else:
            await interaction.response.send_message(
                embed=success_embed(t(lang, "notif.color_removed", user=nom))
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Notifications(bot))
