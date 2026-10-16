import json
import random
import re
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.i18n import t
from utils.helpers import parse_duration
from utils.colors import Colors
from utils.embeds import error_embed, info_embed, success_embed


# ── Helpers ───────────────────────────────────────────────────────────────────

def _recover_giveaway_from_message(message: discord.Message) -> dict | None:
    if not message.embeds:
        return None
    embed = message.embeds[0]
    if not embed.title or "GIVEAWAY" not in embed.title.upper():
        return None

    gid = None
    if embed.footer and embed.footer.text:
        m = re.search(r"ID\s*:\s*(\d+)", embed.footer.text)
        if m:
            gid = int(m.group(1))

    prize = "Giveaway"
    winners_count = 1
    ends_at_iso = None
    host_id = message.author.id

    for field in embed.fields:
        fname = field.name.lower()
        fval = field.value
        if "lot" in fname or "prize" in fname:
            prize = fval.strip()
        elif "gagnant" in fname or "winner" in fname:
            m = re.search(r"\d+", fval)
            if m:
                winners_count = max(1, int(m.group(0)))
        elif "fin" in fname or "end" in fname:
            ts_m = re.search(r"<t:(\d+)", fval)
            if ts_m:
                ts = int(ts_m.group(1))
                ends_at_iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        elif "organisé" in fname or "host" in fname:
            u_m = re.search(r"<@!?(\d+)>", fval)
            if u_m:
                host_id = int(u_m.group(1))

    if not ends_at_iso:
        ends_at_iso = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    return {
        "id": gid,
        "guild_id": message.guild.id if message.guild else None,
        "channel_id": message.channel.id,
        "message_id": message.id,
        "prize": prize,
        "winners_count": winners_count,
        "host_id": host_id,
        "ends_at": ends_at_iso,
    }


def _parse_dt(value) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except ValueError:
            return None
    return None


def _build_giveaway_embed(row: dict, lang: str, participants: list) -> discord.Embed:
    ends_at = _parse_dt(row["ends_at"])
    embed = discord.Embed(
        title=t(lang, "giveaway.title"),
        description=t(lang, "giveaway.desc"),
        color=Colors.GOLD.value,
    )
    embed.add_field(name=t(lang, "giveaway.prize_label"), value=row["prize"], inline=True)
    embed.add_field(name=t(lang, "giveaway.winners_label"), value=str(row["winners_count"]), inline=True)
    if ends_at:
        embed.add_field(
            name=t(lang, "giveaway.ends_label"),
            value=(
                f"{discord.utils.format_dt(ends_at, style='R')}"
                f" ({discord.utils.format_dt(ends_at, style='f')})"
            ),
            inline=False,
        )
    embed.add_field(name=t(lang, "giveaway.host_label"), value=f"<@{row['host_id']}>", inline=True)
    embed.add_field(name=t(lang, "giveaway.participants_label"), value=str(len(participants)), inline=True)
    embed.set_footer(text=f"ID : {row['id']}")
    return embed


def _build_ended_embed(row: dict, lang: str, participants: list) -> discord.Embed:
    embed = discord.Embed(
        title=t(lang, "giveaway.ended_title"),
        color=Colors.NEUTRAL.value,
    )
    embed.add_field(name=t(lang, "giveaway.prize_label"), value=row["prize"], inline=True)
    embed.add_field(name=t(lang, "giveaway.participants_label"), value=str(len(participants)), inline=True)
    embed.add_field(name=t(lang, "giveaway.host_label"), value=f"<@{row['host_id']}>", inline=True)
    embed.add_field(name=t(lang, "giveaway.ended_label"), value="✅", inline=True)
    embed.set_footer(text=f"ID : {row['id']}")
    return embed


# ── Persistent views ──────────────────────────────────────────────────────────

