"""Background loops: reminder dispatch and embedding backfill."""

import asyncio
import datetime
from typing import Optional

import discord
from discord.ext import commands, tasks

from deps.ai.embeddings import embed_texts, to_blob
from deps.bot_state_data_access import STATE_DAILY_SUMMARY_DATE, get_state, set_state
from deps.calendar_data_access import get_events_in_range
from deps.config import get_config
from deps.daily_summary import chunk_message, day_bounds_utc, format_summary, is_summary_due, reminders_for_day
from deps.functions_date import now_in_tz, parse_time
from deps.log import print_error_log, print_log
from deps.message_data_access import archive_bot_message, get_messages_without_embedding, set_message_embedding
from deps.mybot import MyBot
from deps.reminder_data_access import (
    deactivate_reminder,
    get_active_reminders,
    get_active_reminders_for_guild,
    mark_recurring_reminded,
)


class TasksCog(commands.Cog):
    """Owns the periodic task loops."""

    def __init__(self, bot: MyBot) -> None:
        self.bot = bot
        # Local (guild-tz) date the daily summary was last posted; dedupes within a day.
        # Loaded from the DB in before_daily_summary_loop so restarts don't re-post.
        self._last_summary_date: Optional[str] = None
        self.reminder_loop.start()
        self.embedding_loop.start()
        self.daily_summary_loop.start()

    async def cog_unload(self) -> None:
        """Stop loops when the cog unloads."""
        self.reminder_loop.cancel()
        self.embedding_loop.cancel()
        self.daily_summary_loop.cancel()

    # ---------------- Reminders ----------------

    @tasks.loop(seconds=60)
    async def reminder_loop(self) -> None:
        """Check active reminders once a minute and ping when due."""
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        for reminder in get_active_reminders():
            try:
                if reminder.is_recurring:
                    await self._handle_recurring(reminder, now_utc)
                else:
                    await self._handle_onetime(reminder, now_utc)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                print_error_log(f"reminder_loop: reminder {reminder.id}: {exc}")

    async def _handle_recurring(self, reminder, now_utc: datetime.datetime) -> None:
        """Ping a recurring reminder once per local day at its scheduled time."""
        timezone_name = get_config().reminders.timezone
        local_now = now_in_tz(timezone_name)
        today_str = local_now.strftime("%Y-%m-%d")
        if reminder.last_reminded_date == today_str:
            return  # already pinged today
        hour, minute = parse_time(reminder.remind_time)
        scheduled_today = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if local_now < scheduled_today:
            return  # not time yet today
        if await self._send_ping(reminder, recurring=True):
            mark_recurring_reminded(reminder.id, today_str)

    async def _handle_onetime(self, reminder, now_utc: datetime.datetime) -> None:
        """Ping a one-time reminder once, then deactivate it."""
        if reminder.remind_at is None:
            deactivate_reminder(reminder.id)
            return
        remind_at = reminder.remind_at
        if remind_at.tzinfo is None:
            remind_at = remind_at.replace(tzinfo=datetime.timezone.utc)
        if now_utc < remind_at:
            return
        await self._send_ping(reminder, recurring=False)
        deactivate_reminder(reminder.id)

    async def _send_ping(self, reminder, recurring: bool) -> bool:
        """Send the reminder ping to its channel. Returns True on success."""
        channel = self.bot.get_channel(reminder.channel_id)
        if not isinstance(channel, discord.TextChannel):
            print_error_log(f"_send_ping: channel {reminder.channel_id} missing for reminder {reminder.id}")
            return False
        prefix = "🔁 Daily reminder" if recurring else "📅 Reminder"
        # Asterisk italics (not `_`): a reminder whose text contains an underscore
        # (e.g. "file_name") would otherwise break underscore-italic pairing.
        suffix = "\n*React on the original reminder message with any emoji to stop.*" if recurring else ""
        try:
            posted = await channel.send(f"{prefix} for <@{reminder.ping_user_id}>: {reminder.content}{suffix}")
            # Archive the ping so the AI can answer "how many times was I reminded about X?".
            archive_bot_message(posted, reminder.guild_id)
            print_log(f"_send_ping: sent reminder {reminder.id} (recurring={recurring})")
            return True
        except discord.DiscordException as exc:
            print_error_log(f"_send_ping: failed to send reminder {reminder.id}: {exc}")
            return False

    @reminder_loop.before_loop
    async def before_reminder_loop(self) -> None:
        """Wait until the bot is connected before dispatching reminders."""
        await self.bot.wait_until_ready()

    # ---------------- Daily summary ----------------

    @tasks.loop(seconds=60)
    async def daily_summary_loop(self) -> None:
        """Post a digest of the day's calendar events and reminders once per day."""
        # Guard the whole body: a transient DB/Discord error should be logged and retried
        # next tick, never propagate out and permanently stop the loop.
        try:
            config = get_config()
            if not config.daily_summary.enabled:
                return
            timezone_name = config.reminders.timezone
            local_now = now_in_tz(timezone_name)
            if not is_summary_due(local_now, config.daily_summary.time, self._last_summary_date):
                return
            channel = self.bot.get_channel(config.channels.calendar)
            if not isinstance(channel, discord.TextChannel):
                print_error_log(f"daily_summary_loop: calendar channel {config.channels.calendar} not found")
                return
            start_utc, end_utc = day_bounds_utc(local_now, timezone_name)
            events = get_events_in_range(start_utc, end_utc)
            reminders = reminders_for_day(get_active_reminders_for_guild(config.guild_id), local_now, timezone_name)
            content = format_summary(local_now, events, reminders, timezone_name)
            # Split to stay under Discord's 2000-char limit; render mentions without pinging.
            chunks = chunk_message(content)
            posted_first = await channel.send(chunks[0], allowed_mentions=discord.AllowedMentions.none())
            for chunk in chunks[1:]:
                await channel.send(chunk, allowed_mentions=discord.AllowedMentions.none())
            # Archive the first chunk so the AI can answer "what was on the calendar that day?".
            archive_bot_message(posted_first, channel.guild.id)
            # Mark done only after every chunk sent, so a mid-send failure retries cleanly.
            self._last_summary_date = local_now.strftime("%Y-%m-%d")
            set_state(STATE_DAILY_SUMMARY_DATE, self._last_summary_date)
            print_log(f"daily_summary_loop: posted summary for {self._last_summary_date}")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print_error_log(f"daily_summary_loop: {exc}")

    @daily_summary_loop.before_loop
    async def before_daily_summary_loop(self) -> None:
        """Wait until connected, then restore the last-posted date so restarts don't re-post."""
        await self.bot.wait_until_ready()
        self._last_summary_date = get_state(STATE_DAILY_SUMMARY_DATE)

    # ---------------- Embeddings ----------------

    @tasks.loop(seconds=30)
    async def embedding_loop(self) -> None:
        """Compute embeddings for newly archived messages in small batches."""
        batch = get_messages_without_embedding(limit=64)
        if not batch:
            return
        contents = [content for _mid, content in batch]
        try:
            vectors = await asyncio.to_thread(embed_texts, contents)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print_error_log(f"embedding_loop: embedding failed: {exc}")
            return
        for (message_id, _content), vector in zip(batch, vectors):
            set_message_embedding(message_id, to_blob(vector))
        print_log(f"embedding_loop: embedded {len(batch)} message(s)")

    @embedding_loop.before_loop
    async def before_embedding_loop(self) -> None:
        """Wait until the bot is connected before embedding."""
        await self.bot.wait_until_ready()


async def setup(bot: MyBot) -> None:
    """discord.py extension entry point."""
    await bot.add_cog(TasksCog(bot))
