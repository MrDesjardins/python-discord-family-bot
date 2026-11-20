"""Unit tests for Discord-friendly formatting of AI answers (pure, no discord)."""

from deps.ai.discord_format import format_for_discord, split_message, tables_to_lists

TABLE_ANSWER = """Here are the top areas:

| City | Site | Price |
|------|:----:|------:|
| Hooksett, NH | Zillow | $450k |
| Dover, NH | Redfin | $520k |

Let me know if you want more."""


def test_table_becomes_bullet_list() -> None:
    """Each table row becomes a bullet with the first cell bolded."""
    result = tables_to_lists(TABLE_ANSWER)
    assert "|" not in result
    assert "- **Hooksett, NH** — Site: Zillow · Price: $450k" in result
    assert "- **Dover, NH** — Site: Redfin · Price: $520k" in result
    assert result.startswith("Here are the top areas:")
    assert result.endswith("Let me know if you want more.")


def test_table_without_outer_pipes_and_missing_cells() -> None:
    """Pipe-less edges and short rows still convert; empty cells are dropped."""
    text = "Name | Note\n--- | ---\nAlpha | first\nBeta |"
    assert tables_to_lists(text) == "- **Alpha** — Note: first\n- **Beta**"


def test_non_tables_are_untouched() -> None:
    """Pipes without a separator row, horizontal rules and code fences are left alone."""
    text = "a | b | c\n---\n```\n| x | y |\n|---|---|\n| 1 | 2 |\n```"
    assert tables_to_lists(text) == text


def test_split_message_short_text_is_single_chunk() -> None:
    """Short answers are sent as one message."""
    assert split_message("hello") == ["hello"]
    assert not split_message("   ")


def test_split_message_respects_limit_on_line_boundaries() -> None:
    """Long answers split between lines and every chunk fits the limit."""
    lines = [f"{i}. item number {i}" for i in range(1, 200)]
    chunks = split_message("\n".join(lines), limit=200)
    assert len(chunks) > 1
    assert all(len(chunk) <= 200 for chunk in chunks)
    assert "\n".join(chunks).split("\n") == lines


def test_split_message_wraps_overlong_single_line() -> None:
    """A single line longer than the limit is hard-wrapped."""
    chunks = split_message("word " * 200, limit=100)
    assert all(len(chunk) <= 100 for chunk in chunks)
    assert " ".join(chunks).split() == ["word"] * 200


def test_split_message_reopens_code_fence() -> None:
    """A fence open at a boundary is closed and reopened so both chunks render."""
    body = "\n".join(f"line {i}" for i in range(60))
    chunks = split_message(f"```python\n{body}\n```", limit=150)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 150
        assert chunk.count("```") == 2


def test_format_for_discord_combines_both() -> None:
    """Tables are converted before splitting."""
    chunks = format_for_discord(TABLE_ANSWER)
    assert len(chunks) == 1
    assert "|" not in chunks[0]
