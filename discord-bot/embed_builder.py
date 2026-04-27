from __future__ import annotations

from typing import Any

from markdown_utils import escape_discord_md, to_discord_md

COLOR_BLUE = 0x3498DB    # 3447003
COLOR_GREEN = 0x2ECC71   # 3066993
COLOR_RED = 0xE74C3C     # 15158332

EmbedDict = dict[str, Any]

DESCRIPTION_HARD_LIMIT = 4096
DESCRIPTION_SAFE_LIMIT = 4000


def _truncate(text: str, *, limit: int = DESCRIPTION_HARD_LIMIT) -> str:
    if len(text) <= limit:
        return text
    suffix = "\n…(truncated — Phase 2 will add multi-embed fan-out)"
    return text[: limit - len(suffix)] + suffix


def build_status_embed(*, prompt: str) -> EmbedDict:
    safe = escape_discord_md(prompt)
    return {
        "title": "IncidentFox Investigation",
        "description": f"**Investigating…**\n\n> {safe}\n\n_This embed will update as I work._",
        "color": COLOR_BLUE,
    }


def build_streaming_embed(*, prompt: str, partial_text: str) -> EmbedDict:
    safe_prompt = escape_discord_md(prompt)
    body = to_discord_md(partial_text)
    description = f"**Investigating…**\n\n> {safe_prompt}\n\n---\n\n{body}"
    return {
        "title": "IncidentFox Investigation",
        "description": _truncate(description),
        "color": COLOR_BLUE,
    }


def build_final_embed(*, prompt: str, result_text: str, success: bool) -> EmbedDict:
    safe_prompt = escape_discord_md(prompt)
    body = to_discord_md(result_text)
    description = f"**Question**\n\n> {safe_prompt}\n\n---\n\n{body}"
    return {
        "title": "Investigation Complete" if success else "Investigation Failed",
        "description": _truncate(description),
        "color": COLOR_GREEN if success else COLOR_RED,
    }


def build_error_embed(*, prompt: str, error: str) -> EmbedDict:
    safe_prompt = escape_discord_md(prompt)
    safe_err = escape_discord_md(error)
    return {
        "title": "Investigation Failed",
        "description": f"**Question**\n\n> {safe_prompt}\n\n---\n\n**Error:** {safe_err}",
        "color": COLOR_RED,
    }


# Note: multi-embed fan-out (`embeds_for_long_result`) is deferred to Phase 2 since
# the InvestigationHandler currently uses single-embed `edit_embed` for progressive
# updates. Long results are truncated by `_truncate()` above. See spec section 7.
