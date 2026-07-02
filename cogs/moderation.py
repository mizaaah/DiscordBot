import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone
from utils.helpers import parse_duration, duration_to_str
from utils.i18n import t
from utils.colors import Colors


def _parse_dt(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def get_logs(bot: commands.Bot):
    return bot.get_cog("Logs")


# ══════════════════════════════════════════════════════════════════════════════
#  Paginated list views (warnings / history)
# ══════════════════════════════════════════════════════════════════════════════

class _PagedEmbedView(discord.ui.View):
    PAGE_SIZE = 5

    def __init__(self, items: list, lang: str, page: int = 0):
        super().__init__(timeout=120)
        self.items = items
        self.lang  = lang
        self.page  = page
        self.total = max(1, (len(items) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self._update_buttons()

    def _update_buttons(self):
        self.children[0].disabled = self.page == 0
        self.children[1].disabled = self.page >= self.total - 1

    def build_embed(self) -> discord.Embed:
        raise NotImplementedError

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class WarningsView(_PagedEmbedView):
    def __init__(self, warns: list, member: discord.Member, guild: discord.Guild, lang: str):
        self.member = member
        self.guild  = guild
        super().__init__(warns, lang)

    def build_embed(self) -> discord.Embed:
        lang  = self.lang
        embed = discord.Embed(title=t(lang, "mod.warnings_title", member=str(self.member)), color=Colors.CAUTION)
        if not self.items:
            embed.description = t(lang, "mod.warnings_empty")
            return embed
        start = self.page * self.PAGE_SIZE
        for w in self.items[start:start + self.PAGE_SIZE]:
            mod      = self.guild.get_member(w["moderator_id"])
            mod_name = str(mod) if mod else f"ID:{w['moderator_id']}"
            dt       = _parse_dt(w["created_at"])
            date     = discord.utils.format_dt(dt, 'd') if dt else "?"
            embed.add_field(
                name=f"#{w['id']} — {date}",
                value=f"**{t(lang, 'mod.warnings_reason')}:** {w['reason']}\n**{t(lang, 'mod.warnings_moderator')}:** {mod_name}",
                inline=False
            )
        embed.set_footer(text=f"{t(lang, 'mod.warnings_footer', count=len(self.items))} · {t(lang, 'common.page', page=self.page + 1, total=self.total)}")
        return embed


class HistoryView(_PagedEmbedView):
    TYPE_EMOJI = {"kick": "👢", "ban": "🔨", "tempban": "⏱️", "mute": "🔇", "warn": "⚠️", "unban": "✅"}

    def __init__(self, sanctions: list, member: discord.Member, guild: discord.Guild, lang: str):
        self.member = member
        self.guild  = guild
        super().__init__(sanctions, lang)

    def build_embed(self) -> discord.Embed:
        lang  = self.lang
        embed = discord.Embed(title=t(lang, "mod.history_title", member=str(self.member)), color=Colors.DANGER)
        embed.set_thumbnail(url=self.member.display_avatar.url)
        if not self.items:
            embed.description = t(lang, "mod.history_empty")
            return embed
        start = self.page * self.PAGE_SIZE
        for s in self.items[start:start + self.PAGE_SIZE]:
            mod      = self.guild.get_member(s["moderator_id"])
            mod_name = str(mod) if mod else f"ID:{s['moderator_id']}"
            dt       = _parse_dt(s["created_at"])
            date     = discord.utils.format_dt(dt, 'd') if dt else "?"
            emoji    = self.TYPE_EMOJI.get(s["type"], "📋")
            name     = f"{emoji} {s['type'].upper()} — {date}"
            val      = f"**{t(lang, 'mod.history_reason')}:** {s['reason'] or '—'}"
            if s.get("duration"):
                val += f"\n**{t(lang, 'mod.mute_duration')}:** {s['duration']}"
            val += f"\n**{t(lang, 'mod.history_moderator')}:** {mod_name}"
            embed.add_field(name=name, value=val, inline=False)
        embed.set_footer(text=f"{t(lang, 'mod.history_footer', count=len(self.items))} · {t(lang, 'common.page', page=self.page + 1, total=self.total)}")
        return embed


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_temp_bans.start()

    def cog_unload(self):
        self.check_temp_bans.cancel()

    def _can_act_on(self, interaction: discord.Interaction, target: discord.Member) -> bool:
        if target == interaction.guild.owner:
            return False
        if target.top_role >= interaction.guild.me.top_role:
            return False
        if target.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
            return False
        return True

    # ── /kick ────────────────────────────────────────────────────────────────

    @app_commands.command(name="kick", description="Expulse un membre du serveur")
    @app_commands.describe(membre="Le membre à expulser", raison="Raison de l'expulsion")
    @app_commands.default_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison fournie"):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        if not self._can_act_on(interaction, membre):
            return await interaction.response.send_message(t(lang, "mod.cant_act"), ephemeral=True)
        try:
            await membre.send(t(lang, "mod.kick_dm", server=interaction.guild.name, reason=raison))
        except discord.Forbidden:
            pass
        await membre.kick(reason=raison)
        embed = discord.Embed(
            title=t(lang, "mod.kick_title"),
            description=t(lang, "mod.kick_desc", member=str(membre)),
            color=Colors.WARNING
        )
        embed.add_field(name=t(lang, "mod.kick_reason"), value=raison)
        await interaction.response.send_message(embed=embed)
        await self.bot.db.add_sanction(interaction.guild.id, membre.id, interaction.user.id, "kick", raison)
        if logs := get_logs(self.bot):
            await logs.log_kick(interaction.guild, membre, interaction.user, raison)

    # ── /ban ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="ban", description="Bannit un membre (permanent ou temporaire)")
    @app_commands.describe(
        membre="Le membre à bannir",
        durée="Durée du ban (ex: 10m, 2h, 1d, 1w) — laisser vide pour permanent",
        raison="Raison du ban"
    )
    @app_commands.default_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, membre: discord.Member, durée: str = None, raison: str = "Aucune raison fournie"):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        if not self._can_act_on(interaction, membre):
            return await interaction.response.send_message(t(lang, "mod.cant_act"), ephemeral=True)

        unban_at = None
        duration_label = None
        if durée:
            try:
                seconds, delta = parse_duration(durée)
                unban_at = datetime.now(timezone.utc) + delta
                duration_label = duration_to_str(durée)
            except ValueError as e:
                return await interaction.response.send_message(t(lang, "mod.invalid_duration", error=str(e)), ephemeral=True)

        try:
            if duration_label:
                await membre.send(t(lang, "mod.ban_dm_temp", server=interaction.guild.name, reason=raison, duration=duration_label))
            else:
                await membre.send(t(lang, "mod.ban_dm", server=interaction.guild.name, reason=raison))
        except discord.Forbidden:
            pass

        await membre.ban(reason=raison, delete_message_days=0)

        if unban_at:
            await self.bot.db.add_temp_ban(interaction.guild.id, membre.id, interaction.user.id, raison, unban_at)

        title = t(lang, "mod.ban_temp_title", duration=duration_label) if duration_label else t(lang, "mod.ban_title")
        embed = discord.Embed(title=title, description=t(lang, "mod.ban_desc", member=str(membre)), color=Colors.ERROR)
        embed.add_field(name=t(lang, "mod.ban_reason"), value=raison, inline=False)
        if duration_label:
            embed.add_field(name=t(lang, "mod.ban_duration"), value=duration_label, inline=True)
            embed.add_field(name=t(lang, "mod.ban_end"), value=discord.utils.format_dt(unban_at, 'R'), inline=True)
        await interaction.response.send_message(embed=embed)
        await self.bot.db.add_sanction(interaction.guild.id, membre.id, interaction.user.id, "tempban" if duration_label else "ban", raison, duration_label)
        if logs := get_logs(self.bot):
            await logs.log_ban(interaction.guild, membre, interaction.user, raison, duration_label)

    # ── /unban ───────────────────────────────────────────────────────────────

    @app_commands.command(name="unban", description="Débannie un utilisateur par son ID")
    @app_commands.describe(user_id="L'ID de l'utilisateur", raison="Raison du déban")
    @app_commands.default_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str, raison: str = "Aucune raison fournie"):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        try:
            uid = int(user_id)
        except ValueError:
            return await interaction.response.send_message(t(lang, "mod.invalid_id"), ephemeral=True)
        try:
            user = await self.bot.fetch_user(uid)
            await interaction.guild.unban(user, reason=raison)
            await self.bot.db.remove_temp_ban(interaction.guild.id, uid)
            embed = discord.Embed(
                title=t(lang, "mod.unban_title"),
                description=t(lang, "mod.unban_desc", user=str(user)),
                color=Colors.SUCCESS
            )
            embed.add_field(name=t(lang, "mod.unban_reason"), value=raison)
            await interaction.response.send_message(embed=embed)
            if logs := get_logs(self.bot):
                await logs.log_unban(interaction.guild, user, interaction.user, raison)
        except discord.NotFound:
            await interaction.response.send_message(t(lang, "mod.unban_not_banned"), ephemeral=True)

    # ── /mute ────────────────────────────────────────────────────────────────

    @app_commands.command(name="mute", description="Rend muet un membre (timeout Discord natif)")
    @app_commands.describe(
        membre="Le membre à muter",
        durée="Durée du mute (ex: 10m, 2h, 1d) — max 28j",
        raison="Raison du mute"
    )
    @app_commands.default_permissions(moderate_members=True)
    async def mute(self, interaction: discord.Interaction, membre: discord.Member, durée: str, raison: str = "Aucune raison fournie"):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        if not self._can_act_on(interaction, membre):
            return await interaction.response.send_message(t(lang, "mod.cant_act"), ephemeral=True)
        try:
            seconds, delta = parse_duration(durée)
        except ValueError as e:
            return await interaction.response.send_message(t(lang, "mod.invalid_duration", error=str(e)), ephemeral=True)

        if seconds > 2419200:
            return await interaction.response.send_message(t(lang, "mod.mute_max_duration"), ephemeral=True)

        until = datetime.now(timezone.utc) + delta
        await membre.timeout(until, reason=raison)
        duration_label = duration_to_str(durée)

        embed = discord.Embed(
            title=t(lang, "mod.mute_title"),
            description=t(lang, "mod.mute_desc", member=membre.mention),
            color=Colors.WARNING
        )
        embed.add_field(name=t(lang, "mod.mute_duration"), value=duration_label, inline=True)
        embed.add_field(name=t(lang, "mod.mute_end"),      value=discord.utils.format_dt(until, 'R'), inline=True)
        embed.add_field(name=t(lang, "mod.mute_reason"),   value=raison, inline=False)
        await interaction.response.send_message(embed=embed)

        try:
            await membre.send(t(lang, "mod.mute_dm", server=interaction.guild.name, duration=duration_label, reason=raison))
        except discord.Forbidden:
            pass

        await self.bot.db.add_sanction(interaction.guild.id, membre.id, interaction.user.id, "mute", raison, duration_label)
        if logs := get_logs(self.bot):
            await logs.log_mute(interaction.guild, membre, interaction.user, raison, duration_label)

    # ── /unmute ──────────────────────────────────────────────────────────────

    @app_commands.command(name="unmute", description="Retire le mute d'un membre")
    @app_commands.describe(membre="Le membre à démuter", raison="Raison")
    @app_commands.default_permissions(moderate_members=True)
    async def unmute(self, interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison fournie"):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        if not membre.is_timed_out():
            return await interaction.response.send_message(t(lang, "mod.unmute_not_muted"), ephemeral=True)
        await membre.timeout(None, reason=raison)
        embed = discord.Embed(
            title=t(lang, "mod.unmute_title"),
            description=t(lang, "mod.unmute_desc", member=membre.mention),
            color=Colors.SUCCESS
        )
        embed.add_field(name=t(lang, "mod.unmute_reason"), value=raison)
        await interaction.response.send_message(embed=embed)
        if logs := get_logs(self.bot):
            await logs.log_unmute(interaction.guild, membre, interaction.user, raison)

    # ── /warn ────────────────────────────────────────────────────────────────

    @app_commands.command(name="warn", description="Avertit un membre")
    @app_commands.describe(membre="Le membre à avertir", raison="Raison de l'avertissement")
    @app_commands.default_permissions(manage_messages=True)
    async def warn(self, interaction: discord.Interaction, membre: discord.Member, raison: str):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        if membre.bot:
            return await interaction.response.send_message(t(lang, "mod.warn_bot"), ephemeral=True)

        warn_id = await self.bot.db.add_warning(interaction.guild.id, membre.id, interaction.user.id, raison)
        total   = await self.bot.db.get_warning_count(interaction.guild.id, membre.id)

        embed = discord.Embed(
            title=t(lang, "mod.warn_title"),
            description=t(lang, "mod.warn_desc", member=membre.mention),
            color=Colors.CAUTION
        )
        embed.add_field(name=t(lang, "mod.warn_reason"), value=raison, inline=False)
        embed.add_field(name=t(lang, "mod.warn_total"),  value=str(total), inline=True)
        embed.set_footer(text=t(lang, "mod.warn_footer", id=warn_id))
        await interaction.response.send_message(embed=embed)

        try:
            await membre.send(t(lang, "mod.warn_dm", server=interaction.guild.name, reason=raison, total=total))
        except discord.Forbidden:
            pass

        await self.bot.db.add_sanction(interaction.guild.id, membre.id, interaction.user.id, "warn", raison)
        if logs := get_logs(self.bot):
            await logs.log_warn(interaction.guild, membre, interaction.user, raison, warn_id, total)

        self.bot.dispatch("warn_added", interaction.guild, membre, total)

    # ── /unwarn ──────────────────────────────────────────────────────────────

    async def _warn_autocomplete(self, interaction: discord.Interaction, current: str):
        warns = await self.bot.db.get_all_warnings(interaction.guild.id)
        choices = []
        for w in warns:
            member = interaction.guild.get_member(w["user_id"])
            name = member.display_name if member else f"ID:{w['user_id']}"
            label = f"#{w['id']} — {name} — {w['reason'][:60]}"
            if current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label[:100], value=w["id"]))
        return choices[:25]

    @app_commands.command(name="unwarn", description="Supprime un avertissement par son ID")
    @app_commands.describe(id_warn="L'ID de l'avertissement à supprimer")
    @app_commands.autocomplete(id_warn=_warn_autocomplete)
    @app_commands.default_permissions(manage_messages=True)
    async def unwarn(self, interaction: discord.Interaction, id_warn: int):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        removed = await self.bot.db.remove_warning(id_warn, interaction.guild.id)
        if removed:
            await interaction.response.send_message(t(lang, "mod.unwarn_removed", id=id_warn))
        else:
            await interaction.response.send_message(t(lang, "mod.unwarn_not_found", id=id_warn), ephemeral=True)

    # ── /warnings ────────────────────────────────────────────────────────────

    @app_commands.command(name="warnings", description="Affiche les avertissements d'un membre")
    @app_commands.describe(membre="Le membre dont voir les warns")
    @app_commands.default_permissions(manage_messages=True)
    async def warnings(self, interaction: discord.Interaction, membre: discord.Member):
        lang  = await self.bot.db.get_guild_lang(interaction.guild_id)
        warns = await self.bot.db.get_warnings(interaction.guild.id, membre.id)
        view  = WarningsView(warns, membre, interaction.guild, lang)
        await interaction.response.send_message(embed=view.build_embed(), view=view)

    # ── /clearwarnings ───────────────────────────────────────────────────────

    @app_commands.command(name="clearwarnings", description="Efface tous les avertissements d'un membre")
    @app_commands.describe(membre="Le membre dont effacer les warns")
    @app_commands.default_permissions(manage_guild=True)
    async def clearwarnings(self, interaction: discord.Interaction, membre: discord.Member):
        lang  = await self.bot.db.get_guild_lang(interaction.guild_id)
        count = await self.bot.db.clear_warnings(interaction.guild.id, membre.id)
        await interaction.response.send_message(t(lang, "mod.clearwarn_success", count=count, member=membre.mention))

    # ── /history ─────────────────────────────────────────────────────────────

    @app_commands.command(name="history", description="Affiche l'historique des sanctions d'un membre")
    @app_commands.describe(membre="Le membre dont voir l'historique")
    @app_commands.default_permissions(manage_messages=True)
    async def history(self, interaction: discord.Interaction, membre: discord.Member):
        lang      = await self.bot.db.get_guild_lang(interaction.guild_id)
        sanctions = await self.bot.db.get_sanctions(interaction.guild.id, membre.id, limit=100)
        view      = HistoryView(sanctions, membre, interaction.guild, lang)
        await interaction.response.send_message(embed=view.build_embed(), view=view)

    # ── /clear ───────────────────────────────────────────────────────────────

    @app_commands.command(name="clear", description="Supprime des messages en masse avec filtres optionnels")
    @app_commands.describe(
        nombre="Nombre de messages à supprimer (1–100)",
        membre="Seulement les messages de ce membre",
        bots="Seulement les messages de bots",
        images="Seulement les messages avec images/fichiers",
        contient="Seulement les messages contenant ce texte"
    )
    @app_commands.default_permissions(manage_messages=True)
    async def clear(
        self,
        interaction: discord.Interaction,
        nombre: app_commands.Range[int, 1, 100],
        membre: discord.Member = None,
        bots: bool = False,
        images: bool = False,
        contient: str = None
    ):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        await interaction.response.defer(ephemeral=True)
        has_filter = membre or bots or images or contient

        def check(msg: discord.Message) -> bool:
            if membre  and msg.author != membre:                                           return False
            if bots    and not msg.author.bot:                                             return False
            if images  and not msg.attachments and not any(e.image for e in msg.embeds):  return False
            if contient and contient.lower() not in msg.content.lower():                   return False
            return True

        limit   = min(nombre * 5, 500) if has_filter else nombre
        deleted = await interaction.channel.purge(limit=limit, check=check if has_filter else None,
                                                   before=interaction.created_at)
        if len(deleted) > nombre:
            deleted = deleted[:nombre]

        await interaction.followup.send(t(lang, "mod.clear_success", count=len(deleted)), ephemeral=True)

        if logs := get_logs(self.bot):
            await logs.log_clear(interaction.guild, interaction.channel, interaction.user, len(deleted))

    # ── /slowmode ────────────────────────────────────────────────────────────

    @app_commands.command(name="slowmode", description="Active ou désactive le mode lent sur le salon")
    @app_commands.describe(secondes="Délai en secondes (0 pour désactiver, max 21600)")
    @app_commands.default_permissions(manage_channels=True)
    async def slowmode(self, interaction: discord.Interaction, secondes: app_commands.Range[int, 0, 21600] = 0):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        await interaction.channel.edit(slowmode_delay=secondes)
        if secondes == 0:
            await interaction.response.send_message(t(lang, "mod.slowmode_disabled"))
        else:
            await interaction.response.send_message(t(lang, "mod.slowmode_enabled", seconds=secondes))

    # ── /lock ────────────────────────────────────────────────────────────────

    @app_commands.command(name="lock", description="Verrouille le salon actuel")
    @app_commands.describe(raison="Raison du verrouillage")
    @app_commands.default_permissions(manage_channels=True)
    async def lock(self, interaction: discord.Interaction, raison: str = "Aucune raison fournie"):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        embed = discord.Embed(title=t(lang, "mod.lock_title"), description=f"**{t(lang, 'mod.lock_reason')}:** {raison}", color=Colors.ERROR)
        await interaction.response.send_message(embed=embed)
        if logs := get_logs(self.bot):
            await logs.log_lock(interaction.guild, interaction.channel, interaction.user, raison, True)

    # ── /unlock ──────────────────────────────────────────────────────────────

    @app_commands.command(name="unlock", description="Déverrouille le salon actuel")
    @app_commands.describe(raison="Raison du déverrouillage")
    @app_commands.default_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction, raison: str = "Aucune raison fournie"):
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        embed = discord.Embed(title=t(lang, "mod.unlock_title"), description=f"**{t(lang, 'mod.lock_reason')}:** {raison}", color=Colors.SUCCESS)
        await interaction.response.send_message(embed=embed)
        if logs := get_logs(self.bot):
            await logs.log_lock(interaction.guild, interaction.channel, interaction.user, raison, False)

    # ── Background task: check temp bans ─────────────────────────────────────

    @tasks.loop(minutes=1)
    async def check_temp_bans(self):
        expired = await self.bot.db.get_expired_bans()
        for ban in expired:
            guild = self.bot.get_guild(ban["guild_id"])
            if not guild:
                continue
            try:
                user = await self.bot.fetch_user(ban["user_id"])
                await guild.unban(user, reason="Durée du ban expirée")
                if logs := get_logs(self.bot):
                    lang = await self.bot.db.get_guild_lang(guild.id)
                    await logs.log_unban(guild, user, self.bot.user, t(lang, "mod.ban_expired_reason"))
            except (discord.NotFound, discord.Forbidden):
                pass
            finally:
                await self.bot.db.remove_temp_ban(ban["guild_id"], ban["user_id"])

    @check_temp_bans.before_loop
    async def before_check_temp_bans(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
