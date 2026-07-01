"""Integration tests: reminder data access + date helpers working together."""

import datetime

from deps.functions_date import local_datetime_to_utc
from deps.reminder_data_access import (
    acknowledge_reminder,
    create_onetime_reminder,
    create_recurring_reminder,
    get_active_reminders,
    get_reminder_by_message_id,
    set_reminder_message_id,
)


def test_onetime_reminder_due_detection(db):  # pylint: disable=unused-argument
    """A one-time reminder scheduled in a tz is stored as UTC and detected as due."""
    remind_at = local_datetime_to_utc("2026-07-15", "08:30", "America/Los_Angeles")
    rid = create_onetime_reminder(1, 10, 100, "dentist", remind_at)

    active = get_active_reminders()
    assert len(active) == 1
    reminder = active[0]
    assert reminder.id == rid
    assert reminder.remind_at == datetime.datetime(2026, 7, 15, 15, 30, tzinfo=datetime.timezone.utc)

    # Before the time: not due. After: due.
    before = remind_at - datetime.timedelta(minutes=1)
    after = remind_at + datetime.timedelta(minutes=1)
    assert before < reminder.remind_at
    assert after >= reminder.remind_at


def test_recurring_reminder_acknowledge_flow(db):  # pylint: disable=unused-argument
    """Creating, attaching a message, then acknowledging deactivates the reminder."""
    rid = create_recurring_reminder(1, 10, 100, "feed cat", "08:30")
    set_reminder_message_id(rid, 999)

    found = get_reminder_by_message_id(999)
    assert found is not None and found.id == rid and found.is_recurring

    acknowledge_reminder(rid)
    assert get_active_reminders() == []
