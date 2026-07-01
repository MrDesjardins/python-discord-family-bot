"""System test: bot_state key/value CRUD on a file-based copy of a seeded DB."""

from deps.bot_state_data_access import STATE_DAILY_SUMMARY_DATE, get_state, set_state


def test_bot_state_get_set_upsert(system_db):  # pylint: disable=unused-argument
    """Unknown keys read as None; set inserts then upserts in place."""
    assert get_state(STATE_DAILY_SUMMARY_DATE) is None

    set_state(STATE_DAILY_SUMMARY_DATE, "2026-06-30")
    assert get_state(STATE_DAILY_SUMMARY_DATE) == "2026-06-30"

    # Second write updates the same row rather than inserting a duplicate.
    set_state(STATE_DAILY_SUMMARY_DATE, "2026-07-01")
    assert get_state(STATE_DAILY_SUMMARY_DATE) == "2026-07-01"
    cur = system_db.get_cursor()
    cur.execute("SELECT COUNT(*) FROM bot_state WHERE key = ?", (STATE_DAILY_SUMMARY_DATE,))
    assert cur.fetchone()[0] == 1
