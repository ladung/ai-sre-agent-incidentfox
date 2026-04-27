from __future__ import annotations

from markdown_utils import to_discord_md, escape_discord_md, split_for_embed_chunks


def test_passthrough_basic_formatting():
    assert to_discord_md("**bold**") == "**bold**"
    assert to_discord_md("*italic*") == "*italic*"
    assert to_discord_md("`code`") == "`code`"


def test_strip_slack_user_mentions():
    assert to_discord_md("hello <@U123>") == "hello"


def test_escape_discord_special_chars():
    assert escape_discord_md("a*b") == r"a\*b"
    assert escape_discord_md("a_b") == r"a\_b"
    assert escape_discord_md("a`b") == r"a\`b"
    assert escape_discord_md("a~b") == r"a\~b"
    assert escape_discord_md("a|b") == r"a\|b"


def test_escape_handles_backslash_first():
    assert escape_discord_md(r"\*") == r"\\\*"


def test_split_for_embed_chunks_under_limit_is_passthrough():
    text = "a" * 100
    chunks = split_for_embed_chunks(text, max_chars=200)
    assert chunks == [text]


def test_split_for_embed_chunks_at_paragraph_boundary():
    text = "para one\n\npara two\n\npara three"
    chunks = split_for_embed_chunks(text, max_chars=15)
    assert all(len(c) <= 15 + 2 for c in chunks)
    assert "para one" in chunks[0]
    assert chunks[-1].endswith("para three")


def test_split_for_embed_chunks_hard_split_long_paragraph():
    text = "x" * 50
    chunks = split_for_embed_chunks(text, max_chars=20)
    assert len(chunks) == 3
    assert all(len(c) <= 20 for c in chunks)


def test_split_default_max_is_4000_for_discord_safety_margin():
    text = "a" * 5000
    chunks = split_for_embed_chunks(text)
    assert all(len(c) <= 4000 for c in chunks)
    assert len(chunks) >= 2
