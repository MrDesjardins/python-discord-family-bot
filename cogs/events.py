"""Core event handlers: command sync, message archiving, AI mentions."""

import discord
from discord.ext import commands

from deps.ai.ai_functions import answer_question
from deps.channel_visibility import archival_parent_channel_id, visible_channel_ids
from deps.config import get_config
from deps.log import print_error_log, print_log, print_warning_log
from deps.message_data_access import store_message
from deps.mybot import MyBot


class EventsCog(commands.Cog):
    """on_ready, on_message and related gateway events."""

    def __init__(self, bot: MyBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Sync slash commands once the gateway is ready."""
        try:
            synced = await self.bot.tree.sync()
            print_log(f"events: logged in as {self.bot.user}; synced {len(synced)} command(s)")
        except discord.DiscordException as exc:
            print_error_log(f"events.on_ready: command sync failed: {exc}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Archive messages for AI context and answer when the bot is mentioned."""
        if message.author.bot:
            return
        if message.guild is None:
            return  # only archive/handle guild text channels

        # Archive every human message in a text channel for AI grounding.
        try:
            store_message(
                message_id=message.id,
                guild_id=message.guild.id,
                channel_id=message.channel.id,
                channel_name=getattr(message.channel, "name", None),
                author_id=message.author.id,
                author_name=message.author.display_name,
                content=message.content or "",
                created_at=message.created_at,
                parent_channel_id=archival_parent_channel_id(message.channel),
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print_error_log(f"events.on_message: failed to archive message: {exc}")

        # AI: respond when the bot is @-mentioned.
        if self.bot.user is not None and self.bot.user in message.mentions:
            await self._handle_ai_mention(message)

    async def _handle_ai_mention(self, message: discord.Message) -> None:
        """Answer a question directed at the bot via mention."""
        assert message.guild is not None
        ai_channel_id = get_config().channels.ai
        if ai_channel_id is not None and message.channel.id != ai_channel_id:
            return  # AI restricted to another channel

        # Strip the bot mention out of the question text.
        question = message.content
        for mention in (f"<@{self.bot.user.id}>", f"<@!{self.bot.user.id}>"):  # type: ignore[union-attr]
            question = question.replace(mention, "")
        question = question.strip()

        if not question:
            await message.reply("Hi! Ask me a question and I'll use our family chat history to help. 🙂")
            return

        # Resolve the asker to a Member — on a member-cache miss the author is a bare
        # User without roles, which would silently produce an empty visible set.
        member: discord.Member | None
        if isinstance(message.author, discord.Member):
            member = message.author
        else:
            member = message.guild.get_member(message.author.id)
            if member is None:
                try:
                    member = await message.guild.fetch_member(message.author.id)
                except discord.DiscordException as exc:
                    print_warning_log(
                        f"events._handle_ai_mention: cannot resolve member {message.author.id}; "
                        f"answering without archive context: {exc}"
                    )

        # Only ground the answer on channels the asker can read (role-aware).
        visible = visible_channel_ids(message.guild, member) if member is not None else set()
        async with message.channel.typing():
            answer = await answer_question(message.guild.id, question, visible)

        # Discord messages cap at 2000 chars.
        await message.reply(answer[:1990] if len(answer) > 1990 else answer)


async def setup(bot: MyBot) -> None:
    """discord.py extension entry point."""
    await bot.add_cog(EventsCog(bot))
