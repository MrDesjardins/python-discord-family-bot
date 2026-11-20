"""Integration test: AI answer pipeline (real DB retrieval, mocked OpenAI) + Discord formatting."""

import asyncio
import datetime
import types

from deps.ai import ai_functions
from deps.ai.discord_format import DISCORD_MESSAGE_LIMIT, format_for_discord
from deps.message_data_access import store_message

NOW = datetime.datetime(2026, 6, 1, 12, 0, tzinfo=datetime.timezone.utc)


class _FakeCompletions:  # pylint: disable=too-few-public-methods
    """Stands in for ``client.chat.completions``; records the request."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.kwargs: dict = {}

    def create(self, **kwargs):
        """Return a canned completion shaped like the OpenAI SDK response."""
        self.kwargs = kwargs
        message = types.SimpleNamespace(content=self.reply)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


def test_table_answer_is_posted_as_discord_friendly_chunks(db, monkeypatch):  # pylint: disable=unused-argument
    """A table-shaped model reply becomes table-free chunks within Discord's limit."""
    store_message(1, 1, 10, "retirement-house", 100, "dad", "zillow hooksett nh listing", NOW)
    rows = "\n".join(f"| Town {i}, NH | Zillow | ${400 + i}k |" for i in range(80))
    reply = f"Top areas:\n\n| City | Site | Price |\n|---|---|---|\n{rows}"
    completions = _FakeCompletions(reply)
    fake_client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=completions))
    monkeypatch.setattr(ai_functions, "_get_client", lambda: fake_client)
    monkeypatch.setattr(ai_functions, "embed_text", lambda text: None)

    answer = asyncio.run(ai_functions.answer_question(1, "zillow areas", {10}, 10))
    chunks = format_for_discord(answer)

    system_prompt = completions.kwargs["messages"][0]["content"]
    assert "never use tables" in system_prompt
    assert len(chunks) > 1
    assert all(len(chunk) <= DISCORD_MESSAGE_LIMIT for chunk in chunks)
    assert not any("|" in chunk for chunk in chunks)
    assert "- **Town 79, NH** — Site: Zillow · Price: $479k" in chunks[-1]
