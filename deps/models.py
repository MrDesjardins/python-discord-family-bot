"""Domain models."""

import dataclasses
import datetime
from typing import Optional


def _parse_dt(value) -> datetime.datetime:
    """Coerce a DB value (datetime or ISO string) into a datetime."""
    if isinstance(value, datetime.datetime):
        return value
    return datetime.datetime.fromisoformat(value)


@dataclasses.dataclass
class Reminder:
    """A reminder, either recurring-daily-until-acknowledged or one-time."""

    id: int
    guild_id: int
    channel_id: int
    message_id: Optional[int]
    author_id: int
    content: str
    created_at: datetime.datetime
    is_recurring: bool
    remind_time: Optional[str]  # "HH:MM" for recurring reminders
    remind_at: Optional[datetime.datetime]  # UTC datetime for one-time reminders
    is_active: bool
    acknowledged: bool
    last_reminded_date: Optional[str]  # "YYYY-MM-DD" in guild tz, dedupe for recurring
    target_id: Optional[int] = None  # who to ping; None means the author

    @property
    def ping_user_id(self) -> int:
        """The user to ping: the optional target, else the author."""
        return self.target_id if self.target_id is not None else self.author_id

    @staticmethod
    def from_db_row(row: tuple) -> "Reminder":
        """Build a Reminder from a SELECT * row of the reminder table."""
        return Reminder(
            id=row[0],
            guild_id=row[1],
            channel_id=row[2],
            message_id=row[3],
            author_id=row[4],
            content=row[5],
            created_at=row[6] if isinstance(row[6], datetime.datetime) else datetime.datetime.fromisoformat(row[6]),
            is_recurring=bool(row[7]),
            remind_time=row[8],
            remind_at=(
                row[9]
                if row[9] is None or isinstance(row[9], datetime.datetime)
                else datetime.datetime.fromisoformat(row[9])
            ),
            is_active=bool(row[10]),
            acknowledged=bool(row[11]),
            last_reminded_date=row[12],
            target_id=row[13],
        )


@dataclasses.dataclass
class CalendarEvent:
    """A Google Calendar event mirrored in the local database."""

    event_id: str
    calendar_id: str
    summary: str
    description: Optional[str]
    location: Optional[str]
    start_utc: datetime.datetime
    end_utc: Optional[datetime.datetime]
    html_link: Optional[str]
    reminded: bool = False

    @staticmethod
    def from_db_row(row: tuple) -> "CalendarEvent":
        """Build a CalendarEvent from a SELECT * row of the calendar_event table."""
        return CalendarEvent(
            event_id=row[0],
            calendar_id=row[1],
            summary=row[2] or "(no title)",
            description=row[3],
            location=row[4],
            start_utc=_parse_dt(row[5]),
            end_utc=_parse_dt(row[6]) if row[6] is not None else None,
            html_link=row[7],
            reminded=bool(row[8]),
        )
