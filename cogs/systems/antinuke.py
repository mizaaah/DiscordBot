import discord
from discord.ext import commands, tasks
import time
from collections import defaultdict
from cogs.core.config import Colors

class AntiNuke(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Structure: tracker[guild_id][user_id][action_type] = [timestamps]
        # action_type can be: 'ban', 'kick', 'channel_delete', 'role_delete'
        self.tracker = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        self.cleanup_task.start()

    def cog_unload(self):
        self.cleanup_task.cancel()

    @tasks.loop(minutes=5)
    async def cleanup_task(self):
        # Nettoyer les timestamps vieux de plus de 60 secondes pour éviter la fuite de mémoire
        now = time.time()
        for guild_id in list(self.tracker.keys()):
            for user_id in list(self.tracker[guild_id].keys()):
                for action in list(self.tracker[guild_id][user_id].keys()):
                    self.tracker[guild_id][user_id][action] = [t for t in self.tracker[guild_id][user_id][action] if now - t <= 60]
                    if not self.tracker[guild_id][user_id][action]:
                        del self.tracker[guild_id][user_id][action]
                if not self.tracker[guild_id][user_id]:
                    del self.tracker[guild_id][user_id]
            if not self.tracker[guild_id]:
                del self.tracker[guild_id]

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        guild = entry.guild
        user = entry.user
        
        # Ignorer le bot lui-même et les actions du propriétaire du serveur
        if not user or user.bot or user.id == guild.owner_id:
            return

        config = await self.bot.db.get_antinuke_config(guild.id)
        if not config.get("enabled"):
            return

        # Vérifier si l'utilisateur a un rôle bypass
        bypass_roles = config.get("bypass_roles") or []
        if isinstance(user, discord.Member):
            if any(r.id in bypass_roles for r in user.roles):
                return

        action_type = None
        threshold = None

        if entry.action == discord.AuditLogAction.ban:
            action_type = "ban"
            threshold = config.get("ban_threshold", 3)
        elif entry.action == discord.AuditLogAction.kick:
            action_type = "kick"
            threshold = config.get("kick_threshold", 3)
        elif entry.action == discord.AuditLogAction.channel_delete:
            action_type = "channel_delete"
            threshold = config.get("channel_delete_threshold", 2)
        elif entry.action == discord.AuditLogAction.role_delete:
            action_type = "role_delete"
            threshold = config.get("role_delete_threshold", 2)

        if not action_type or not threshold:
            return

        now = time.time()
        self.tracker[guild.id][user.id][action_type].append(now)
        
        # Nettoyer uniquement cette liste
        self.tracker[guild.id][user.id][action_type] = [t for t in self.tracker[guild.id][user.id][action_type] if now - t <= 60]

        count = len(self.tracker[guild.id][user.id][action_type])
        
        if count >= threshold:
            await self.punish_user(guild, user, config, action_type, count)
            # Réinitialiser pour éviter de punir en boucle
            self.tracker[guild.id][user.id][action_type] = []

    async def punish_user(self, guild: discord.Guild, user: discord.Member | discord.User, config: dict, reason: str, count: int):
        action = config.get("action", "quarantine")
        
        # S'assurer que le bot peut agir sur l'utilisateur
        member = guild.get_member(user.id)
        if member and guild.me.top_role <= member.top_role:
            return # Ne peut pas punir quelqu'un avec un rôle plus haut ou égal

        success = False
        punishment_str = ""

        try:
            if action == "ban":
                await guild.ban(user, reason=f"Anti-Nuke: Limite de {reason} dépassée ({count}/min)")
                success = True
                punishment_str = "Bannissement"
            elif action == "kick" and member:
                await member.kick(reason=f"Anti-Nuke: Limite de {reason} dépassée ({count}/min)")
                success = True
                punishment_str = "Expulsion"
            elif action == "quarantine" and member:
                # Retirer tous les rôles sauf everyone
                roles_to_remove = [r for r in member.roles if r != guild.default_role and r.is_assignable()]
                if roles_to_remove:
                    await member.remove_roles(*roles_to_remove, reason=f"Anti-Nuke: Mise en quarantaine ({reason})")
                success = True
                punishment_str = "Quarantaine (Retrait des rôles)"
        except discord.Forbidden:
            success = False
            punishment_str = "Échec (Permissions insuffisantes)"

        # Alerte
        alert_channel_id = config.get("alert_channel_id")
        if alert_channel_id:
            alert_channel = guild.get_channel(alert_channel_id)
            if alert_channel:
                embed = discord.Embed(
                    title="⚠️ DÉTECTION ANTI-NUKE",
                    description=f"Le système Anti-Nuke a détecté un comportement suspect.",
                    color=Colors.ERROR.value
                )
                embed.add_field(name="Coupable", value=f"{user.mention} (`{user.id}`)", inline=False)
                action_fr = {
                    "ban": "Bannissements",
                    "kick": "Expulsions",
                    "channel_delete": "Suppressions de salons",
                    "role_delete": "Suppressions de rôles"
                }.get(reason, reason)
                embed.add_field(name="Action", value=f"Trop de **{action_fr}** ({count} en moins d'une minute)", inline=False)
                embed.add_field(name="Sanction", value=punishment_str, inline=False)
                embed.set_thumbnail(url=user.display_avatar.url)
                
                try:
                    await alert_channel.send(embed=embed)
                except discord.Forbidden:
                    pass

async def setup(bot: commands.Bot):
    await bot.add_cog(AntiNuke(bot))
