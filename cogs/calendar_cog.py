"""Google Calendar: mirror the configured calendar and remind before events."""

import asyncio
import datetime
from typing import Optional

import discord
from discord.ext import commands, tasks

from deps.calendar_data_access import (
    delete_past_events,
    get_events_needing_reminder,
    mark_event_reminded,
    upsert_event,
)
from deps.config import get_config
from deps.functions_date import get_tz
from deps.google_calendar import fetch_upcoming_events, find_calendar_id_by_name, is_configured
from deps.log import print_error_log, print_log
from deps.models import CalendarEvent
from deps.mybot import MyBot


class CalendarCog(commands.Cog):
    """Polls Google Calendar and posts reminders 30 minutes before events."""

    def __init__(self, bot: MyBot) -> None:
        self.bot = bot
        self.calendar_id: Optional[str] = None
        config = get_config()
        if not config.calendar.enabled:
            print_log("calendar: disabled in config.yaml; not starting loops")
            return
        if not is_configured():
            print_log("calendar: no service-account file; not starting loops")
            return
        self.poll_loop.change_interval(minutes=config.calendar.poll_interval_minutes)
        self.poll_loop.start()
        self.reminder_loop.start()

    async def cog_unload(self) -> None:
        """Stop loops on unload."""
        self.poll_loop.cancel()
        self.reminder_loop.cancel()

    async def _resolve_calendar_id(self) -> Optional[str]:
        """Resolve and cache the calendarId for the configured calendar."""
        if self.calendar_id is not None:
            return self.calendar_id
        config = get_config()
        # An explicit calendar_id is authoritative: a calendar shared with a service
        # account is reachable by id even though it never appears in calendarList().
        if config.calendar.calendar_id:
            self.calendar_id = config.calendar.calendar_id
            print_log(f"calendar: using configured calendar_id {self.calendar_id}")
            return self.calendar_id
        name = config.calendar.name
        try:
            self.calendar_id = await asyncio.to_thread(find_calendar_id_by_name, name)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print_error_log(f"calendar: failed to resolve calendar '{name}': {exc}")
            return None
        if self.calendar_id is None:
            print_error_log(
                f"calendar: no calendar named '{name}' visible to the service account. "
                "Did you share it with the service-account email?"
            )
        else:
            print_log(f"calendar: resolved '{name}' -> {self.calendar_id}")
        return self.calendar_id

    @tasks.loop(minutes=15)
    async def poll_loop(self) -> None:
        """Refresh upcoming events from Google into the local database."""
        calendar_id = await self._resolve_calendar_id()
        if calendar_id is None:
            return
        config = get_config()
        try:
            events = await asyncio.to_thread(fetch_upcoming_events, calendar_id, config.calendar.lookahead_hours)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print_error_log(f"calendar.poll_loop: fetch failed: {exc}")
            return
        for event in events:
            try:
                upsert_event(event)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                print_error_log(f"calendar.poll_loop: upsert failed for {event.event_id}: {exc}")
        # Housekeeping: drop events that started more than a day ago.
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
        delete_past_events(cutoff)

    @tasks.loop(seconds=60)
    async def reminder_loop(self) -> None:
        """Ping the calendar channel for events starting within the lead window."""
        config = get_config()
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        due = get_events_needing_reminder(now_utc, config.calendar.reminder_lead_minutes)
        if not due:
            return
        channel = self.bot.get_channel(config.channels.calendar)
        if not isinstance(channel, discord.TextChannel):
            print_error_log(f"calendar: calendar channel {config.channels.calendar} not found")
            return
        for event in due:
            try:
                await channel.send(self._format_reminder(event, config.reminders.timezone))
                mark_event_reminded(event.event_id)
                print_log(f"calendar: reminded for event {event.event_id} ({event.summary})")
            except discord.DiscordException as exc:
                print_error_log(f"calendar.reminder_loop: send failed for {event.event_id}: {exc}")

    @staticmethod
    def _format_reminder(event: CalendarEvent, timezone_name: str) -> str:
        """Build the reminder message for an event."""
        local_start = event.start_utc.astimezone(get_tz(timezone_name))
        minutes = max(1, round((event.start_utc - datetime.datetime.now(datetime.timezone.utc)).total_seconds() / 60))
        lines = [f"📅 **In {minutes} min**: {event.summary}", f"🕒 {local_start:%a %b %d, %H:%M} ({timezone_name})"]
        if event.location:
            lines.append(f"📍 {event.location}")
        if event.html_link:
            lines.append(f"<{event.html_link}>")
        return "\n".join(lines)

    @poll_loop.before_loop
    async def before_poll_loop(self) -> None:
        """Wait until the bot is ready before polling."""
        await self.bot.wait_until_ready()

    @reminder_loop.before_loop
    async def before_reminder_loop(self) -> None:
        """Wait until the bot is ready before reminding."""
        await self.bot.wait_until_ready()


async def setup(bot: MyBot) -> None:
    """discord.py extension entry point."""
    await bot.add_cog(CalendarCog(bot))
