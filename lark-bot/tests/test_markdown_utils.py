from __future__ import annotations

from markdown_utils import to_lark_md, escape_lark_md, split_for_card_chunks


def test_passthrough_basic_formatting():
    assert to_lark_md("**bold**") == "**bold**"
    assert to_lark_md("*italic*") == "*italic*"
    assert to_lark_md("`code`") == "`code`"


def test_heading_becomes_bold_line():
    assert to_lark_md("# Title").splitlines()[0] == "**Title**"
    assert to_lark_md("## Sub").splitlines()[0] == "**Sub**"


def test_links_passthrough():
    assert to_lark_md("[docs](https://example.com)") == "[docs](https://example.com)"


def test_user_mention_replacement():
    # Slack-style <@U123> should be stripped (not a Lark concept)
    assert to_lark_md("hello <@U123>") == "hello"


def test_escape_pipe_and_brackets_in_user_text():
    # User-supplied text fed into a card cell — pipes break tables, brackets break links.
    assert escape_lark_md("a|b") == r"a\|b"
    assert escape_lark_md("[x]") == r"\[x\]"


def test_split_for_card_chunks_under_limit_is_passthrough():
    text = "a" * 100
    chunks = split_for_card_chunks(text, max_chars=200)
    assert chunks == [text]


def test_split_for_card_chunks_at_paragraph_boundary():
    text = "para one\n\npara two\n\npara three"
    chunks = split_for_card_chunks(text, max_chars=15)
    assert all(len(c) <= 15 + 2 for c in chunks)  # +2 for trailing \n\n on flush
    assert "para one" in chunks[0]
    assert chunks[-1].endswith("para three")


def test_split_for_card_chunks_hard_split_long_paragraph():
    text = "x" * 50
    chunks = split_for_card_chunks(text, max_chars=20)
    assert len(chunks) == 3
    assert all(len(c) <= 20 for c in chunks)
