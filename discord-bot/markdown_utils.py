from __future__ import annotations

import re

_SLACK_USER_MENTION_RE = re.compile(r"\s*<@[UW][A-Z0-9]+>")


def to_discord_md(text: str) -> str:
    """Convert agent-emitted markdown to Discord markdown.

    Discord supports standard GitHub-flavored markdown inside embed descriptions.
    Headings (#, ##) ARE rendered (unlike Lark cards). The only conversion needed:
    - Strip Slack-style user mentions (<@U123>) since Discord's mention syntax differs.
    """
    return _SLACK_USER_MENTION_RE.sub("", text)


def escape_discord_md(s: str) -> str:
    """Escape user-supplied text before inserting into a Discord embed.

    Discord markdown special chars: \\, *, _, `, ~, |
    Backslash must be escaped first to avoid double-escaping.
    """
    out = s.replace("\\", "\\\\")
    out = out.replace("*", "\\*")
    out = out.replace("_", "\\_")
    out = out.replace("`", "\\`")
    out = out.replace("~", "\\~")
    out = out.replace("|", "\\|")
    return out


def split_for_embed_chunks(text: str, *, max_chars: int = 4000) -> list[str]:
    """Split long text into Discord embed-description-friendly chunks.

    Discord's embed.description hard limit is 4096 chars; default is 4000 for safety.
    Prefer paragraph boundaries; fall back to hard split for runs longer than max_chars.
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
        for i in range(0, len(para), max_chars):
            chunks.append(para[i:i + max_chars])
    if buffer:
        chunks.append(buffer)
    return chunks
