"""OpenAI-backed Q&A grounded on archived family messages."""

from __future__ import annotations

import asyncio
import datetime
import os
from typing import List, Tuple

from openai import OpenAI

from deps.ai.embeddings import embed_text, rank_messages
from deps.config import get_config
from deps.log import print_error_log, print_log
from deps.message_data_access import get_embedded_messages_for_guild

_client: OpenAI | None = None

SYSTEM_PROMPT = (
    "You are a friendly assistant for a family's private Discord server. "
    "Answer the question using the provided family chat history as context when relevant. "
    "The context lines are formatted as '[date] author: message'. "
    "If the context does not contain the answer, say so and answer from general knowledge. "
    "Be concise and warm."
)


def _get_client() -> OpenAI:
    """Return a cached OpenAI client (reads OPENAI_API_KEY from env)."""
    global _client  # pylint: disable=global-statement
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        _client = OpenAI(api_key=api_key)
    return _client


def _build_context(guild_id: int, question: str) -> Tuple[str, int]:
    """Retrieve the top relevant messages and format them as a context block."""
    rows = get_embedded_messages_for_guild(guild_id)
    if not rows:
        return "", 0
    ai_cfg = get_config().ai
    query_vector = embed_text(question)
    ranked = rank_messages(
        query_vector,
        rows,
        ai_cfg.max_context_messages,
        similarity_weight=ai_cfg.similarity_weight,
        halflife_days=ai_cfg.recency_halflife_days,
    )
    # Present chronologically so the model reads the conversation in order.
    ranked.sort(key=lambda item: item[3])
    lines: List[str] = []
    for _message_id, author_name, content, created_at, _score in ranked:
        date_str = created_at.strftime("%Y-%m-%d")
        lines.append(f"[{date_str}] {author_name}: {content}")
    return "\n".join(lines), len(ranked)


def _answer_sync(guild_id: int, question: str) -> str:
    """Blocking call: build context and ask OpenAI. Run via asyncio.to_thread."""
    context, used = _build_context(guild_id, question)
    print_log(f"ai: answering with {used} context messages for guild {guild_id}")

    user_content = question
    if context:
        user_content = f"Family chat history (most relevant excerpts):\n{context}\n\nQuestion: {question}"

    client = _get_client()
    response = client.chat.completions.create(
        model=get_config().ai.model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.5,
        max_tokens=600,
    )
    answer = response.choices[0].message.content or ""
    return answer.strip()


async def answer_question(guild_id: int, question: str) -> str:
    """Answer ``question`` using family chat context. Safe to await from a cog."""
    try:
        return await asyncio.to_thread(_answer_sync, guild_id, question)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print_error_log(f"answer_question: {exc}")
        return "Sorry, I couldn't come up with an answer right now. Please try again later."


def now_utc() -> datetime.datetime:
    """Helper for callers needing a tz-aware now."""
    return datetime.datetime.now(datetime.timezone.utc)
