"""System test: full reminder CRUD lifecycle on a file-based copy of a seeded DB."""

import datetime

from deps.reminder_data_access import (
    create_onetime_reminder,
    deactivate_reminder,
    get_active_reminders,
    mark_recurring_reminded,
)


def test_reminder_crud_on_seeded_copy(system_db):
    """INSERT, UPDATE and DELETE-by-deactivate against a real copied database."""
    cur = system_db.get_cursor()

    # The seed DB already contains one active recurring reminder.
    active = get_active_reminders()
    assert len(active) == 1
    seeded = active[0]
    assert seeded.content == "seed reminder"

    # INSERT a new one-time reminder (real SQL).
    when = datetime.datetime(2030, 1, 1, 16, 30, tzinfo=datetime.timezone.utc)
    new_id = create_onetime_reminder(1, 10, 100, "new event", when)
    assert len(get_active_reminders()) == 2

    # UPDATE: mark the recurring reminder as reminded today.
    mark_recurring_reminded(seeded.id, "2026-06-29")
    cur.execute("SELECT last_reminded_date FROM reminder WHERE id = ?", (seeded.id,))
    assert cur.fetchone()[0] == "2026-06-29"

    # DELETE (logical): deactivate the new reminder.
    deactivate_reminder(new_id)
    remaining = {r.id for r in get_active_reminders()}
    assert new_id not in remaining
    assert seeded.id in remaining

    # Hard DELETE via raw SQL to prove real row removal on the copy.
    cur.execute("DELETE FROM reminder WHERE id = ?", (new_id,))
    system_db.get_conn().commit()
    cur.execute("SELECT COUNT(*) FROM reminder")
    assert cur.fetchone()[0] == 1
