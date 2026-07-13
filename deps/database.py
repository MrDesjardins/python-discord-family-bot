"""SQLite connection + schema for the family bot.

A single shared :class:`DatabaseManager` (instantiated as ``database_manager``)
owns the connection. WAL mode is enabled for better concurrent read/write.
"""

import datetime
import os
import sqlite3
from typing import Optional

from deps.log import print_log

DATABASE_NAME = os.getenv("DATABASE_NAME", "family_bot.db")
DATABASE_NAME_TEST = "family_bot_test.db"


def adapt_datetime(value: datetime.datetime) -> str:
    """Store datetimes as ISO 8601 strings."""
    return value.isoformat()


def convert_datetime(value: bytes) -> datetime.datetime:
    """Parse an ISO 8601 string back into a datetime."""
    return datetime.datetime.fromisoformat(value.decode())


class DatabaseManager:
    """Owns the SQLite connection and creates the schema."""

    def __init__(self, name: str) -> None:
        sqlite3.register_adapter(datetime.datetime, adapt_datetime)
        sqlite3.register_converter("datetime", convert_datetime)
        self.name = ""
        self.conn: Optional[sqlite3.Connection] = None
        self.cursor: Optional[sqlite3.Cursor] = None
        self.set_database_name(name)

    def set_database_name(self, name: str) -> None:
        """(Re)open the connection against ``name`` and ensure the schema."""
        if self.conn is not None:
            try:
                self.conn.close()
            except sqlite3.Error:
                pass
        self.name = name
        self.conn = sqlite3.connect(name, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA foreign_keys=ON;")
        self.cursor = self.conn.cursor()
        self.init_database()
        print_log(f"DatabaseManager: connected to {name}")

    def get_database_name(self) -> str:
        """Return the current database file name."""
        return self.name

    def get_conn(self) -> sqlite3.Connection:
        """Return the live connection."""
        assert self.conn is not None
        return self.conn

    def get_cursor(self) -> sqlite3.Cursor:
        """Return the live cursor."""
        assert self.cursor is not None
        return self.cursor

    def drop_all_tables(self) -> None:
        """Drop every table (used by tests)."""
        cur = self.get_cursor()
        cur.execute("DROP TABLE IF EXISTS reminder")
        cur.execute("DROP TABLE IF EXISTS message")
        cur.execute("DROP TABLE IF EXISTS calendar_event")
        cur.execute("DROP TABLE IF EXISTS bot_state")
        self.get_conn().commit()
        self.init_database()

    def init_database(self) -> None:
        """Create tables and indexes if they do not exist."""
        cur = self.get_cursor()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS reminder (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id           INTEGER NOT NULL,
                channel_id         INTEGER NOT NULL,
                message_id         INTEGER,
                author_id          INTEGER NOT NULL,
                target_id          INTEGER,
                content            TEXT NOT NULL,
                created_at         datetime NOT NULL,
                is_recurring       INTEGER NOT NULL,
                remind_time        TEXT,
                remind_at          datetime,
                is_active          INTEGER NOT NULL DEFAULT 1,
                acknowledged       INTEGER NOT NULL DEFAULT 0,
                last_reminded_date TEXT
            )
            """
        )
        # Databases created before the optional target existed lack the column;
        # NULL means "ping the author".
        cur.execute("PRAGMA table_info(reminder)")
        if "target_id" not in {row[1] for row in cur.fetchall()}:
            cur.execute("ALTER TABLE reminder ADD COLUMN target_id INTEGER")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_reminder_active ON reminder(is_active)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_reminder_message ON reminder(message_id)")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS message (
                message_id   INTEGER PRIMARY KEY,
                guild_id     INTEGER,
                channel_id   INTEGER NOT NULL,
                channel_name TEXT,
                author_id    INTEGER NOT NULL,
                author_name  TEXT,
                content      TEXT NOT NULL,
                created_at   datetime NOT NULL,
                embedding    BLOB
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_message_guild ON message(guild_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_message_created ON message(created_at)")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_message_embedding_null ON message(embedding) WHERE embedding IS NULL"
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS calendar_event (
                event_id    TEXT PRIMARY KEY,
                calendar_id TEXT NOT NULL,
                summary     TEXT,
                description TEXT,
                location    TEXT,
                start_utc   datetime NOT NULL,
                end_utc     datetime,
                html_link   TEXT,
                reminded    INTEGER NOT NULL DEFAULT 0,
                updated_at  datetime NOT NULL
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_calendar_start ON calendar_event(start_utc)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_calendar_reminded ON calendar_event(reminded)")

        # Small key/value store for cross-restart bot state (e.g. the day the daily
        # summary was last posted, so a restart doesn't re-post it).
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_state (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )

        self.get_conn().commit()


database_manager = DatabaseManager(DATABASE_NAME_TEST if os.getenv("ENV") == "test" else DATABASE_NAME)
