import asyncpg
import os

ALLOWED_SETTINGS = {
    "log_channel_id", "welcome_channel_id", "goodbye_channel_id",
    "autorole_id", "welcome_message", "goodbye_message"
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
