"""Background loops: reminder dispatch and embedding backfill."""

import asyncio
import datetime

import discord
from discord.ext import commands, tasks

from deps.ai.embeddings import embed_texts, to_blob
from deps.config import get_config
from deps.functions_date import now_in_tz, parse_time
from deps.log import print_error_log, print_log
from deps.message_data_access import get_messages_without_embedding, set_message_embedding
from deps.mybot import MyBot
from deps.reminder_data_access import (
    deactivate_reminder,
    get_active_reminders,
    mark_recurring_reminded,
)


class TasksCog(commands.Cog):
    """Owns the periodic task loops."""

    def __init__(self, bot: MyBot) -> None:
        self.bot = bot
        self.reminder_loop.start()
        self.embedding_loop.start()

    async def cog_unload(self) -> None:
        """Stop loops when the cog unloads."""
        self.reminder_loop.cancel()
        self.embedding_loop.cancel()

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
        suffix = "\n_React on the original reminder message with any emoji to stop._" if recurring else ""
        try:
            await channel.send(f"{prefix} for <@{reminder.author_id}>: {reminder.content}{suffix}")
            print_log(f"_send_ping: sent reminder {reminder.id} (recurring={recurring})")
            return True
        except discord.DiscordException as exc:
            print_error_log(f"_send_ping: failed to send reminder {reminder.id}: {exc}")
            return False

    @reminder_loop.before_loop
    async def before_reminder_loop(self) -> None:
        """Wait until the bot is connected before dispatching reminders."""
        await self.bot.wait_until_ready()

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
