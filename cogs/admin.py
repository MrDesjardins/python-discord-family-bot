"""Admin utility commands."""

import discord
from discord import app_commands
from discord.ext import commands

from deps.config import reload_config
from deps.log import print_error_log, print_log
from deps.mybot import MyBot
from deps.values import COMMAND_RELOAD_CONFIG


class AdminCog(commands.Cog):
    """Administrative commands."""

    def __init__(self, bot: MyBot) -> None:
        self.bot = bot

    @app_commands.command(name=COMMAND_RELOAD_CONFIG, description="Reload config.yaml without restarting the bot.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reload_config_cmd(self, interaction: discord.Interaction) -> None:
        """Re-read config.yaml from disk."""
        await interaction.response.defer(ephemeral=True)
        try:
            cfg = reload_config()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print_error_log(f"reloadconfig: {exc}")
            await interaction.followup.send(f"Failed to reload config: {exc}", ephemeral=True)
            return
        print_log("admin: config.yaml reloaded")
        await interaction.followup.send(
            f"Config reloaded. Reminder channel <#{cfg.channels.reminder}>, "
            f"calendar channel <#{cfg.channels.calendar}>, timezone `{cfg.reminders.timezone}`.",
            ephemeral=True,
        )

    @reload_config_cmd.error
    async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        """Friendly message for non-admins."""
        if isinstance(error, app_commands.MissingPermissions):
            msg = "You need administrator permission for that."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        else:
            print_error_log(f"AdminCog error: {error}")


async def setup(bot: MyBot) -> None:
    """discord.py extension entry point."""
    await bot.add_cog(AdminCog(bot))