class GiveawayButton(discord.ui.Button):
    def __init__(self, count: int = 0, disabled: bool = False):
        super().__init__(
            label=f"🎉 {count}",
            style=discord.ButtonStyle.primary,
            custom_id="giveaway_enter",
            disabled=disabled,
        )

    async def callback(self, interaction: discord.Interaction):
        bot = interaction.client
        row = await bot.db.get_giveaway_by_msg(interaction.message.id)
        if not row:
            # Auto-recovery from message embed
            recovered = _recover_giveaway_from_message(interaction.message)
            if recovered and recovered.get("guild_id"):
                gid = recovered.get("id")
                if gid:
                    existing = await bot.db.get_giveaway(gid)
                    if existing:
                        await bot.db.set_giveaway_message(gid, interaction.message.id)
                        row = await bot.db.get_giveaway(gid)
                    else:
                        await bot.db._exec(
                            "INSERT OR REPLACE INTO giveaways (id, guild_id, channel_id, message_id, prize, winners_count, host_id, ends_at, ended, winner_ids, participants) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, '[]', '[]')",
                            gid,
                            recovered["guild_id"],
                            recovered["channel_id"],
                            recovered["message_id"],
                            recovered["prize"],
                            recovered["winners_count"],
                            recovered["host_id"],
                            recovered["ends_at"],
                        )
                        row = await bot.db.get_giveaway(gid)
                else:
                    new_id = await bot.db.create_giveaway(
                        guild_id=recovered["guild_id"],
                        channel_id=recovered["channel_id"],
                        prize=recovered["prize"],
                        winners_count=recovered["winners_count"],
                        host_id=recovered["host_id"],
                        ends_at=recovered["ends_at"],
                    )
                    await bot.db.set_giveaway_message(new_id, interaction.message.id)
                    row = await bot.db.get_giveaway(new_id)

        if not row:
            return await interaction.response.send_message(embed=error_embed("❌ Giveaway introuvable."), ephemeral=True)

        lang = await bot.db.get_guild_lang(interaction.guild_id)

        if row["ended"]:
            return await interaction.response.send_message(
                embed=error_embed(t(lang, "giveaway.already_ended")), ephemeral=True
            )

        # Participants are stored in the separate `participants` column.
        participants = json.loads(row.get("participants") or "[]")
        user_id = interaction.user.id

        if user_id in participants:
            participants.remove(user_id)
            joined = False
        else:
            participants.append(user_id)
            joined = True

        await bot.db._exec(
            "UPDATE giveaways SET participants = ? WHERE id = ?",
            json.dumps(participants),
            row["id"],
        )

        updated_row = await bot.db.get_giveaway(row["id"])
        embed = _build_giveaway_embed(updated_row, lang, participants)
        new_view = GiveawayView(count=len(participants))

        await interaction.response.edit_message(embed=embed, view=new_view)

        msg = success_embed(t(lang, "giveaway.join_success")) if joined else info_embed(t(lang, "giveaway.leave_success"))
        await interaction.followup.send(embed=msg, ephemeral=True)


class GiveawayView(discord.ui.View):
    def __init__(self, count: int = 0, disabled: bool = False):
        super().__init__(timeout=None)
        self.add_item(GiveawayButton(count=count, disabled=disabled))


# ── Cog ───────────────────────────────────────────────────────────────────────

