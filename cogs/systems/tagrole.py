import discord
from discord import app_commands
from discord.ext import commands, tasks
import logging
from utils.colors import Colors
from utils.embeds import success_embed, error_embed


def member_has_tag(member: discord.Member, tag: str, guild: discord.Guild) -> bool:
    """Vérifie si un membre porte le tag Discord Server/Clan, ou dans son pseudo / statut."""
    t = tag.lower().strip()
    if not t:
        return False

    # 1. Discord Server Clan / Guild Tag officiel (ex: mizaaah 🌙 17th)
    if hasattr(member, "primary_guild") and member.primary_guild:
        pg = member.primary_guild
        pg_tag = getattr(pg, "tag", None)
        if pg_tag and pg_tag.lower() == t:
            return True
        pg_id = getattr(pg, "id", None)
        if pg_id and pg_id == guild.id:
            return True

    # 2. Pseudo / Nom d'affichage
    if member.nick and t in member.nick.lower():
        return True
    if member.display_name and t in member.display_name.lower():
        return True

    # 3. Nom d'utilisateur global
    if member.name and t in member.name.lower():
        return True
    if getattr(member, "global_name", None) and t in member.global_name.lower():
        return True

    # 4. Statut personnalisé (Custom Activity)
    for act in getattr(member, "activities", []):
        if isinstance(act, discord.CustomActivity):
            if act.state and t in act.state.lower():
                return True
            if act.name and t in act.name.lower():
                return True

    return False


