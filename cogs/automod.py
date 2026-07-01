import re
import time
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands
from utils.colors import Colors

INVITE_REGEX = re.compile(r"discord(?:\.gg|app\.com/invite)/[a-zA-Z0-9-]+", re.IGNORECASE)
URL_REGEX = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.IGNORECASE)


def _extract_domain(url: str) -> str:
    if not url.lower().startswith(("http://", "https://")):
        url = "http://" + url
    netloc = urlparse(url).netloc.lower().split(":")[0]
    return netloc[4:] if netloc.startswith("www.") else netloc

ACTION_CHOICES = [
    app_commands.Choice(name="Avertir", value="warn"),
    app_commands.Choice(name="Muter 10 min", value="mute"),
    app_commands.Choice(name="Expulser", value="kick"),
    app_commands.Choice(name="Bannir", value="ban"),
]


class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._timestamps: dict[tuple, deque] = defaultdict(lambda: deque())
        self._contents: dict[tuple, deque] = defaultdict(lambda: deque(maxlen=10))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _should_bypass(self, member: discord.Member, bypass_roles: list) -> bool:
        if member.guild_permissions.manage_messages:
            return True
        return any(r.id in bypass_roles for r in member.roles)

    async def _apply_action(self, message: discord.Message, action: str, reason: str):
        member = message.author
        guild = message.guild

        try:
            await message.delete()
        except discord.HTTPException:
            pass

        try:
            await member.send(
                f"⚠️ **AutoMod** — **{guild.name}**\n**Raison :** {reason}"
            )
        except discord.Forbidden:
            pass

        if action == "warn":
            warn_id = await self.bot.db.add_warning(guild.id, member.id, self.bot.user.id, f"[AutoMod] {reason}")
            total = await self.bot.db.get_warning_count(guild.id, member.id)
            try:
                await message.channel.send(
                    f"⚠️ {member.mention} | Avertissement automatique (`{total}` warn(s)).",
                    delete_after=6
                )
            except discord.Forbidden:
                pass
            if logs := self.bot.get_cog("Logs"):
                embed = discord.Embed(title="🤖 AutoMod — Warn", color=Colors.CAUTION)
                embed.add_field(name="Membre", value=f"{member.mention} (`{member.id}`)", inline=True)
                embed.add_field(name="Raison", value=reason, inline=False)
                embed.set_footer(text=f"ID warn : #{warn_id}")
                await logs.send_log(guild, embed)

        elif action == "mute":
            until = datetime.now(timezone.utc) + timedelta(minutes=10)
            try:
                await member.timeout(until, reason=f"[AutoMod] {reason}")
                await message.channel.send(
                    f"🔇 {member.mention} muté automatiquement (10 min).", delete_after=6
                )
            except discord.Forbidden:
                pass
            if logs := self.bot.get_cog("Logs"):
                embed = discord.Embed(title="🤖 AutoMod — Mute", color=Colors.WARNING)
                embed.add_field(name="Membre", value=f"{member.mention} (`{member.id}`)", inline=True)
                embed.add_field(name="Durée", value="10 minutes", inline=True)
                embed.add_field(name="Raison", value=reason, inline=False)
                await logs.send_log(guild, embed)

        elif action == "kick":
            try:
                await member.kick(reason=f"[AutoMod] {reason}")
            except discord.Forbidden:
                pass
            if logs := self.bot.get_cog("Logs"):
                embed = discord.Embed(title="🤖 AutoMod — Kick", color=Colors.ERROR)
                embed.add_field(name="Membre", value=f"{member.mention} (`{member.id}`)", inline=True)
                embed.add_field(name="Raison", value=reason, inline=False)
                await logs.send_log(guild, embed)

        elif action == "ban":
            try:
                await member.ban(reason=f"[AutoMod] {reason}", delete_message_days=0)
            except discord.Forbidden:
                pass
            if logs := self.bot.get_cog("Logs"):
                embed = discord.Embed(title="🤖 AutoMod — Ban", color=Colors.DANGER)
                embed.add_field(name="Membre", value=f"{member.mention} (`{member.id}`)", inline=True)
                embed.add_field(name="Raison", value=reason, inline=False)
                await logs.send_log(guild, embed)

    # ── Listener ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if not isinstance(message.author, discord.Member):
            return

        config = await self.bot.db.get_automod_config(message.guild.id)
        if not config.get("enabled", True):
            return

        bypass_roles = config.get("bypass_roles") or []
        if self._should_bypass(message.author, bypass_roles):
            return

        key = (message.guild.id, message.author.id)
        now = time.monotonic()

        # ── Anti-spam ────────────────────────────────────────────────────────
        if config.get("spam_enabled", True):
            threshold = config["spam_threshold"]
            window = config["spam_window"]
            self._timestamps[key].append(now)
            while self._timestamps[key] and now - self._timestamps[key][0] > window:
                self._timestamps[key].popleft()
            if len(self._timestamps[key]) >= threshold:
                self._timestamps[key].clear()
                await self._apply_action(message, config["spam_action"], "Spam de messages détecté")
                return

        # ── Anti-flood ───────────────────────────────────────────────────────
        if config.get("flood_enabled", True):
            flood_threshold = config["flood_threshold"]
            self._contents[key].append(message.content.lower().strip())
            recent = list(self._contents[key])
            if len(recent) >= flood_threshold and len(set(recent[-flood_threshold:])) == 1:
                self._contents[key].clear()
                await self._apply_action(message, config["flood_action"], "Messages identiques répétés (flood)")
                return

        # ── Anti-invites ──────────────────────────────────────────────────────
        if config.get("invite_enabled", False):
            if INVITE_REGEX.search(message.content):
                await self._apply_action(message, config["invite_action"], "Lien d'invitation Discord non autorisé")
                return

        # ── Anti-liens ────────────────────────────────────────────────────────
        if config.get("link_enabled", False):
            urls = URL_REGEX.findall(message.content)
            if urls:
                whitelist = set(config.get("link_whitelist") or [])
                if any(_extract_domain(u) not in whitelist for u in urls):
                    await self._apply_action(message, config["link_action"], "Lien non autorisé")
                    return

        # ── Anti-caps ─────────────────────────────────────────────────────────
        if config.get("caps_enabled", False):
            content = message.content
            min_len = config["caps_min_length"]
            threshold = config["caps_threshold"]
            if len(content) >= min_len:
                letters = [c for c in content if c.isalpha()]
                if letters:
                    pct = sum(1 for c in letters if c.isupper()) / len(letters) * 100
                    if pct >= threshold:
                        await self._apply_action(message, config["caps_action"], f"Excès de majuscules ({pct:.0f}%)")
                        return

        # ── Anti-mention ──────────────────────────────────────────────────────
        if config.get("mention_enabled", False):
            threshold = config["mention_threshold"]
            total_mentions = len(message.mentions) + len(message.role_mentions)
            if total_mentions >= threshold:
                await self._apply_action(
                    message, config["mention_action"],
                    f"Mentions massives ({total_mentions} mentions)"
                )
                return

    # ── Slash commands ────────────────────────────────────────────────────────

    automod_group = app_commands.Group(name="automod", description="Configuration de l'auto-modération")

    @automod_group.command(name="status", description="Affiche la configuration de l'auto-modération")
    @app_commands.default_permissions(manage_guild=True)
    async def automod_status(self, interaction: discord.Interaction):
        config = await self.bot.db.get_automod_config(interaction.guild.id)

        def status(enabled: bool) -> str:
            return "✅ Activé" if enabled else "❌ Désactivé"

        embed = discord.Embed(
            title="🤖 AutoMod — Configuration",
            color=Colors.INFO
        )
        embed.add_field(name="Statut global", value=status(config["enabled"]), inline=False)
        embed.add_field(
            name="🔁 Anti-spam",
            value=f"{status(config['spam_enabled'])} | {config['spam_threshold']} msgs / {config['spam_window']}s | Action : `{config['spam_action']}`",
            inline=False
        )
        embed.add_field(
            name="📋 Anti-flood",
            value=f"{status(config['flood_enabled'])} | {config['flood_threshold']} msgs identiques | Action : `{config['flood_action']}`",
            inline=False
        )
        embed.add_field(
            name="🔗 Anti-invites",
            value=f"{status(config['invite_enabled'])} | Action : `{config['invite_action']}`",
            inline=False
        )
        whitelist = config.get("link_whitelist") or []
        embed.add_field(
            name="🌐 Anti-liens",
            value=f"{status(config['link_enabled'])} | Action : `{config['link_action']}` | Whitelist : {len(whitelist)} domaine(s)",
            inline=False
        )
        embed.add_field(
            name="🔠 Anti-caps",
            value=f"{status(config['caps_enabled'])} | >{config['caps_threshold']}% caps (min {config['caps_min_length']} chars) | Action : `{config['caps_action']}`",
            inline=False
        )
        embed.add_field(
            name="📢 Anti-mentions",
            value=f"{status(config['mention_enabled'])} | >{config['mention_threshold']} mentions | Action : `{config['mention_action']}`",
            inline=False
        )
        bypass = config.get("bypass_roles") or []
        bypass_str = " ".join(f"<@&{r}>" for r in bypass) if bypass else "Aucun"
        embed.add_field(name="Rôles ignorés", value=bypass_str, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @automod_group.command(name="toggle", description="Active ou désactive l'AutoMod globalement")
    @app_commands.describe(activer="Activer ou désactiver")
    @app_commands.default_permissions(manage_guild=True)
    async def automod_toggle(self, interaction: discord.Interaction, activer: bool):
        await self.bot.db.update_automod_setting(interaction.guild.id, "enabled", activer)
        state = "activé ✅" if activer else "désactivé ❌"
        await interaction.response.send_message(f"🤖 AutoMod {state}.")

    @automod_group.command(name="spam", description="Configure la détection de spam")
    @app_commands.describe(
        activer="Activer/désactiver",
        seuil="Nombre de messages déclenchant le spam (défaut : 5)",
        fenetre="Fenêtre de temps en secondes (défaut : 5)",
        action="Action à effectuer"
    )
    @app_commands.choices(action=ACTION_CHOICES)
    @app_commands.default_permissions(manage_guild=True)
    async def automod_spam(self, interaction: discord.Interaction, activer: bool, seuil: int = 5, fenetre: int = 5, action: str = "mute"):
        db = self.bot.db
        gid = interaction.guild.id
        await db.update_automod_setting(gid, "spam_enabled", activer)
        await db.update_automod_setting(gid, "spam_threshold", seuil)
        await db.update_automod_setting(gid, "spam_window", fenetre)
        await db.update_automod_setting(gid, "spam_action", action)
        state = "activé ✅" if activer else "désactivé ❌"
        await interaction.response.send_message(
            f"🔁 Anti-spam {state} | {seuil} msgs / {fenetre}s → `{action}`"
        )

    @automod_group.command(name="flood", description="Configure la détection de flood (messages identiques)")
    @app_commands.describe(activer="Activer/désactiver", seuil="Nombre de répétitions (défaut : 3)", action="Action à effectuer")
    @app_commands.choices(action=ACTION_CHOICES)
    @app_commands.default_permissions(manage_guild=True)
    async def automod_flood(self, interaction: discord.Interaction, activer: bool, seuil: int = 3, action: str = "warn"):
        db = self.bot.db
        gid = interaction.guild.id
        await db.update_automod_setting(gid, "flood_enabled", activer)
        await db.update_automod_setting(gid, "flood_threshold", seuil)
        await db.update_automod_setting(gid, "flood_action", action)
        state = "activé ✅" if activer else "désactivé ❌"
        await interaction.response.send_message(
            f"📋 Anti-flood {state} | {seuil} messages identiques → `{action}`"
        )

    @automod_group.command(name="invites", description="Configure le filtre d'invitations Discord")
    @app_commands.describe(activer="Activer/désactiver", action="Action à effectuer")
    @app_commands.choices(action=ACTION_CHOICES)
    @app_commands.default_permissions(manage_guild=True)
    async def automod_invites(self, interaction: discord.Interaction, activer: bool, action: str = "warn"):
        db = self.bot.db
        gid = interaction.guild.id
        await db.update_automod_setting(gid, "invite_enabled", activer)
        await db.update_automod_setting(gid, "invite_action", action)
        state = "activé ✅" if activer else "désactivé ❌"
        await interaction.response.send_message(f"🔗 Anti-invites {state} → `{action}`")

    @automod_group.command(name="links", description="Configure le filtre anti-liens (bloque toutes les URLs)")
    @app_commands.describe(activer="Activer/désactiver", action="Action à effectuer")
    @app_commands.choices(action=ACTION_CHOICES)
    @app_commands.default_permissions(manage_guild=True)
    async def automod_links(self, interaction: discord.Interaction, activer: bool, action: str = "warn"):
        db = self.bot.db
        gid = interaction.guild.id
        await db.update_automod_setting(gid, "link_enabled", activer)
        await db.update_automod_setting(gid, "link_action", action)
        state = "activé ✅" if activer else "désactivé ❌"
        await interaction.response.send_message(f"🌐 Anti-liens {state} → `{action}`")

    @automod_group.command(name="linkwhitelist", description="Ajoute ou retire un domaine autorisé par l'anti-liens")
    @app_commands.describe(domaine="Nom de domaine (ex: youtube.com)", action="Ajouter ou retirer")
    @app_commands.choices(action=[
        app_commands.Choice(name="Ajouter", value="add"),
        app_commands.Choice(name="Retirer", value="remove"),
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def automod_linkwhitelist(self, interaction: discord.Interaction, domaine: str, action: str):
        config = await self.bot.db.get_automod_config(interaction.guild.id)
        whitelist = list(config.get("link_whitelist") or [])
        domaine = domaine.lower().strip().removeprefix("www.")
        if action == "add":
            if domaine not in whitelist:
                whitelist.append(domaine)
            msg = f"✅ **{domaine}** ajouté à la whitelist des liens."
        else:
            whitelist = [d for d in whitelist if d != domaine]
            msg = f"✅ **{domaine}** retiré de la whitelist des liens."
        await self.bot.db.update_automod_setting(interaction.guild.id, "link_whitelist", whitelist)
        await interaction.response.send_message(msg)

    @automod_group.command(name="caps", description="Configure le filtre anti-majuscules")
    @app_commands.describe(
        activer="Activer/désactiver",
        pourcentage="Seuil de majuscules en % pour déclencher (défaut : 70)",
        min_longueur="Longueur min du message pour vérifier (défaut : 10)",
        action="Action à effectuer"
    )
    @app_commands.choices(action=ACTION_CHOICES)
    @app_commands.default_permissions(manage_guild=True)
    async def automod_caps(self, interaction: discord.Interaction, activer: bool, pourcentage: int = 70, min_longueur: int = 10, action: str = "warn"):
        db = self.bot.db
        gid = interaction.guild.id
        await db.update_automod_setting(gid, "caps_enabled", activer)
        await db.update_automod_setting(gid, "caps_threshold", max(1, min(100, pourcentage)))
        await db.update_automod_setting(gid, "caps_min_length", min_longueur)
        await db.update_automod_setting(gid, "caps_action", action)
        state = "activé ✅" if activer else "désactivé ❌"
        await interaction.response.send_message(
            f"🔠 Anti-caps {state} | >{pourcentage}% (min {min_longueur} chars) → `{action}`"
        )

    @automod_group.command(name="mentions", description="Configure le filtre anti-mentions massives")
    @app_commands.describe(activer="Activer/désactiver", seuil="Nombre max de mentions (défaut : 5)", action="Action à effectuer")
    @app_commands.choices(action=ACTION_CHOICES)
    @app_commands.default_permissions(manage_guild=True)
    async def automod_mentions(self, interaction: discord.Interaction, activer: bool, seuil: int = 5, action: str = "mute"):
        db = self.bot.db
        gid = interaction.guild.id
        await db.update_automod_setting(gid, "mention_enabled", activer)
        await db.update_automod_setting(gid, "mention_threshold", seuil)
        await db.update_automod_setting(gid, "mention_action", action)
        state = "activé ✅" if activer else "désactivé ❌"
        await interaction.response.send_message(
            f"📢 Anti-mentions {state} | >{seuil} mentions → `{action}`"
        )

    @automod_group.command(name="bypass", description="Ajoute ou retire un rôle ignoré par l'AutoMod")
    @app_commands.describe(role="Le rôle", action="Ajouter ou retirer")
    @app_commands.choices(action=[
        app_commands.Choice(name="Ajouter", value="add"),
        app_commands.Choice(name="Retirer", value="remove"),
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def automod_bypass(self, interaction: discord.Interaction, role: discord.Role, action: str):
        config = await self.bot.db.get_automod_config(interaction.guild.id)
        bypass = list(config.get("bypass_roles") or [])
        if action == "add":
            if role.id not in bypass:
                bypass.append(role.id)
            msg = f"✅ {role.mention} ajouté aux rôles ignorés."
        else:
            bypass = [r for r in bypass if r != role.id]
            msg = f"✅ {role.mention} retiré des rôles ignorés."
        await self.bot.db.update_automod_setting(interaction.guild.id, "bypass_roles", bypass)
        await interaction.response.send_message(msg)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
