from __future__ import annotations

import re

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
_SLACK_USER_MENTION_RE = re.compile(r"\s*<@[UW][A-Z0-9]+>")


def to_lark_md(text: str) -> str:
    """Convert agent-emitted markdown to Lark md_v2 subset.

    - Headings → bold lines (Lark cards don't render h1-h6 inside divs).
    - Strip Slack-style user mentions (<@U123>); Lark uses <at user_id="..."> emitted by card_builder.
    - Pass through bold, italic, code, code fences, links.
    """
    text = _HEADING_RE.sub(lambda m: f"**{m.group(2).strip()}**", text)
    text = _SLACK_USER_MENTION_RE.sub("", text)
    return text


def escape_lark_md(s: str) -> str:
    """Escape user-supplied text before inserting into a card cell."""
    return s.replace("\\", "\\\\").replace("|", r"\|").replace("[", r"\[").replace("]", r"\]")


def split_for_card_chunks(text: str, *, max_chars: int = 4000) -> list[str]:
    """Split long text into card-friendly chunks.

    Lark's per-element text limit is 4096 chars (we use 4000 default for safety margin).
    Prefer paragraph boundaries; fall back to hard split.
    """
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    buffer = ""
    for para in text.split("\n\n"):
        candidate = (buffer + ("\n\n" if buffer else "") + para)
        if len(candidate) <= max_chars:
            buffer = candidate
            continue
        if buffer:
            chunks.append(buffer)
            buffer = ""
        # Paragraph itself too large — hard split.
        for i in range(0, len(para), max_chars):
            chunks.append(para[i:i + max_chars])
    if buffer:
        chunks.append(buffer)
    return chunks
