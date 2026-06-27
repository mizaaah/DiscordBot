import aiosqlite
import json
import os
from datetime import datetime, timezone

DB_PATH = os.getenv("DB_PATH", "bot.db")

ALLOWED_SETTINGS = {
    "log_channel_id", "welcome_channel_id", "goodbye_channel_id",
    "autorole_id", "welcome_message", "goodbye_message", "report_channel_id"
}

ALLOWED_AUTOMOD_SETTINGS = {
    "enabled", "spam_enabled", "spam_threshold", "spam_window", "spam_action",
    "invite_enabled", "invite_action", "caps_enabled", "caps_threshold",
    "caps_min_length", "caps_action", "mention_enabled", "mention_threshold",
    "mention_action", "flood_enabled", "flood_threshold", "flood_action", "bypass_roles"
}

ALLOWED_TICKET_SETTINGS = {
    "category_id", "staff_role_id", "log_channel_id",
    "panel_message_id", "panel_channel_id",
    "embed_color", "welcome_message", "categories"
}

ALLOWED_ANTIRAID_SETTINGS = {
    "enabled", "join_threshold", "join_window",
    "min_account_age", "action", "alert_channel_id", "lockdown_active"
}

ALLOWED_TEMPVOICE_SETTINGS = {
    "trigger_channel_id", "control_channel_id", "category_id", "default_limit", "name_format"
}