class Giveaway(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Additive migration: track participants separately from winner_ids.
        # winner_ids is used exclusively for the final drawn winners post-end.
        try:
            await self.bot.db._exec(
                "ALTER TABLE giveaways ADD COLUMN participants TEXT DEFAULT '[]'"
            )
        except Exception:
            pass  # Column already exists on subsequent restarts.

        self.bot.add_view(GiveawayView())
        self.check_expired_giveaways.start()
        self.bot.loop.create_task(self._auto_recover_giveaways())

    async def _auto_recover_giveaways(self):
        await self.bot.wait_until_ready()
        try:
            active_1 = await self.bot.db.get_giveaway(1)
            if not active_1:
                await self.bot.db._exec(
                    "INSERT OR REPLACE INTO giveaways (id, guild_id, channel_id, message_id, prize, winners_count, host_id, ends_at, ended, winner_ids, participants) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, '[]', '[]')",
                    1, 1461480122518606036, 1560630217477718098, 1560632824695103529, "Pack Yeat Fortnite", 1, 938847960509325342, "2026-10-18T12:37:40+00:00"
                )
        except Exception:
            pass

    def cog_unload(self):
        self.check_expired_giveaways.cancel()

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _draw_and_end(self, giveaway_id: int) -> tuple[list | None, dict | None]:
        """Pick random winners, persist result, and update the Discord message."""
        row = await self.bot.db.get_giveaway(giveaway_id)
        if not row or row["ended"]:
            return None, None

        participants = json.loads(row.get("participants") or "[]")
        k = min(row["winners_count"], len(participants))
        winner_ids = random.sample(participants, k) if k > 0 else []

        await self.bot.db.end_giveaway(giveaway_id, winner_ids)

        guild = self.bot.get_guild(row["guild_id"])
        lang = await self.bot.db.get_guild_lang(row["guild_id"])

        channel = guild.get_channel(row["channel_id"]) if guild else None
        if channel and row.get("message_id"):
            try:
                message = await channel.fetch_message(row["message_id"])
                ended_embed = _build_ended_embed(row, lang, participants)
                disabled_view = GiveawayView(count=len(participants), disabled=True)
                await message.edit(embed=ended_embed, view=disabled_view)

                if winner_ids:
                    mentions = ", ".join(f"<@{uid}>" for uid in winner_ids)
                    announce = t(lang, "giveaway.winner_announce", winners=mentions, prize=row["prize"])
                else:
                    announce = t(lang, "giveaway.no_winner")
                await channel.send(announce)
            except (discord.NotFound, discord.Forbidden):
                pass

        return winner_ids, row

    # ── Background task ───────────────────────────────────────────────────────

    @tasks.loop(minutes=1)
    async def check_expired_giveaways(self):
        try:
            expired = await self.bot.db.get_expired_giveaways()
            for row in expired:
                await self._draw_and_end(row["id"])
        except Exception:
            pass

    @check_expired_giveaways.before_loop
    async def _before_check_giveaways(self):
        await self.bot.wait_until_ready()

    # ── Command group ─────────────────────────────────────────────────────────

    giveaway_group = app_commands.Group(name="giveaway", description="Gestion des giveaways")

    @giveaway_group.command(name="start", description="Lance un nouveau giveaway")
    @app_commands.describe(
        prize="Le lot mis en jeu",
        durée="Durée du giveaway (ex: 30m, 2h, 1d)",
        gagnants="Nombre de gagnants (défaut : 1)",
        salon="Salon où poster le giveaway (défaut : salon actuel)",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def giveaway_start(
        self,
        interaction: discord.Interaction,
        prize: str,
        durée: str,
        gagnants: int = 1,
        salon: discord.TextChannel = None,
    ):
        await interaction.response.defer(ephemeral=True)
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)

        try:
            _seconds, delta = parse_duration(durée)
        except ValueError:
            return await interaction.followup.send(
                embed=error_embed(t(lang, "giveaway.invalid_duration")), ephemeral=True
            )

        channel = salon or interaction.channel
        ends_at = datetime.now(timezone.utc) + delta
        ends_at_str = ends_at.isoformat()

        giveaway_id = await self.bot.db.create_giveaway(
            guild_id=interaction.guild_id,
            channel_id=channel.id,
            prize=prize,
            winners_count=max(1, gagnants),
            host_id=interaction.user.id,
            ends_at=ends_at_str,
        )

        row = await self.bot.db.get_giveaway(giveaway_id)
        embed = _build_giveaway_embed(row, lang, [])
        view = GiveawayView(count=0)

        try:
            message = await channel.send(embed=embed, view=view)
        except discord.Forbidden:
            return await interaction.followup.send(
                embed=error_embed(t(lang, "giveaway.cant_send")),
                ephemeral=True,
            )

        await self.bot.db.set_giveaway_message(giveaway_id, message.id)
        await interaction.followup.send(
            embed=success_embed(t(lang, "giveaway.created", channel=channel.mention)), ephemeral=True
        )

    @giveaway_group.command(name="end", description="Termine manuellement un giveaway et tire les gagnants")
    @app_commands.describe(id="ID du giveaway à terminer")
    @app_commands.default_permissions(manage_guild=True)
    async def giveaway_end(self, interaction: discord.Interaction, id: int):
        await interaction.response.defer(ephemeral=True)
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)

        row = await self.bot.db.get_giveaway(id)
        if not row or row["guild_id"] != interaction.guild_id:
            return await interaction.followup.send(embed=error_embed(t(lang, "giveaway.not_found")), ephemeral=True)
        if row["ended"]:
            return await interaction.followup.send(embed=error_embed(t(lang, "giveaway.already_ended")), ephemeral=True)

        winner_ids, _ended_row = await self._draw_and_end(id)
        if winner_ids is None:
            # Raced with background task or already ended — surface a safe error.
            return await interaction.followup.send(embed=error_embed(t(lang, "giveaway.already_ended")), ephemeral=True)

        await interaction.followup.send(embed=success_embed(t(lang, "giveaway.ended_success")), ephemeral=True)

    @giveaway_group.command(name="reroll", description="Relance le tirage au sort pour un giveaway terminé")
    @app_commands.describe(id="ID du giveaway terminé")
    @app_commands.default_permissions(manage_guild=True)
    async def giveaway_reroll(self, interaction: discord.Interaction, id: int):
        await interaction.response.defer(ephemeral=True)
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)

        row = await self.bot.db.get_giveaway(id)
        if not row or row["guild_id"] != interaction.guild_id:
            return await interaction.followup.send(embed=error_embed(t(lang, "giveaway.not_found")), ephemeral=True)
        if not row["ended"]:
            return await interaction.followup.send(
                embed=error_embed(t(lang, "giveaway.not_ended_yet")), ephemeral=True
            )

        # Reroll draws from the original participant pool stored separately.
        participants = json.loads(row.get("participants") or "[]")
        if not participants:
            return await interaction.followup.send(embed=error_embed(t(lang, "giveaway.no_winner")), ephemeral=True)

        winner_id = random.choice(participants)
        embed = discord.Embed(
            title=t(lang, "giveaway.reroll_title"),
            description=t(
                lang, "giveaway.reroll_winner",
                winner=f"<@{winner_id}>",
                prize=row["prize"],
            ),
            color=Colors.GOLD.value,
        )
        await interaction.followup.send(embed=embed)

    @giveaway_group.command(name="list", description="Liste les giveaways actifs sur ce serveur")
    async def giveaway_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        lang = await self.bot.db.get_guild_lang(interaction.guild_id)

        giveaways = await self.bot.db.get_active_giveaways(interaction.guild_id)
        if not giveaways:
            embed = discord.Embed(
                title=t(lang, "giveaway.list_title"),
                description=t(lang, "giveaway.list_empty"),
                color=Colors.GOLD.value,
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        embed = discord.Embed(title=t(lang, "giveaway.list_title"), color=Colors.GOLD.value)
        for row in giveaways:
            ends_at = _parse_dt(row["ends_at"])
            channel = interaction.guild.get_channel(row["channel_id"])
            participants = json.loads(row.get("participants") or "[]")

            lines = [
                f"**{t(lang, 'giveaway.prize_label')}:** {row['prize']}",
                f"**{t(lang, 'giveaway.winners_label')}:** {row['winners_count']}",
                f"**{t(lang, 'giveaway.participants_label')}:** {len(participants)}",
            ]
            if ends_at:
                lines.append(
                    f"**{t(lang, 'giveaway.ends_label')}:** {discord.utils.format_dt(ends_at, style='R')}"
                )
            if channel:
                lines.append(f"**Salon :** {channel.mention}")

            embed.add_field(
                name=f"Giveaway #{row['id']}",
                value="\n".join(lines),
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @giveaway_group.command(name="sync", description="Synchronise et restaure un giveaway actif trouvé dans ce salon")
    @app_commands.default_permissions(manage_guild=True)
    async def giveaway_sync(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        count = 0
        async for msg in interaction.channel.history(limit=50):
            recovered = _recover_giveaway_from_message(msg)
            if recovered and recovered.get("id"):
                gid = recovered["id"]
                existing = await self.bot.db.get_giveaway(gid)
                if not existing:
                    await self.bot.db._exec(
                        "INSERT OR REPLACE INTO giveaways (id, guild_id, channel_id, message_id, prize, winners_count, host_id, ends_at, ended, winner_ids, participants) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, '[]', '[]')",
                        gid, recovered["guild_id"], recovered["channel_id"], recovered["message_id"],
                        recovered["prize"], recovered["winners_count"], recovered["host_id"], recovered["ends_at"]
                    )
                    count += 1
                elif not existing.get("message_id"):
                    await self.bot.db.set_giveaway_message(gid, msg.id)
                    count += 1
        await interaction.followup.send(embed=success_embed(f"Synchronisation terminée : {count} giveaway(s) restauré(s)."), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaway(bot))

