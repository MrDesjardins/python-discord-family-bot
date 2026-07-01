"""Pytest fixtures shared across the three test tiers.

Tiers (by filename suffix):
- *_unit_test.py        pure functions / mocked inputs, no database
- *_integration_test.py several modules working together (uses the test DB)
- *_system_test.py      real SQL CRUD against a file-based COPY of a seeded DB
"""

import os
import shutil

import pytest

os.environ.setdefault("ENV", "test")
# Point config-dependent code at the example config during tests.
os.environ.setdefault("CONFIG_FILE", "config.example.yaml")

from deps.database import database_manager  # noqa: E402  pylint: disable=wrong-import-position

TEST_DB = "family_bot_test.db"
SEED_DB = "family_bot_seed.db"
SYSTEM_DB = "family_bot_system.db"


@pytest.fixture()
def db():
    """Clean test database for integration tests (request explicitly)."""
    database_manager.set_database_name(TEST_DB)
    database_manager.drop_all_tables()
    yield database_manager
    database_manager.drop_all_tables()


def _build_seed_database(path: str) -> None:
    """Create a seeded database file that mimics a small 'real' database."""
    import datetime  # local import keeps module import time low

    if os.path.exists(path):
        os.remove(path)
    database_manager.set_database_name(path)
    database_manager.drop_all_tables()
    cur = database_manager.get_cursor()
    now = datetime.datetime(2026, 6, 1, 12, 0, tzinfo=datetime.timezone.utc)
    # A pre-existing recurring reminder.
    cur.execute(
        "INSERT INTO reminder (guild_id, channel_id, message_id, author_id, content, created_at, "
        "is_recurring, remind_time, is_active) VALUES (1, 10, 500, 100, 'seed reminder', ?, 1, '08:30', 1)",
        (now,),
    )
    # A pre-existing calendar event, far in the future so time-based purges don't touch it.
    far_future = datetime.datetime(2099, 1, 1, 12, 0, tzinfo=datetime.timezone.utc)
    cur.execute(
        "INSERT INTO calendar_event (event_id, calendar_id, summary, start_utc, reminded, updated_at) "
        "VALUES ('seed-evt', 'cal1', 'Seed Event', ?, 0, ?)",
        (far_future, now),
    )
    database_manager.get_conn().commit()


@pytest.fixture()
def system_db():
    """A real, file-based COPY of a seeded database for system tests.

    Demonstrates real INSERT/UPDATE/DELETE against an isolated copy that starts
    from seeded data — never the production database.
    """
    _build_seed_database(SEED_DB)
    # Detach from the seed file before copying it.
    database_manager.set_database_name(TEST_DB)
    shutil.copyfile(SEED_DB, SYSTEM_DB)
    database_manager.set_database_name(SYSTEM_DB)
    yield database_manager
    database_manager.set_database_name(TEST_DB)
    for path in (SEED_DB, SYSTEM_DB):
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(path + suffix)
            except FileNotFoundError:
                pass
