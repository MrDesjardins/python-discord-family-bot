"""OpenAI-backed Q&A grounded on archived family messages."""

from __future__ import annotations

import asyncio
import datetime
import os
import re
from typing import List, Set, Tuple

from openai import OpenAI

from deps.ai.embeddings import embed_text, rank_messages
from deps.config import get_config
from deps.log import print_error_log, print_log
from deps.message_data_access import (
    get_embedded_messages_for_guild,
    get_relevant_messages_for_guild,
)

_client: OpenAI | None = None

SYSTEM_PROMPT = (
    "You are a friendly assistant for a family's private Discord server. "
    "Answer the question using the provided family chat history as context when relevant. "
    "The context lines are formatted as '[date #channel] author: message'. "
    "If the context does not contain a requested family-history fact, clearly say it "
    "was not found; "
    "answer unrelated general-knowledge questions normally. "
    "When asked what was discussed in a channel, use those retrieved messages and do not "
    "invent or infer a list that the messages do not support. "
    "Be concise and warm."
)

_SEARCH_STOP_WORDS = {
    "about",
    "are",
    "can",
    "could",
    "did",
    "discussed",
    "do",
    "does",
    "find",
    "for",
    "from",
    "get",
    "give",
    "have",
    "help",
    "hey",
    "history",
    "how",
    "i",
    "in",
    "it",
    "me",
    "of",
    "on",
    "or",
    "please",
    "show",
    "that",
    "the",
    "their",
    "them",
    "there",
    "these",
    "they",
    "this",
    "those",
    "to",
    "top",
    "us",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "with",
    "would",
    "you",
    "your",
}


def _search_terms(question: str) -> List[str]:
    """Extract useful exact-search terms from a natural-language question."""
    words = re.findall(r"[a-z0-9]+(?:[-'][a-z0-9]+)*", question.lower())
    terms = [word for word in words if len(word) > 2 and word not in _SEARCH_STOP_WORDS]
    # Preserve order while preventing a repeated word from dominating SQL ranking.
    return list(dict.fromkeys(terms))[:12]


def _get_client() -> OpenAI:
    """Return a cached OpenAI client (reads OPENAI_API_KEY from env)."""
    global _client  # pylint: disable=global-statement
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        _client = OpenAI(api_key=api_key)
    return _client


ContextRow = Tuple[int, str, str, datetime.datetime, str]


def _select_context_rows(  # pylint: disable=too-many-locals
    guild_id: int,
    question: str,
    visible_channel_ids: Set[int],
    preferred_channel_id: int | None = None,
    exclude_message_id: int | None = None,
) -> List[ContextRow]:
    """Retrieve exact, semantic, and recent messages from visible channels."""
    if not visible_channel_ids:
        return []

    ai_cfg = get_config().ai
    context_limit = max(1, ai_cfg.max_context_messages)
    exact_limit = max(1, context_limit // 2)
    recent_limit = 0
    if preferred_channel_id is not None:
        recent_limit = min(context_limit - exact_limit, max(1, context_limit // 3))
    lexical_rows = get_relevant_messages_for_guild(
        guild_id,
        visible_channel_ids,
        _search_terms(question),
        target_channel_id=preferred_channel_id,
        limit=exact_limit,
        exclude_message_id=exclude_message_id,
    )
    selected: dict[int, ContextRow] = {
        row[0]: (row[0], row[1], row[2], row[3], row[5] or "unknown") for row in lexical_rows
    }
    # Reserve part of the prompt for the immediate channel history, which can
    # contain the referent of a follow-up that omits the original subject words.
    recent_rows = []
    if recent_limit:
        recent_rows = get_relevant_messages_for_guild(
            guild_id,
            visible_channel_ids,
            [],
            target_channel_id=preferred_channel_id,
            limit=recent_limit,
            exclude_message_id=exclude_message_id,
        )
        for row in recent_rows:
            selected.setdefault(row[0], (row[0], row[1], row[2], row[3], row[5] or "unknown"))

    rows = get_embedded_messages_for_guild(
        guild_id,
        visible_channel_ids,
        preferred_channel_id,
        exclude_message_id,
    )
    semantic_limit = max(0, context_limit - exact_limit - recent_limit)
    if rows and semantic_limit:
        query_vector = embed_text(question)
        ranked = rank_messages(
            query_vector,
            rows,
            semantic_limit,
            similarity_weight=ai_cfg.similarity_weight,
            halflife_days=ai_cfg.recency_halflife_days,
        )
        for message_id, author_name, content, created_at, _score in ranked:
            if message_id in selected:
                continue
            selected[message_id] = (message_id, author_name, content, created_at, "unknown")
            if len(selected) >= context_limit:
                break

    return sorted(selected.values(), key=lambda item: item[3])


def _build_context(
    guild_id: int,
    question: str,
    visible_channel_ids: Set[int],
    preferred_channel_id: int | None = None,
    exclude_message_id: int | None = None,
) -> Tuple[str, int]:
    """Retrieve relevant messages and format them as a context block.

    Only messages from ``visible_channel_ids`` (the asking member's readable
    channels) are considered, so answers never leak restricted-channel content.
    """
    messages = _select_context_rows(
        guild_id,
        question,
        visible_channel_ids,
        preferred_channel_id,
        exclude_message_id,
    )
    lines: List[str] = []
    for _message_id, author_name, content, created_at, channel_name in messages:
        date_str = created_at.strftime("%Y-%m-%d")
        lines.append(f"[{date_str} #{channel_name}] {author_name}: {content}")
    return "\n".join(lines), len(messages)


def _answer_sync(
    guild_id: int,
    question: str,
    visible_channel_ids: Set[int],
    preferred_channel_id: int | None = None,
    exclude_message_id: int | None = None,
) -> str:
    """Blocking call: build context and ask OpenAI. Run via asyncio.to_thread."""
    context, used = _build_context(
        guild_id,
        question,
        visible_channel_ids,
        preferred_channel_id,
        exclude_message_id,
    )
    print_log(
        f"ai: answering with {used} context messages for guild {guild_id} "
        f"({len(visible_channel_ids)} visible channels)"
    )

    user_content = question
    if context:
        context_header = f"Family chat history (most relevant excerpts):\n{context}\n\n"
        user_content = context_header + f"Question: {question}"

    client = _get_client()
    response = client.chat.completions.create(
        model=get_config().ai.model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        reasoning_effort="low",
        max_completion_tokens=2000,
    )
    answer = response.choices[0].message.content or ""
    return answer.strip()


async def answer_question(
    guild_id: int,
    question: str,
    visible_channel_ids: Set[int],
    preferred_channel_id: int | None = None,
    exclude_message_id: int | None = None,
) -> str:
    """Answer ``question`` using family chat context. Safe to await from a cog.

    ``visible_channel_ids`` restricts retrieval to channels the asker can read
    (compute with ``deps.channel_visibility.visible_channel_ids``).
    """
    try:
        return await asyncio.to_thread(
            _answer_sync,
            guild_id,
            question,
            visible_channel_ids,
            preferred_channel_id,
            exclude_message_id,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print_error_log(f"answer_question: {exc}")
        return "Sorry, I couldn't come up with an answer right now. Please try again later."


def now_utc() -> datetime.datetime:
    """Helper for callers needing a tz-aware now."""
    return datetime.datetime.now(datetime.timezone.utc)