class Database:
    def __init__(self):
        self.db: aiosqlite.Connection = None

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _row(self, sql: str, *args) -> dict | None:
        async with self.db.execute(sql, args) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def _rows(self, sql: str, *args) -> list:
        async with self.db.execute(sql, args) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def _val(self, sql: str, *args):
        async with self.db.execute(sql, args) as cur:
            row = await cur.fetchone()
            return row[0] if row else None

    async def _exec(self, sql: str, *args) -> aiosqlite.Cursor:
        cur = await self.db.execute(sql, args)
        await self.db.commit()
        return cur

    # ── Connect / init ────────────────────────────────────────────────────────

    async def connect(self):
        self.db = await aiosqlite.connect(DB_PATH)
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA journal_mode=WAL")
        await self.db.execute("PRAGMA foreign_keys=ON")
        await self._init_tables()

    async def _init_tables(self):
        stmts = [
            """CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id            INTEGER PRIMARY KEY,
                log_channel_id      INTEGER,
                welcome_channel_id  INTEGER,
                goodbye_channel_id  INTEGER,
                autorole_id         INTEGER,
                welcome_message     TEXT DEFAULT 'Bienvenue {mention} sur **{server}** !',
                goodbye_message     TEXT DEFAULT 'Au revoir **{name}**, bonne continuation !'
            )""",
            """CREATE TABLE IF NOT EXISTS warnings (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id        INTEGER NOT NULL,
                user_id         INTEGER NOT NULL,
                moderator_id    INTEGER NOT NULL,
                reason          TEXT NOT NULL DEFAULT 'Aucune raison fournie',
                created_at      TEXT DEFAULT (datetime('now'))
            )""",
            """CREATE TABLE IF NOT EXISTS xp (
                guild_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                xp          INTEGER NOT NULL DEFAULT 0,
                level       INTEGER NOT NULL DEFAULT 0,
                messages    INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )""",
            """CREATE TABLE IF NOT EXISTS temp_bans (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id        INTEGER NOT NULL,
                user_id         INTEGER NOT NULL,
                moderator_id    INTEGER NOT NULL,
                reason          TEXT NOT NULL DEFAULT 'Aucune raison fournie',
                unban_at        TEXT NOT NULL,
                created_at      TEXT DEFAULT (datetime('now'))
            )""",
            """CREATE TABLE IF NOT EXISTS automod_config (
                guild_id            INTEGER PRIMARY KEY,
                enabled             INTEGER DEFAULT 1,
                spam_enabled        INTEGER DEFAULT 1,
                spam_threshold      INTEGER DEFAULT 5,
                spam_window         INTEGER DEFAULT 5,
                spam_action         TEXT DEFAULT 'mute',
                invite_enabled      INTEGER DEFAULT 0,
                invite_action       TEXT DEFAULT 'warn',
                caps_enabled        INTEGER DEFAULT 0,
                caps_threshold      INTEGER DEFAULT 70,
                caps_min_length     INTEGER DEFAULT 10,
                caps_action         TEXT DEFAULT 'warn',
                mention_enabled     INTEGER DEFAULT 0,
                mention_threshold   INTEGER DEFAULT 5,
                mention_action      TEXT DEFAULT 'mute',
                flood_enabled       INTEGER DEFAULT 1,
                flood_threshold     INTEGER DEFAULT 3,
                flood_action        TEXT DEFAULT 'warn',
                bypass_roles        TEXT DEFAULT '[]'
            )""",
            """CREATE TABLE IF NOT EXISTS antiraid_config (
                guild_id            INTEGER PRIMARY KEY,
                enabled             INTEGER DEFAULT 0,
                join_threshold      INTEGER DEFAULT 10,
                join_window         INTEGER DEFAULT 30,
                min_account_age     INTEGER DEFAULT 0,
                action              TEXT DEFAULT 'kick',
                alert_channel_id    INTEGER,
                lockdown_active     INTEGER DEFAULT 0
            )""",
            """CREATE TABLE IF NOT EXISTS ticket_config (
                guild_id            INTEGER PRIMARY KEY,
                category_id         INTEGER,
                staff_role_id       INTEGER,
                log_channel_id      INTEGER,
                ticket_counter      INTEGER DEFAULT 0,
                panel_message_id    INTEGER,
                panel_channel_id    INTEGER,
                embed_color         INTEGER DEFAULT 5793266,
                welcome_message     TEXT,
                categories          TEXT DEFAULT '[]'
            )""",
            """CREATE TABLE IF NOT EXISTS tickets (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id        INTEGER NOT NULL,
                channel_id      INTEGER NOT NULL UNIQUE,
                user_id         INTEGER NOT NULL,
                ticket_number   INTEGER NOT NULL,
                category        TEXT,
                claimed_by      INTEGER,
                status          TEXT DEFAULT 'open',
                created_at      TEXT DEFAULT (datetime('now')),
                closed_at       TEXT,
                closed_by       INTEGER
            )""",
            """CREATE TABLE IF NOT EXISTS rr_panels (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER NOT NULL,
                channel_id  INTEGER NOT NULL,
                message_id  INTEGER NOT NULL UNIQUE,
                title       TEXT NOT NULL,
                description TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS rr_buttons (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                panel_id    INTEGER REFERENCES rr_panels(id) ON DELETE CASCADE,
                role_id     INTEGER NOT NULL,
                label       TEXT NOT NULL,
                emoji       TEXT,
                style       TEXT DEFAULT 'secondary'
            )""",
            """CREATE TABLE IF NOT EXISTS embed_custom_buttons (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER NOT NULL,
                channel_id  INTEGER NOT NULL,
                message_id  INTEGER NOT NULL,
                label       TEXT NOT NULL,
                style       TEXT DEFAULT 'secondary',
                emoji       TEXT,
                action_type TEXT NOT NULL,
                action_data TEXT NOT NULL,
                ephemeral   INTEGER DEFAULT 1,
                position    INTEGER DEFAULT 0
            )""",
            """CREATE TABLE IF NOT EXISTS autosanctions (
                guild_id    INTEGER NOT NULL,
                warn_count  INTEGER NOT NULL,
                action      TEXT NOT NULL,
                duration    INTEGER,
                PRIMARY KEY (guild_id, warn_count)
            )""",
            """CREATE TABLE IF NOT EXISTS reports (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id        INTEGER NOT NULL,
                message_id      INTEGER,
                reporter_id     INTEGER NOT NULL,
                reported_id     INTEGER NOT NULL,
                reason          TEXT NOT NULL,
                resolved        INTEGER DEFAULT 0,
                created_at      TEXT DEFAULT (datetime('now'))
            )""",
            """CREATE TABLE IF NOT EXISTS xp_roles (
                guild_id    INTEGER NOT NULL,
                level       INTEGER NOT NULL,
                role_id     INTEGER NOT NULL,
                PRIMARY KEY (guild_id, level)
            )""",
            """CREATE TABLE IF NOT EXISTS tempvoice_config (
                guild_id            INTEGER PRIMARY KEY,
                trigger_channel_id  INTEGER,
                control_channel_id  INTEGER,
                category_id         INTEGER,
                default_limit       INTEGER DEFAULT 0,
                name_format         TEXT DEFAULT '{user} • Salon'
            )""",
            """CREATE TABLE IF NOT EXISTS tempvoice_channels (
                channel_id      INTEGER PRIMARY KEY,
                guild_id        INTEGER NOT NULL,
                owner_id        INTEGER NOT NULL,
                control_msg_id  INTEGER,
                locked          INTEGER DEFAULT 0,
                hidden          INTEGER DEFAULT 0,
                allowed_users   TEXT DEFAULT '[]'
            )""",
        ]
        for stmt in stmts:
            await self.db.execute(stmt)
        await self.db.commit()
        # Migrations pour installations existantes
        for migration in [
            "ALTER TABLE guild_settings ADD COLUMN report_channel_id INTEGER",
        ]:
            try:
                await self.db.execute(migration)
                await self.db.commit()
            except Exception:
                pass

    async def close(self):
        if self.db:
            await self.db.close()

    # ── Guild settings ────────────────────────────────────────────────────────

    async def get_guild_settings(self, guild_id: int) -> dict:
        row = await self._row("SELECT * FROM guild_settings WHERE guild_id = ?", guild_id)
        if not row:
            await self._exec("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", guild_id)
            row = await self._row("SELECT * FROM guild_settings WHERE guild_id = ?", guild_id)
        return row

    async def update_guild_setting(self, guild_id: int, setting: str, value):
        if setting not in ALLOWED_SETTINGS:
            raise ValueError(f"Paramètre '{setting}' non autorisé.")
        await self._exec(
            f"INSERT INTO guild_settings (guild_id, {setting}) VALUES (?, ?)"
            f" ON CONFLICT(guild_id) DO UPDATE SET {setting} = excluded.{setting}",
            guild_id, value
        )

    # ── Warnings ──────────────────────────────────────────────────────────────

    async def add_warning(self, guild_id: int, user_id: int, moderator_id: int, reason: str) -> int:
        cur = await self._exec(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)",
            guild_id, user_id, moderator_id, reason
        )
        return cur.lastrowid

    async def get_warnings(self, guild_id: int, user_id: int) -> list:
        return await self._rows(
            "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC",
            guild_id, user_id
        )

    async def get_warning_count(self, guild_id: int, user_id: int) -> int:
        return await self._val(
            "SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?",
            guild_id, user_id
        ) or 0

    async def remove_warning(self, warning_id: int, guild_id: int) -> bool:
        cur = await self._exec(
            "DELETE FROM warnings WHERE id = ? AND guild_id = ?",
            warning_id, guild_id
        )
        return cur.rowcount > 0

    async def clear_warnings(self, guild_id: int, user_id: int) -> int:
        cur = await self._exec(
            "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?",
            guild_id, user_id
        )
        return cur.rowcount

    # ── XP ───────────────────────────────────────────────────────────────────

    async def get_xp(self, guild_id: int, user_id: int) -> dict:
        row = await self._row("SELECT * FROM xp WHERE guild_id = ? AND user_id = ?", guild_id, user_id)
        return row or {"guild_id": guild_id, "user_id": user_id, "xp": 0, "level": 0, "messages": 0}

    async def add_xp(self, guild_id: int, user_id: int, amount: int) -> dict:
        await self._exec(
            """INSERT INTO xp (guild_id, user_id, xp, messages) VALUES (?, ?, ?, 1)
               ON CONFLICT(guild_id, user_id)
               DO UPDATE SET xp = xp.xp + excluded.xp, messages = xp.messages + 1""",
            guild_id, user_id, amount
        )
        return await self.get_xp(guild_id, user_id)

    async def set_xp(self, guild_id: int, user_id: int, amount: int, level: int):
        await self._exec(
            """INSERT INTO xp (guild_id, user_id, xp, level) VALUES (?, ?, ?, ?)
               ON CONFLICT(guild_id, user_id) DO UPDATE SET xp = excluded.xp, level = excluded.level""",
            guild_id, user_id, amount, level
        )

    async def reset_xp(self, guild_id: int, user_id: int):
        await self._exec("DELETE FROM xp WHERE guild_id = ? AND user_id = ?", guild_id, user_id)

    async def get_leaderboard(self, guild_id: int, limit: int = 10) -> list:
        return await self._rows(
            "SELECT * FROM xp WHERE guild_id = ? ORDER BY xp DESC LIMIT ?", guild_id, limit
        )

    async def get_rank(self, guild_id: int, user_id: int) -> int:
        user_xp = await self._val("SELECT xp FROM xp WHERE guild_id = ? AND user_id = ?", guild_id, user_id) or 0
        rank    = await self._val("SELECT COUNT(*) FROM xp WHERE guild_id = ? AND xp > ?", guild_id, user_xp) or 0
        return rank + 1

    # ── Temp bans ─────────────────────────────────────────────────────────────

    async def add_temp_ban(self, guild_id: int, user_id: int, moderator_id: int, reason: str, unban_at):
        unban_str = unban_at.isoformat() if hasattr(unban_at, "isoformat") else str(unban_at)
        await self._exec(
            "INSERT OR IGNORE INTO temp_bans (guild_id, user_id, moderator_id, reason, unban_at)"
            " VALUES (?, ?, ?, ?, ?)",
            guild_id, user_id, moderator_id, reason, unban_str
        )

    async def get_expired_bans(self) -> list:
        return await self._rows("SELECT * FROM temp_bans WHERE unban_at <= datetime('now')")

    async def remove_temp_ban(self, guild_id: int, user_id: int):
        await self._exec("DELETE FROM temp_bans WHERE guild_id = ? AND user_id = ?", guild_id, user_id)

    # ── AutoMod ───────────────────────────────────────────────────────────────

    async def get_automod_config(self, guild_id: int) -> dict:
        row = await self._row("SELECT * FROM automod_config WHERE guild_id = ?", guild_id)
        if not row:
            await self._exec("INSERT OR IGNORE INTO automod_config (guild_id) VALUES (?)", guild_id)
            row = await self._row("SELECT * FROM automod_config WHERE guild_id = ?", guild_id)
        row["bypass_roles"] = json.loads(row.get("bypass_roles") or "[]")
        return row

    async def update_automod_setting(self, guild_id: int, setting: str, value):
        if setting not in ALLOWED_AUTOMOD_SETTINGS:
            raise ValueError(f"Paramètre '{setting}' non autorisé.")
        if isinstance(value, list):
            value = json.dumps(value)
        await self._exec(
            f"INSERT INTO automod_config (guild_id, {setting}) VALUES (?, ?)"
            f" ON CONFLICT(guild_id) DO UPDATE SET {setting} = excluded.{setting}",
            guild_id, value
        )

    # ── Tickets ───────────────────────────────────────────────────────────────

    async def get_ticket_config(self, guild_id: int) -> dict:
        row = await self._row("SELECT * FROM ticket_config WHERE guild_id = ?", guild_id)
        if not row:
            await self._exec("INSERT OR IGNORE INTO ticket_config (guild_id) VALUES (?)", guild_id)
            row = await self._row("SELECT * FROM ticket_config WHERE guild_id = ?", guild_id)
        row["categories"] = json.loads(row.get("categories") or "[]")
        return row

    async def update_ticket_config(self, guild_id: int, setting: str, value):
        if setting not in ALLOWED_TICKET_SETTINGS:
            raise ValueError(f"Paramètre '{setting}' non autorisé.")
        if isinstance(value, list):
            value = json.dumps(value)
        await self._exec(
            f"INSERT INTO ticket_config (guild_id, {setting}) VALUES (?, ?)"
            f" ON CONFLICT(guild_id) DO UPDATE SET {setting} = excluded.{setting}",
            guild_id, value
        )

    async def increment_ticket_counter(self, guild_id: int) -> int:
        await self._exec("INSERT OR IGNORE INTO ticket_config (guild_id) VALUES (?)", guild_id)
        await self._exec(
            "UPDATE ticket_config SET ticket_counter = ticket_counter + 1 WHERE guild_id = ?", guild_id
        )
        return await self._val("SELECT ticket_counter FROM ticket_config WHERE guild_id = ?", guild_id)

    async def create_ticket(self, guild_id: int, channel_id: int, user_id: int, ticket_number: int, category: str = None):
        await self._exec(
            "INSERT INTO tickets (guild_id, channel_id, user_id, ticket_number, category) VALUES (?, ?, ?, ?, ?)",
            guild_id, channel_id, user_id, ticket_number, category
        )

    async def claim_ticket(self, channel_id: int, user_id: int):
        await self._exec("UPDATE tickets SET claimed_by = ? WHERE channel_id = ?", user_id, channel_id)

    async def unclaim_ticket(self, channel_id: int):
        await self._exec("UPDATE tickets SET claimed_by = NULL WHERE channel_id = ?", channel_id)

    async def get_ticket(self, channel_id: int) -> dict | None:
        return await self._row("SELECT * FROM tickets WHERE channel_id = ?", channel_id)

    async def get_user_open_ticket(self, guild_id: int, user_id: int) -> dict | None:
        return await self._row(
            "SELECT * FROM tickets WHERE guild_id = ? AND user_id = ? AND status = 'open'",
            guild_id, user_id
        )

    async def close_ticket(self, channel_id: int, closed_by: int):
        await self._exec(
            "UPDATE tickets SET status = 'closed', closed_at = datetime('now'), closed_by = ? WHERE channel_id = ?",
            closed_by, channel_id
        )

    # ── Reaction Roles ────────────────────────────────────────────────────────

    async def create_rr_panel(self, guild_id: int, channel_id: int, message_id: int, title: str, description: str = None) -> int:
        cur = await self._exec(
            "INSERT INTO rr_panels (guild_id, channel_id, message_id, title, description) VALUES (?, ?, ?, ?, ?)",
            guild_id, channel_id, message_id, title, description
        )
        return cur.lastrowid

    async def get_rr_panel_by_id(self, panel_id: int, guild_id: int) -> dict | None:
        return await self._row("SELECT * FROM rr_panels WHERE id = ? AND guild_id = ?", panel_id, guild_id)

    async def get_all_rr_panels(self, guild_id: int) -> list:
        return await self._rows("SELECT * FROM rr_panels WHERE guild_id = ? ORDER BY id", guild_id)

    async def get_all_rr_panels_global(self) -> list:
        return await self._rows("SELECT * FROM rr_panels ORDER BY id")

    async def add_rr_button(self, panel_id: int, role_id: int, label: str, emoji: str = None, style: str = "secondary") -> int:
        cur = await self._exec(
            "INSERT INTO rr_buttons (panel_id, role_id, label, emoji, style) VALUES (?, ?, ?, ?, ?)",
            panel_id, role_id, label, emoji, style
        )
        return cur.lastrowid

    async def get_rr_buttons(self, panel_id: int) -> list:
        return await self._rows("SELECT * FROM rr_buttons WHERE panel_id = ? ORDER BY id", panel_id)

    async def remove_rr_button(self, button_id: int, panel_id: int):
        await self._exec("DELETE FROM rr_buttons WHERE id = ? AND panel_id = ?", button_id, panel_id)

    async def delete_rr_panel(self, panel_id: int):
        await self._exec("DELETE FROM rr_panels WHERE id = ?", panel_id)

    # ── Embed Custom Buttons ──────────────────────────────────────────────────

    async def save_embed_button(
        self, guild_id: int, channel_id: int, message_id: int,
        label: str, style: str, emoji: str | None,
        action_type: str, action_data: str, ephemeral: bool, position: int
    ) -> int:
        cur = await self._exec(
            """INSERT INTO embed_custom_buttons
               (guild_id, channel_id, message_id, label, style, emoji, action_type, action_data, ephemeral, position)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            guild_id, channel_id, message_id, label, style, emoji,
            action_type, action_data, int(ephemeral), position
        )
        return cur.lastrowid

    async def get_embed_buttons(self, message_id: int) -> list:
        rows = await self._rows(
            "SELECT * FROM embed_custom_buttons WHERE message_id = ? ORDER BY position", message_id
        )
        for r in rows:
            r["ephemeral"] = bool(r["ephemeral"])
        return rows

    async def get_all_embed_button_message_ids(self) -> list:
        return await self._rows(
            "SELECT DISTINCT message_id FROM embed_custom_buttons WHERE action_type != 'link'"
        )

    async def delete_embed_buttons_for_message(self, message_id: int):
        await self._exec("DELETE FROM embed_custom_buttons WHERE message_id = ?", message_id)

    # ── Anti-Raid ─────────────────────────────────────────────────────────────

    async def get_antiraid_config(self, guild_id: int) -> dict:
        row = await self._row("SELECT * FROM antiraid_config WHERE guild_id = ?", guild_id)
        if not row:
            await self._exec("INSERT OR IGNORE INTO antiraid_config (guild_id) VALUES (?)", guild_id)
            row = await self._row("SELECT * FROM antiraid_config WHERE guild_id = ?", guild_id)
        return row

    async def update_antiraid_setting(self, guild_id: int, setting: str, value):
        if setting not in ALLOWED_ANTIRAID_SETTINGS:
            raise ValueError(f"Paramètre '{setting}' non autorisé.")
        await self._exec(
            f"INSERT INTO antiraid_config (guild_id, {setting}) VALUES (?, ?)"
            f" ON CONFLICT(guild_id) DO UPDATE SET {setting} = excluded.{setting}",
            guild_id, value
        )

    # ── Auto-sanctions ────────────────────────────────────────────────────────

    async def get_autosanctions(self, guild_id: int) -> list:
        return await self._rows("SELECT * FROM autosanctions WHERE guild_id = ? ORDER BY warn_count", guild_id)

    async def add_autosanction(self, guild_id: int, warn_count: int, action: str, duration: int | None):
        await self._exec(
            "INSERT INTO autosanctions (guild_id, warn_count, action, duration) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(guild_id, warn_count) DO UPDATE SET action = excluded.action, duration = excluded.duration",
            guild_id, warn_count, action, duration
        )

    async def remove_autosanction(self, guild_id: int, warn_count: int) -> bool:
        cur = await self._exec("DELETE FROM autosanctions WHERE guild_id = ? AND warn_count = ?", guild_id, warn_count)
        return cur.rowcount > 0

    # ── Reports ───────────────────────────────────────────────────────────────

    async def create_report(self, guild_id: int, message_id: int, reporter_id: int, reported_id: int, reason: str) -> int:
        cur = await self._exec(
            "INSERT INTO reports (guild_id, message_id, reporter_id, reported_id, reason) VALUES (?, ?, ?, ?, ?)",
            guild_id, message_id, reporter_id, reported_id, reason
        )
        return cur.lastrowid

    async def get_report_by_msg(self, message_id: int) -> dict | None:
        return await self._row("SELECT * FROM reports WHERE message_id = ?", message_id)

    async def resolve_report(self, report_id: int):
        await self._exec("UPDATE reports SET resolved = 1 WHERE id = ?", report_id)

    async def get_unresolved_reports(self) -> list:
        return await self._rows("SELECT * FROM reports WHERE resolved = 0")

    # ── XP Roles ──────────────────────────────────────────────────────────────

    async def get_xp_roles(self, guild_id: int) -> list:
        return await self._rows("SELECT * FROM xp_roles WHERE guild_id = ? ORDER BY level", guild_id)

    async def add_xp_role(self, guild_id: int, level: int, role_id: int):
        await self._exec(
            "INSERT INTO xp_roles (guild_id, level, role_id) VALUES (?, ?, ?)"
            " ON CONFLICT(guild_id, level) DO UPDATE SET role_id = excluded.role_id",
            guild_id, level, role_id
        )

    async def remove_xp_role(self, guild_id: int, level: int) -> bool:
        cur = await self._exec("DELETE FROM xp_roles WHERE guild_id = ? AND level = ?", guild_id, level)
        return cur.rowcount > 0

    # ── TempVoice Config ──────────────────────────────────────────────────────

    async def get_tempvoice_config(self, guild_id: int) -> dict:
        row = await self._row("SELECT * FROM tempvoice_config WHERE guild_id = ?", guild_id)
        if not row:
            await self._exec("INSERT OR IGNORE INTO tempvoice_config (guild_id) VALUES (?)", guild_id)
            row = await self._row("SELECT * FROM tempvoice_config WHERE guild_id = ?", guild_id)
        return row

    async def update_tempvoice_config(self, guild_id: int, setting: str, value):
        if setting not in ALLOWED_TEMPVOICE_SETTINGS:
            raise ValueError(f"Paramètre '{setting}' non autorisé.")
        await self._exec(
            f"INSERT INTO tempvoice_config (guild_id, {setting}) VALUES (?, ?)"
            f" ON CONFLICT(guild_id) DO UPDATE SET {setting} = excluded.{setting}",
            guild_id, value
        )

    # ── TempVoice Channels ────────────────────────────────────────────────────

    async def create_tempvoice_channel(self, channel_id: int, guild_id: int, owner_id: int, control_msg_id: int | None):
        await self._exec(
            "INSERT OR IGNORE INTO tempvoice_channels (channel_id, guild_id, owner_id, control_msg_id) VALUES (?, ?, ?, ?)",
            channel_id, guild_id, owner_id, control_msg_id
        )

    async def get_tempvoice_channel(self, channel_id: int) -> dict | None:
        return await self._row("SELECT * FROM tempvoice_channels WHERE channel_id = ?", channel_id)

    async def get_tempvoice_by_msg(self, msg_id: int) -> dict | None:
        return await self._row("SELECT * FROM tempvoice_channels WHERE control_msg_id = ?", msg_id)

    async def get_all_tempvoice_channels(self) -> list:
        return await self._rows("SELECT * FROM tempvoice_channels")

    async def update_tempvoice_state(self, channel_id: int, locked: int = None, hidden: int = None):
        if locked is not None:
            await self._exec("UPDATE tempvoice_channels SET locked = ? WHERE channel_id = ?", locked, channel_id)
        if hidden is not None:
            await self._exec("UPDATE tempvoice_channels SET hidden = ? WHERE channel_id = ?", hidden, channel_id)

    async def update_tempvoice_allowed(self, channel_id: int, allowed_users: list):
        await self._exec(
            "UPDATE tempvoice_channels SET allowed_users = ? WHERE channel_id = ?",
            json.dumps(allowed_users), channel_id
        )

    async def update_tempvoice_owner(self, channel_id: int, owner_id: int):
        await self._exec("UPDATE tempvoice_channels SET owner_id = ? WHERE channel_id = ?", owner_id, channel_id)

    async def delete_tempvoice_channel(self, channel_id: int):
        await self._exec("DELETE FROM tempvoice_channels WHERE channel_id = ?", channel_id)
