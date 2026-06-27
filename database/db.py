import asyncpg
import os

ALLOWED_SETTINGS = {
    "log_channel_id", "welcome_channel_id", "goodbye_channel_id",
    "autorole_id", "welcome_message", "goodbye_message"
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


class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", 5432)),
            database=os.getenv("DB_NAME", "discordbot"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD"),
        )
        await self._init_tables()

    async def _init_tables(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id            BIGINT PRIMARY KEY,
                    log_channel_id      BIGINT,
                    welcome_channel_id  BIGINT,
                    goodbye_channel_id  BIGINT,
                    autorole_id         BIGINT,
                    welcome_message     TEXT DEFAULT 'Bienvenue {mention} sur **{server}** !',
                    goodbye_message     TEXT DEFAULT 'Au revoir **{name}**, bonne continuation !'
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS warnings (
                    id              SERIAL PRIMARY KEY,
                    guild_id        BIGINT NOT NULL,
                    user_id         BIGINT NOT NULL,
                    moderator_id    BIGINT NOT NULL,
                    reason          TEXT NOT NULL DEFAULT 'Aucune raison fournie',
                    created_at      TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS xp (
                    guild_id    BIGINT NOT NULL,
                    user_id     BIGINT NOT NULL,
                    xp          INTEGER NOT NULL DEFAULT 0,
                    level       INTEGER NOT NULL DEFAULT 0,
                    messages    INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS temp_bans (
                    id              SERIAL PRIMARY KEY,
                    guild_id        BIGINT NOT NULL,
                    user_id         BIGINT NOT NULL,
                    moderator_id    BIGINT NOT NULL,
                    reason          TEXT NOT NULL DEFAULT 'Aucune raison fournie',
                    unban_at        TIMESTAMPTZ NOT NULL,
                    created_at      TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS automod_config (
                    guild_id            BIGINT PRIMARY KEY,
                    enabled             BOOLEAN DEFAULT TRUE,
                    spam_enabled        BOOLEAN DEFAULT TRUE,
                    spam_threshold      INTEGER DEFAULT 5,
                    spam_window         INTEGER DEFAULT 5,
                    spam_action         TEXT DEFAULT 'mute',
                    invite_enabled      BOOLEAN DEFAULT FALSE,
                    invite_action       TEXT DEFAULT 'warn',
                    caps_enabled        BOOLEAN DEFAULT FALSE,
                    caps_threshold      INTEGER DEFAULT 70,
                    caps_min_length     INTEGER DEFAULT 10,
                    caps_action         TEXT DEFAULT 'warn',
                    mention_enabled     BOOLEAN DEFAULT FALSE,
                    mention_threshold   INTEGER DEFAULT 5,
                    mention_action      TEXT DEFAULT 'mute',
                    flood_enabled       BOOLEAN DEFAULT TRUE,
                    flood_threshold     INTEGER DEFAULT 3,
                    flood_action        TEXT DEFAULT 'warn',
                    bypass_roles        BIGINT[] DEFAULT '{}'
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS antiraid_config (
                    guild_id            BIGINT PRIMARY KEY,
                    enabled             BOOLEAN DEFAULT FALSE,
                    join_threshold      INTEGER DEFAULT 10,
                    join_window         INTEGER DEFAULT 30,
                    min_account_age     INTEGER DEFAULT 0,
                    action              TEXT DEFAULT 'kick',
                    alert_channel_id    BIGINT,
                    lockdown_active     BOOLEAN DEFAULT FALSE
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ticket_config (
                    guild_id            BIGINT PRIMARY KEY,
                    category_id         BIGINT,
                    staff_role_id       BIGINT,
                    log_channel_id      BIGINT,
                    ticket_counter      INTEGER DEFAULT 0,
                    panel_message_id    BIGINT,
                    panel_channel_id    BIGINT,
                    embed_color         INTEGER DEFAULT 5793266,
                    welcome_message     TEXT,
                    categories          TEXT[] DEFAULT '{}'
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    id              SERIAL PRIMARY KEY,
                    guild_id        BIGINT NOT NULL,
                    channel_id      BIGINT NOT NULL UNIQUE,
                    user_id         BIGINT NOT NULL,
                    ticket_number   INTEGER NOT NULL,
                    category        TEXT,
                    claimed_by      BIGINT,
                    status          TEXT DEFAULT 'open',
                    created_at      TIMESTAMPTZ DEFAULT NOW(),
                    closed_at       TIMESTAMPTZ,
                    closed_by       BIGINT
                )
            """)
            # Migrations pour les serveurs déjà existants
            for col in [
                "ALTER TABLE ticket_config ADD COLUMN IF NOT EXISTS embed_color INTEGER DEFAULT 5793266",
                "ALTER TABLE ticket_config ADD COLUMN IF NOT EXISTS welcome_message TEXT",
                "ALTER TABLE ticket_config ADD COLUMN IF NOT EXISTS categories TEXT[] DEFAULT '{}'",
                "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS category TEXT",
                "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS claimed_by BIGINT",
            ]:
                await conn.execute(col)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS rr_panels (
                    id          SERIAL PRIMARY KEY,
                    guild_id    BIGINT NOT NULL,
                    channel_id  BIGINT NOT NULL,
                    message_id  BIGINT NOT NULL UNIQUE,
                    title       TEXT NOT NULL,
                    description TEXT
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS rr_buttons (
                    id          SERIAL PRIMARY KEY,
                    panel_id    INTEGER REFERENCES rr_panels(id) ON DELETE CASCADE,
                    role_id     BIGINT NOT NULL,
                    label       TEXT NOT NULL,
                    emoji       TEXT,
                    style       TEXT DEFAULT 'secondary'
                )
            """)

    async def close(self):
        if self.pool:
            await self.pool.close()

    # ── Guild settings ──────────────────────────────────────────────────────

    async def get_guild_settings(self, guild_id: int) -> dict:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM guild_settings WHERE guild_id = $1", guild_id
            )
            if not row:
                await conn.execute(
                    "INSERT INTO guild_settings (guild_id) VALUES ($1) ON CONFLICT DO NOTHING",
                    guild_id
                )
                row = await conn.fetchrow(
                    "SELECT * FROM guild_settings WHERE guild_id = $1", guild_id
                )
            return dict(row)

    async def update_guild_setting(self, guild_id: int, setting: str, value):
        if setting not in ALLOWED_SETTINGS:
            raise ValueError(f"Paramètre '{setting}' non autorisé.")
        async with self.pool.acquire() as conn:
            await conn.execute(
                f"""
                INSERT INTO guild_settings (guild_id, {setting})
                VALUES ($1, $2)
                ON CONFLICT (guild_id) DO UPDATE SET {setting} = $2
                """,
                guild_id, value
            )

    # ── Warnings ────────────────────────────────────────────────────────────

    async def add_warning(self, guild_id: int, user_id: int, moderator_id: int, reason: str) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO warnings (guild_id, user_id, moderator_id, reason)
                VALUES ($1, $2, $3, $4) RETURNING id
                """,
                guild_id, user_id, moderator_id, reason
            )
            return row["id"]

    async def get_warnings(self, guild_id: int, user_id: int) -> list:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT * FROM warnings WHERE guild_id = $1 AND user_id = $2 ORDER BY created_at DESC",
                guild_id, user_id
            )

    async def get_warning_count(self, guild_id: int, user_id: int) -> int:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM warnings WHERE guild_id = $1 AND user_id = $2",
                guild_id, user_id
            )

    async def remove_warning(self, warning_id: int, guild_id: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM warnings WHERE id = $1 AND guild_id = $2",
                warning_id, guild_id
            )
            return result != "DELETE 0"

    async def clear_warnings(self, guild_id: int, user_id: int) -> int:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM warnings WHERE guild_id = $1 AND user_id = $2",
                guild_id, user_id
            )
            return int(result.split()[-1])

    # ── XP ──────────────────────────────────────────────────────────────────

    async def get_xp(self, guild_id: int, user_id: int) -> dict:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM xp WHERE guild_id = $1 AND user_id = $2",
                guild_id, user_id
            )
            if row:
                return dict(row)
            return {"guild_id": guild_id, "user_id": user_id, "xp": 0, "level": 0, "messages": 0}

    async def add_xp(self, guild_id: int, user_id: int, amount: int) -> dict:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO xp (guild_id, user_id, xp, messages)
                VALUES ($1, $2, $3, 1)
                ON CONFLICT (guild_id, user_id)
                DO UPDATE SET xp = xp.xp + $3, messages = xp.messages + 1
                """,
                guild_id, user_id, amount
            )
            row = await conn.fetchrow(
                "SELECT * FROM xp WHERE guild_id = $1 AND user_id = $2",
                guild_id, user_id
            )
            return dict(row)

    async def set_xp(self, guild_id: int, user_id: int, amount: int, level: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO xp (guild_id, user_id, xp, level)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (guild_id, user_id)
                DO UPDATE SET xp = $3, level = $4
                """,
                guild_id, user_id, amount, level
            )

    async def reset_xp(self, guild_id: int, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM xp WHERE guild_id = $1 AND user_id = $2",
                guild_id, user_id
            )

    async def get_leaderboard(self, guild_id: int, limit: int = 10) -> list:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT * FROM xp WHERE guild_id = $1 ORDER BY xp DESC LIMIT $2",
                guild_id, limit
            )

    async def get_rank(self, guild_id: int, user_id: int) -> int:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                """
                SELECT COUNT(*) + 1 FROM xp
                WHERE guild_id = $1
                AND xp > (SELECT COALESCE(xp, 0) FROM xp WHERE guild_id = $1 AND user_id = $2)
                """,
                guild_id, user_id
            )

    # ── Temp bans ────────────────────────────────────────────────────────────

    async def add_temp_ban(self, guild_id: int, user_id: int, moderator_id: int, reason: str, unban_at):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO temp_bans (guild_id, user_id, moderator_id, reason, unban_at)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT DO NOTHING
                """,
                guild_id, user_id, moderator_id, reason, unban_at
            )

    async def get_expired_bans(self) -> list:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT * FROM temp_bans WHERE unban_at <= NOW()"
            )

    async def remove_temp_ban(self, guild_id: int, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM temp_bans WHERE guild_id = $1 AND user_id = $2",
                guild_id, user_id
            )

    # ── AutoMod ──────────────────────────────────────────────────────────────

    async def get_automod_config(self, guild_id: int) -> dict:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM automod_config WHERE guild_id = $1", guild_id)
            if not row:
                await conn.execute(
                    "INSERT INTO automod_config (guild_id) VALUES ($1) ON CONFLICT DO NOTHING", guild_id
                )
                row = await conn.fetchrow("SELECT * FROM automod_config WHERE guild_id = $1", guild_id)
            return dict(row)

    async def update_automod_setting(self, guild_id: int, setting: str, value):
        if setting not in ALLOWED_AUTOMOD_SETTINGS:
            raise ValueError(f"Paramètre '{setting}' non autorisé.")
        async with self.pool.acquire() as conn:
            await conn.execute(
                f"""
                INSERT INTO automod_config (guild_id, {setting})
                VALUES ($1, $2)
                ON CONFLICT (guild_id) DO UPDATE SET {setting} = $2
                """,
                guild_id, value
            )

    # ── Tickets ───────────────────────────────────────────────────────────────

    async def get_ticket_config(self, guild_id: int) -> dict:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM ticket_config WHERE guild_id = $1", guild_id)
            if not row:
                await conn.execute(
                    "INSERT INTO ticket_config (guild_id) VALUES ($1) ON CONFLICT DO NOTHING", guild_id
                )
                row = await conn.fetchrow("SELECT * FROM ticket_config WHERE guild_id = $1", guild_id)
            return dict(row)

    async def update_ticket_config(self, guild_id: int, setting: str, value):
        if setting not in ALLOWED_TICKET_SETTINGS:
            raise ValueError(f"Paramètre '{setting}' non autorisé.")
        async with self.pool.acquire() as conn:
            await conn.execute(
                f"""
                INSERT INTO ticket_config (guild_id, {setting})
                VALUES ($1, $2)
                ON CONFLICT (guild_id) DO UPDATE SET {setting} = $2
                """,
                guild_id, value
            )

    async def increment_ticket_counter(self, guild_id: int) -> int:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO ticket_config (guild_id) VALUES ($1) ON CONFLICT DO NOTHING", guild_id
            )
            return await conn.fetchval(
                "UPDATE ticket_config SET ticket_counter = ticket_counter + 1 WHERE guild_id = $1 RETURNING ticket_counter",
                guild_id
            )

    async def create_ticket(self, guild_id: int, channel_id: int, user_id: int, ticket_number: int, category: str = None):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO tickets (guild_id, channel_id, user_id, ticket_number, category) VALUES ($1, $2, $3, $4, $5)",
                guild_id, channel_id, user_id, ticket_number, category
            )

    async def claim_ticket(self, channel_id: int, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE tickets SET claimed_by = $2 WHERE channel_id = $1", channel_id, user_id
            )

    async def unclaim_ticket(self, channel_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE tickets SET claimed_by = NULL WHERE channel_id = $1", channel_id
            )

    async def get_ticket(self, channel_id: int) -> dict | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM tickets WHERE channel_id = $1", channel_id)
            return dict(row) if row else None

    async def get_user_open_ticket(self, guild_id: int, user_id: int) -> dict | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM tickets WHERE guild_id = $1 AND user_id = $2 AND status = 'open'",
                guild_id, user_id
            )
            return dict(row) if row else None

    async def close_ticket(self, channel_id: int, closed_by: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE tickets SET status = 'closed', closed_at = NOW(), closed_by = $2 WHERE channel_id = $1",
                channel_id, closed_by
            )

    # ── Reaction Roles ────────────────────────────────────────────────────────

    async def create_rr_panel(self, guild_id: int, channel_id: int, message_id: int, title: str, description: str = None) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO rr_panels (guild_id, channel_id, message_id, title, description) VALUES ($1, $2, $3, $4, $5) RETURNING id",
                guild_id, channel_id, message_id, title, description
            )
            return row["id"]

    async def get_rr_panel_by_id(self, panel_id: int, guild_id: int) -> dict | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM rr_panels WHERE id = $1 AND guild_id = $2", panel_id, guild_id
            )
            return dict(row) if row else None

    async def get_all_rr_panels(self, guild_id: int) -> list:
        async with self.pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM rr_panels WHERE guild_id = $1 ORDER BY id", guild_id)

    async def get_all_rr_panels_global(self) -> list:
        async with self.pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM rr_panels ORDER BY id")

    async def add_rr_button(self, panel_id: int, role_id: int, label: str, emoji: str = None, style: str = "secondary") -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO rr_buttons (panel_id, role_id, label, emoji, style) VALUES ($1, $2, $3, $4, $5) RETURNING id",
                panel_id, role_id, label, emoji, style
            )
            return row["id"]

    async def get_rr_buttons(self, panel_id: int) -> list:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT * FROM rr_buttons WHERE panel_id = $1 ORDER BY id", panel_id
            )

    async def remove_rr_button(self, button_id: int, panel_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM rr_buttons WHERE id = $1 AND panel_id = $2", button_id, panel_id
            )

    async def delete_rr_panel(self, panel_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM rr_panels WHERE id = $1", panel_id)

    # ── Anti-Raid ─────────────────────────────────────────────────────────────

    async def get_antiraid_config(self, guild_id: int) -> dict:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM antiraid_config WHERE guild_id = $1", guild_id)
            if not row:
                await conn.execute(
                    "INSERT INTO antiraid_config (guild_id) VALUES ($1) ON CONFLICT DO NOTHING", guild_id
                )
                row = await conn.fetchrow("SELECT * FROM antiraid_config WHERE guild_id = $1", guild_id)
            return dict(row)

    async def update_antiraid_setting(self, guild_id: int, setting: str, value):
        if setting not in ALLOWED_ANTIRAID_SETTINGS:
            raise ValueError(f"Paramètre '{setting}' non autorisé.")
        async with self.pool.acquire() as conn:
            await conn.execute(
                f"""
                INSERT INTO antiraid_config (guild_id, {setting})
                VALUES ($1, $2)
                ON CONFLICT (guild_id) DO UPDATE SET {setting} = $2
                """,
                guild_id, value
            )
