"""The /setreminder command and reminder management."""

import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from deps.config import get_config
from deps.functions_date import get_tz, now_in_tz
from deps.functions_when import parse_when, suggest_when
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

    async def when_autocomplete(  # pylint: disable=unused-argument
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Offer tap-friendly time suggestions as the user fills in ``when`` (interaction unused)."""
        config = get_config()
        try:
            pairs = suggest_when(
                current, now_in_tz(config.reminders.timezone), config.reminders.timezone, config.reminders.default_time
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print_error_log(f"reminders.when_autocomplete: {exc}")
            return []
        return [app_commands.Choice(name=label[:100], value=value[:100]) for label, value in pairs]

    @app_commands.command(
        name=COMMAND_SET_REMINDER,
        description="Create a reminder. Leave 'when' empty to repeat daily until you react with any emoji.",
    )
    @app_commands.describe(
        message="What to be reminded about.",
        when="Tap a suggestion, or type e.g. 'tomorrow', 'in 3 days', 'fri 6pm', '2026-07-15 18:00'. Empty = daily.",
        person="Who to ping. Leave empty to be pinged yourself.",
    )
    @app_commands.autocomplete(when=when_autocomplete)
    async def set_reminder(  # pylint: disable=too-many-locals
        self,
        interaction: discord.Interaction,
        message: str,
        when: Optional[str] = None,
        person: Optional[discord.Member] = None,
    ) -> None:
        """Create a recurring (default) or one-time reminder from a natural 'when'."""
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

        try:
            parsed = parse_when(when, now_in_tz(timezone_name), timezone_name, config.reminders.default_time)
        except (ValueError, IndexError):
            await interaction.followup.send(
                "I couldn't understand that time. Try `tomorrow`, `in 3 days`, `fri 6pm`, "
                "or a date like `2026-07-15 18:00`.",
                ephemeral=True,
            )
            return

        author = interaction.user
        target = person if person is not None else author
        target_id = person.id if person is not None else None
        for_target = f" for {target.display_name}" if person is not None else ""

        if parsed.recurring:
            remind_time = parsed.remind_time or config.reminders.default_time
            reminder_id = create_recurring_reminder(guild.id, channel.id, author.id, message, remind_time, target_id)
            posted = await channel.send(
                f"🔁 **Daily reminder** for {target.mention}: {message}\n"
                # Asterisk italics (not `_`): the timezone name contains an underscore
                # (e.g. America/Los_Angeles) which breaks underscore-italic pairing.
                f"*I'll ping {'you' if person is None else target.display_name} every day "
                f"at {remind_time} ({timezone_name}). "
                f"React to this message with any emoji to stop.*"
            )
            set_reminder_message_id(reminder_id, posted.id)
            await interaction.followup.send(
                f"Daily reminder created{for_target} in {channel.mention} (id `{reminder_id}`).", ephemeral=True
            )
            print_log(f"reminders: created recurring reminder {reminder_id} for guild {guild.id}")
        else:
            remind_at_utc = parsed.remind_at_utc
            assert remind_at_utc is not None  # non-recurring always carries an instant
            local_when = remind_at_utc.astimezone(get_tz(timezone_name)).strftime("%a %b %d at %H:%M")
            if remind_at_utc <= datetime.datetime.now(datetime.timezone.utc):
                await interaction.followup.send(
                    f"That time (**{local_when}**, {timezone_name}) is already in the past. "
                    "Try `tomorrow`, a later time today, or a date like `2026-07-15 18:00`.",
                    ephemeral=True,
                )
                return
            reminder_id = create_onetime_reminder(guild.id, channel.id, author.id, message, remind_at_utc, target_id)
            posted = await channel.send(
                f"📅 **Reminder set** for {target.mention} on **{local_when}** ({timezone_name}): {message}"
            )
            set_reminder_message_id(reminder_id, posted.id)
            await interaction.followup.send(
                f"One-time reminder created{for_target} in {channel.mention} for {local_when} (id `{reminder_id}`).",
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
            lines.append(f"`{rem.id}` • <@{rem.ping_user_id}> • {when} • {preview}")
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
