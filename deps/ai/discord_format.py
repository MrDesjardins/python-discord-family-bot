"""Make LLM Markdown render well in Discord.

Discord renders bold/italics, lists, headings, links and code blocks, but **not**
Markdown tables — a ``| a | b |`` table shows up as raw pipes. The system prompt
asks the model to avoid tables; this module is the safety net that rewrites any
table that slips through into a bullet list, and splits long answers into chunks
that fit Discord's 2000-character message limit. Pure functions, no discord import.
"""

from __future__ import annotations

import re
from typing import List

DISCORD_MESSAGE_LIMIT = 2000

_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")
_FENCE = "```"


def _split_row(line: str) -> List[str]:
    """Split a ``| a | b |`` table row into stripped cells."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [cell.strip() for cell in body.split("|")]


def _is_separator(line: str) -> bool:
    """True for a header separator row such as ``|---|:---:|``."""
    if "|" not in line:
        return False
    cells = _split_row(line)
    return bool(cells) and all(_SEPARATOR_CELL.match(cell) for cell in cells)


def _is_row(line: str) -> bool:
    return "|" in line


def _table_to_bullets(header: List[str], rows: List[List[str]]) -> List[str]:
    """Render table rows as ``- **first** — Header: value · Header: value``."""
    bullets: List[str] = []
    for row in rows:
        cells = row + [""] * (len(header) - len(row))
        first = cells[0]
        pairs = zip(header[1:], cells[1:])
        details = [f"{name}: {value}" if name else value for name, value in pairs if value]
        lead = f"**{first}**" if first else ""
        text = " — ".join(part for part in (lead, " · ".join(details)) if part)
        if text:
            bullets.append(f"- {text}")
    return bullets


def tables_to_lists(text: str) -> str:
    """Rewrite Markdown tables (outside code fences) as bullet lists."""
    lines = text.split("\n")
    out: List[str] = []
    in_fence = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith(_FENCE):
            in_fence = not in_fence
            out.append(line)
            i += 1
            continue
        has_next = i + 1 < len(lines)
        is_table_start = not in_fence and has_next and _is_row(line) and _is_separator(lines[i + 1])
        if not is_table_start:
            out.append(line)
            i += 1
            continue
        header = _split_row(line)
        i += 2
        rows: List[List[str]] = []
        while i < len(lines) and lines[i].strip() and _is_row(lines[i]):
            rows.append(_split_row(lines[i]))
            i += 1
        out.extend(_table_to_bullets(header, rows))
    return "\n".join(out)


def _hard_wrap(line: str, limit: int) -> List[str]:
    """Break a single over-long line, preferring spaces."""
    pieces: List[str] = []
    while len(line) > limit:
        cut = line.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        pieces.append(line[:cut])
        line = line[cut:].lstrip(" ")
    pieces.append(line)
    return pieces


def split_message(text: str, limit: int = DISCORD_MESSAGE_LIMIT) -> List[str]:
    """Split ``text`` into chunks of at most ``limit`` chars on line boundaries.

    A code fence left open at a chunk boundary is closed and reopened in the next
    chunk so each message renders on its own.
    """
    text = text.strip()
    if not text:
        return []
    # Reserve room for a closing fence appended at a boundary.
    budget = limit - len(_FENCE) - 1
    chunks: List[str] = []
    current: List[str] = []
    size = 0
    open_fence: str | None = None

    def flush() -> None:
        nonlocal current, size
        body = "\n".join(current).strip("\n")
        if open_fence is not None:
            body += "\n" + _FENCE
        if body.strip():
            chunks.append(body)
        current = [open_fence] if open_fence is not None else []
        size = len(open_fence) if open_fence is not None else 0

    for raw_line in text.split("\n"):
        for line in _hard_wrap(raw_line, budget - len(_FENCE) - 16):
            added = len(line) + (1 if current else 0)
            if current and size + added > budget:
                flush()
                added = len(line) + (1 if current else 0)
            current.append(line)
            size += added
            if line.strip().startswith(_FENCE):
                open_fence = None if open_fence is not None else line.strip()
    if open_fence is not None:
        open_fence = None  # the model left it open; don't add a stray fence
    body = "\n".join(current).strip("\n")
    if body.strip():
        chunks.append(body)
    return chunks


def format_for_discord(text: str, limit: int = DISCORD_MESSAGE_LIMIT) -> List[str]:
    """Convert tables to lists and split into Discord-sized messages."""
    return split_message(tables_to_lists(text), limit)
