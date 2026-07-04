"""Google Calendar access via a service account.

The service-account JSON path comes from the ``GOOGLE_SERVICE_ACCOUNT_FILE``
environment variable (a secret). Share the target calendar (e.g. "Équipe PM")
with the service account's email address (Viewer) so it can read events.

Network/SDK calls here are blocking; callers should run them via
``asyncio.to_thread`` from async code.
"""

from __future__ import annotations

import datetime
import os
import unicodedata
from typing import List, Optional

from deps.log import print_error_log, print_log
from deps.models import CalendarEvent

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
SERVICE_ACCOUNT_ENV = "GOOGLE_SERVICE_ACCOUNT_FILE"


def _build_service():
    """Build a Google Calendar API service client from the service-account file."""
    # Imported lazily so the bot (and tests) don't require googleapiclient unless
    # the calendar feature is actually used.
    from google.oauth2 import service_account  # pylint: disable=import-outside-toplevel
    from googleapiclient.discovery import build  # pylint: disable=import-outside-toplevel

    path = os.getenv(SERVICE_ACCOUNT_ENV)
    if not path:
        raise RuntimeError(f"{SERVICE_ACCOUNT_ENV} is not set")
    if not os.path.exists(path):
        raise RuntimeError(f"{SERVICE_ACCOUNT_ENV} points to a missing file: {path}")
    credentials = service_account.Credentials.from_service_account_file(path, scopes=SCOPES)
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def _normalize_name(value: str) -> str:
    """Casefold + Unicode-normalize so 'Équipe' (NFC) and 'Équipe' (NFD) compare equal."""
    return unicodedata.normalize("NFC", value).strip().casefold()


def list_visible_calendars(service=None) -> List[dict]:
    """Return the raw calendarList entries the service account can see.

    Used for debugging "calendar not found": every calendar shared with (and
    accepted into) the service account's list appears here.
    """
    service = service or _build_service()
    page_token = None
    entries: List[dict] = []
    while True:
        calendar_list = service.calendarList().list(pageToken=page_token).execute()
        entries.extend(calendar_list.get("items", []))
        page_token = calendar_list.get("nextPageToken")
        if not page_token:
            break
    return entries


def find_calendar_id_by_name(name: str, service=None) -> Optional[str]:
    """Return the calendarId whose summary matches ``name`` (case/accent-insensitive)."""
    service = service or _build_service()
    target = _normalize_name(name)
    for entry in list_visible_calendars(service):
        summary = _normalize_name(entry.get("summaryOverride") or entry.get("summary") or "")
        if summary == target:
            return entry.get("id")
    return None


def _parse_event_datetime(node: dict) -> Optional[datetime.datetime]:
    """Parse a Google event start/end node into a tz-aware UTC datetime."""
    if not node:
        return None
    if "dateTime" in node:
        value = node["dateTime"].replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(value)
    elif "date" in node:
        # All-day event: treat as midnight UTC of that date.
        dt = datetime.datetime.fromisoformat(node["date"])
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def normalize_event(item: dict, calendar_id: str) -> Optional[CalendarEvent]:
    """Convert a raw Google event dict into a CalendarEvent (or None if unusable)."""
    start = _parse_event_datetime(item.get("start", {}))
    if start is None:
        return None
    return CalendarEvent(
        event_id=item["id"],
        calendar_id=calendar_id,
        summary=item.get("summary") or "(no title)",
        description=item.get("description"),
        location=item.get("location"),
        start_utc=start,
        end_utc=_parse_event_datetime(item.get("end", {})),
        html_link=item.get("htmlLink"),
        reminded=False,
    )


def fetch_upcoming_events(
    calendar_id: str, lookahead_hours: int, service=None, now: Optional[datetime.datetime] = None
) -> List[CalendarEvent]:
    """Fetch single (expanded) events from ``now`` up to ``lookahead_hours`` ahead.

    ``now`` lets the caller pin the window start so a follow-up prune of local rows
    (see ``delete_stale_events``) uses exactly the same bounds as the fetch.
    """
    service = service or _build_service()
    now = now or datetime.datetime.now(datetime.timezone.utc)
    time_max = now + datetime.timedelta(hours=lookahead_hours)
    events: List[CalendarEvent] = []
    page_token = None
    while True:
        response = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=now.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                pageToken=page_token,
            )
            .execute()
        )
        for item in response.get("items", []):
            event = normalize_event(item, calendar_id)
            if event is not None:
                events.append(event)
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    print_log(f"google_calendar: fetched {len(events)} event(s) from {calendar_id}")
    return events


def is_configured() -> bool:
    """Return True if a service-account file path is set and exists."""
    path = os.getenv(SERVICE_ACCOUNT_ENV)
    if not path or not os.path.exists(path):
        print_error_log(f"google_calendar: {SERVICE_ACCOUNT_ENV} not set or file missing; calendar disabled")
        return False
    return True