class TagRole(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._user_cache = {}
        self.periodic_sync.start()

    def cog_unload(self):
        self.periodic_sync.cancel()

    async def check_member_has_tag(self, member: discord.Member, tag: str, guild: discord.Guild, allow_fetch: bool = True) -> bool:
        """Vérifie la présence du tag avec fallback API fetch_user pour le Clan Tag Discord si nécessaire."""
        if member_has_tag(member, tag, guild):
            return True

        if not allow_fetch:
            return False

        t = tag.lower().strip()
        try:
            # Vérifier via l'API User (seul moyen garanti par Discord pour récupérer primary_guild / Clan tag)
            user = await self.bot.fetch_user(member.id)
            if user and hasattr(user, "primary_guild") and user.primary_guild:
                pg = user.primary_guild
                pg_tag = getattr(pg, "tag", None)
                if pg_tag and pg_tag.lower() == t:
                    return True
                pg_id = getattr(pg, "id", None)
                if pg_id and pg_id == guild.id:
                    return True
        except Exception:
            pass

        return False

    async def _sync_member(self, member: discord.Member, role_id: int, tag_text: str, allow_fetch: bool = True) -> str:
        """Ajoute ou retire le rôle selon la présence du tag. Retourne 'added', 'removed' ou None."""
        if not role_id or member.bot:
            return None

        guild = member.guild
        role = guild.get_role(role_id)
        if not role or not guild.me.guild_permissions.manage_roles:
            return None

        # Sécurité hiérarchie des rôles
        if guild.me.top_role <= role:
            return None

        should_have = await self.check_member_has_tag(member, tag_text, guild, allow_fetch=allow_fetch)
        has_role = role in member.roles

        try:
            if should_have and not has_role:
                await member.add_roles(role, reason=f"Tag '{tag_text}' détecté")
                return "added"
            elif not should_have and has_role:
                await member.remove_roles(role, reason=f"Tag '{tag_text}' non détecté")
                return "removed"
        except (discord.Forbidden, discord.HTTPException) as e:
            logging.debug(f"[TagRole] Erreur sync membre {member.id} : {e}")

        return None

    # ── Événements Discord ──────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if after.bot or not after.guild:
            return

        settings = await self.bot.db.get_guild_settings(after.guild.id)
        role_id = settings.get("tagrole_id")
        if not role_id:
            return

        tag_text = settings.get("tagrole_text") or "17th"
        await self._sync_member(after, role_id, tag_text)

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        if not isinstance(after, discord.Member) or after.bot or not after.guild:
            return

        settings = await self.bot.db.get_guild_settings(after.guild.id)
        role_id = settings.get("tagrole_id")
        if not role_id:
            return

        tag_text = settings.get("tagrole_text") or "17th"
        await self._sync_member(after, role_id, tag_text)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot or not member.guild:
            return

        settings = await self.bot.db.get_guild_settings(member.guild.id)
        role_id = settings.get("tagrole_id")
        if not role_id:
            return

        tag_text = settings.get("tagrole_text") or "17th"
        await self._sync_member(member, role_id, tag_text)

    # ── Synchronisation périodique ──────────────────────────────────────────

    @tasks.loop(minutes=20)
    async def periodic_sync(self):
        """Vérifie périodiquement les membres pour éviter toute désynchronisation."""
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            try:
                settings = await self.bot.db.get_guild_settings(guild.id)
                role_id = settings.get("tagrole_id")
                if not role_id:
                    continue

                tag_text = settings.get("tagrole_text") or "17th"
                role = guild.get_role(role_id)
                if not role or guild.me.top_role <= role:
                    continue

                for member in guild.members:
                    if not member.bot:
                        await self._sync_member(member, role_id, tag_text, allow_fetch=False)
            except Exception as e:
                logging.debug(f"[TagRole] Erreur loop sync guild {guild.id} : {e}")

    @periodic_sync.before_loop
    async def before_periodic_sync(self):
        await self.bot.wait_until_ready()

    # ── Commandes Slash ──────────────────────────────────────────────────────

    tagrole = app_commands.Group(name="tagrole", description="Gestion du rôle automatique lié au tag 17th")

    @tagrole.command(name="config", description="Configure le rôle attribué à ceux qui portent le tag")
    @app_commands.describe(
        role="Le rôle à donner automatiquement",
        tag="Le tag à surveiller (par défaut: 17th)"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def tagrole_config(self, interaction: discord.Interaction, role: discord.Role, tag: str = "17th"):
        if interaction.guild.me.top_role <= role:
            return await interaction.response.send_message(
                embed=error_embed("❌ Ce rôle est supérieur ou égal au rôle le plus élevé du bot."),
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)
        await self.bot.db.update_guild_setting(interaction.guild.id, "tagrole_id", role.id)
        await self.bot.db.update_guild_setting(interaction.guild.id, "tagrole_text", tag.strip())

        # Lancer un premier scan immédiat
        added = 0
        for m in interaction.guild.members:
            if not m.bot:
                res = await self._sync_member(m, role.id, tag.strip(), allow_fetch=False)
                if res == "added":
                    added += 1

        cont = discord.ui.Container(accent_color=Colors.SUCCESS.value)
        cont.add_item(discord.ui.TextDisplay(
            f"# 🏷️ Rôle Tag Configuré avec Succès !\n"
            f"> Le bot surveille désormais le tag `{tag.strip()}` en temps réel.\n\n"
            f"🎭 **Rôle associé :** {role.mention}\n"
            f"🏷️ **Tag recherché :** `{tag.strip()}`\n"
            f"✨ **Membres synchronisés immédiatement :** `{added}` nouveau(x) membre(s)"
        ))
        view = discord.ui.LayoutView()
        view.add_item(cont)
        await interaction.followup.send(view=view, ephemeral=True)

    @tagrole.command(name="disable", description="Désactive l'attribution automatique du rôle pour le tag")
    @app_commands.default_permissions(manage_guild=True)
    async def tagrole_disable(self, interaction: discord.Interaction):
        await self.bot.db.update_guild_setting(interaction.guild.id, "tagrole_id", None)
        await interaction.response.send_message("✅ Le système de rôle lié au tag a été **désactivé**.", ephemeral=True)

    @tagrole.command(name="status", description="Affiche l'état actuel et les statistiques du tag role")
    @app_commands.default_permissions(manage_guild=True)
    async def tagrole_status(self, interaction: discord.Interaction):
        settings = await self.bot.db.get_guild_settings(interaction.guild.id)
        role_id = settings.get("tagrole_id")
        tag_text = settings.get("tagrole_text") or "17th"

        role = interaction.guild.get_role(role_id) if role_id else None
        role_str = role.mention if role else "❌ Non configuré"

        tag_count = 0
        role_count = len(role.members) if role else 0

        for m in interaction.guild.members:
            if not m.bot and member_has_tag(m, tag_text, interaction.guild):
                tag_count += 1

        cont = discord.ui.Container(accent_color=Colors.PRIMARY.value)
        cont.add_item(discord.ui.TextDisplay(
            f"# 🏷️ Statut du Rôle Tag • {interaction.guild.name}\n"
            f"> Attribue automatiquement un rôle exclusif à ceux qui soutiennent le serveur.\n\n"
            f"🎭 **Rôle configuré :** {role_str}\n"
            f"🏷️ **Tag recherché :** `{tag_text}`\n"
            f"👥 **Membres portant le tag :** `{tag_count}`\n"
            f"🛡️ **Membres ayant le rôle :** `{role_count}`\n\n"
            f"💡 *Le rôle est ajouté dès qu'un membre met le tag, et retiré automatiquement dès qu'il l'enlève.*"
        ))
        view = discord.ui.LayoutView()
        view.add_item(cont)
        await interaction.response.send_message(view=view, ephemeral=True)

    @tagrole.command(name="scan", description="Force une vérification de tous les membres pour synchroniser le rôle")
    @app_commands.default_permissions(manage_guild=True)
    async def tagrole_scan(self, interaction: discord.Interaction):
        settings = await self.bot.db.get_guild_settings(interaction.guild.id)
        role_id = settings.get("tagrole_id")
        if not role_id:
            return await interaction.response.send_message(
                embed=error_embed("❌ Aucun rôle de tag n'est configuré. Utilise `/tagrole config` d'abord."),
                ephemeral=True
            )

        tag_text = settings.get("tagrole_text") or "17th"
        role = interaction.guild.get_role(role_id)
        if not role:
            return await interaction.response.send_message(
                embed=error_embed("❌ Le rôle configuré est introuvable sur le serveur."),
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        added = 0
        removed = 0

        for m in interaction.guild.members:
            if not m.bot:
                res = await self._sync_member(m, role_id, tag_text, allow_fetch=False)
                if res == "added":
                    added += 1
                elif res == "removed":
                    removed += 1

        cont = discord.ui.Container(accent_color=Colors.SUCCESS.value)
        cont.add_item(discord.ui.TextDisplay(
            f"# 🔄 Synchronisation du Tag Réussie !\n"
            f"> Scan complet de l'ensemble des membres du serveur terminé.\n\n"
            f"➕ **Rôles ajoutés :** `{added}` *(membres ayant mis le tag)*\n"
            f"➖ **Rôles retirés :** `{removed}` *(membres ayant retiré le tag)*\n"
            f"🏷️ **Tag actif :** `{tag_text}` ➔ {role.mention}"
        ))
        view = discord.ui.LayoutView()
        view.add_item(cont)
        await interaction.followup.send(view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(TagRole(bot))
