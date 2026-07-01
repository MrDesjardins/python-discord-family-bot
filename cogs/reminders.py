"""The /setreminder command and reminder management."""

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from deps.config import get_config
from deps.functions_date import local_datetime_to_utc, parse_time
from deps.log import print_error_log, print_log
from deps.mybot import MyBot
from deps.reminder_data_access import (
    acknowledge_reminder,
    create_onetime_reminder,
    create_recurring_reminder,
    deactivate_reminder,
    get_active_reminders_for_guild,
    get_reminder_by_message_id,
    set_reminder_message_id,
)
from deps.values import (
    COMMAND_CANCEL_REMINDER,
    COMMAND_LIST_REMINDERS,
    COMMAND_SET_REMINDER,
)


class RemindersCog(commands.Cog):
    """Create and manage reminders."""

    def __init__(self, bot: MyBot) -> None:
        self.bot = bot

    @app_commands.command(
        name=COMMAND_SET_REMINDER,
        description="Create a reminder. Without a date it repeats daily until you react with any emoji.",
    )
    @app_commands.describe(
        message="What to be reminded about.",
        date="Optional one-time date (YYYY-MM-DD). With a date it pings only that day.",
        time="Optional time (HH:MM, 24h). Defaults to 08:30.",
    )
    async def set_reminder(
        self,
        interaction: discord.Interaction,
        message: str,
        date: Optional[str] = None,
        time: Optional[str] = None,
    ) -> None:
        """Create a recurring (default) or one-time (with date) reminder."""
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("This command must be used in a server.", ephemeral=True)
            return

        config = get_config()
        channel = guild.get_channel(config.channels.reminder)
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send(
                "The reminder channel in config.yaml is missing or wrong. Ask an admin to fix `channels.reminder`.",
                ephemeral=True,
            )
            return

        timezone_name = config.reminders.timezone
        default_time = config.reminders.default_time

        # Validate time early so we can give a clean error.
        try:
            parse_time(time)
        except (ValueError, IndexError):
            await interaction.followup.send("Invalid time. Use HH:MM, e.g. `08:30`.", ephemeral=True)
            return

        author = interaction.user

        if date is None:
            # Recurring daily reminder until acknowledged with an emoji.
            remind_time = time or default_time
            reminder_id = create_recurring_reminder(guild.id, channel.id, author.id, message, remind_time)
            posted = await channel.send(
                f"🔁 **Daily reminder** for {author.mention}: {message}\n"
                f"_I'll ping you every day at {remind_time} ({timezone_name}). "
                f"React to this message with any emoji to stop._"
            )
            set_reminder_message_id(reminder_id, posted.id)
            await interaction.followup.send(
                f"Daily reminder created in {channel.mention} (id `{reminder_id}`).", ephemeral=True
            )
            print_log(f"reminders: created recurring reminder {reminder_id} for guild {guild.id}")
        else:
            # One-time reminder at a specific date/time.
            remind_time = time or default_time
            try:
                remind_at_utc = local_datetime_to_utc(date, remind_time, timezone_name)
            except (ValueError, IndexError):
                await interaction.followup.send("Invalid date. Use YYYY-MM-DD, e.g. `2026-07-15`.", ephemeral=True)
                return
            reminder_id = create_onetime_reminder(guild.id, channel.id, author.id, message, remind_at_utc)
            posted = await channel.send(
                f"📅 **Reminder set** for {author.mention} on **{date} at {remind_time}** "
                f"({timezone_name}): {message}"
            )
            set_reminder_message_id(reminder_id, posted.id)
            await interaction.followup.send(
                f"One-time reminder created in {channel.mention} for {date} at {remind_time} (id `{reminder_id}`).",
                ephemeral=True,
            )
            print_log(f"reminders: created one-time reminder {reminder_id} for guild {guild.id}")

    @app_commands.command(name=COMMAND_LIST_REMINDERS, description="List active reminders in this server.")
    async def list_reminders(self, interaction: discord.Interaction) -> None:
        """List all active reminders for the guild."""
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("This command must be used in a server.", ephemeral=True)
            return
        reminders = get_active_reminders_for_guild(guild.id)
        if not reminders:
            await interaction.followup.send("No active reminders.", ephemeral=True)
            return
        lines = []
        for rem in reminders:
            if rem.is_recurring:
                when = f"daily at {rem.remind_time}"
            else:
                when = f"once at {rem.remind_at:%Y-%m-%d %H:%M} UTC" if rem.remind_at else "once"
            preview = rem.content if len(rem.content) <= 60 else rem.content[:57] + "..."
            lines.append(f"`{rem.id}` • <@{rem.author_id}> • {when} • {preview}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @app_commands.command(name=COMMAND_CANCEL_REMINDER, description="Cancel a reminder by its id.")
    @app_commands.describe(reminder_id="The id shown by /listreminders.")
    async def cancel_reminder(self, interaction: discord.Interaction, reminder_id: int) -> None:
        """Cancel (deactivate) a reminder by id."""
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("This command must be used in a server.", ephemeral=True)
            return
        active = {rem.id for rem in get_active_reminders_for_guild(guild.id)}
        if reminder_id not in active:
            await interaction.followup.send(f"No active reminder with id `{reminder_id}`.", ephemeral=True)
            return
        deactivate_reminder(reminder_id)
        await interaction.followup.send(f"Reminder `{reminder_id}` cancelled.", ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Reacting with any emoji on a recurring reminder acknowledges and stops it."""
        if self.bot.user is not None and payload.user_id == self.bot.user.id:
            return
        reminder = get_reminder_by_message_id(payload.message_id)
        if reminder is None or not reminder.is_recurring or not reminder.is_active:
            return
        acknowledge_reminder(reminder.id)
        print_log(f"reminders: reminder {reminder.id} acknowledged via emoji by user {payload.user_id}")
        try:
            channel = self.bot.get_channel(payload.channel_id)
            if isinstance(channel, discord.TextChannel):
                await channel.send(
                    f"✅ Reminder acknowledged — I'll stop the daily ping for: {reminder.content}",
                    delete_after=30,
                )
        except discord.DiscordException as exc:
            print_error_log(f"reminders.on_raw_reaction_add: {exc}")


async def setup(bot: MyBot) -> None:
    """discord.py extension entry point."""
    await bot.add_cog(RemindersCog(bot))
