from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class DiscordMessageEvent:
    message_id: int
    channel_id: int
    guild_id: int
    author_id: int
    text_after_mention: str
    is_mention: bool


def _strip_mentions_for_user(text: str, user_id: int) -> str:
    """Remove all forms of <@USER_ID> and <@!USER_ID> mention strings for the given user."""
    pattern = re.compile(rf"<@!?{user_id}>")
    return pattern.sub("", text).strip()


def normalize_message(
    message: Any,
    *,
    bot_user_id: int,
    bound_guild_id: Optional[int] = None,
) -> Optional[DiscordMessageEvent]:
    """Normalize a discord.py Message into a unified event dataclass.

    Returns None to indicate the message should be ignored:
    - Bot's own messages
    - Messages without an @-mention of this bot
    - Messages outside `bound_guild_id` if specified
    """
    # Filter: bot's own messages
    if getattr(message.author, "id", None) == bot_user_id:
        return None

    # Filter: outside bound guild
    if bound_guild_id is not None and getattr(message.guild, "id", None) != bound_guild_id:
        return None

    # Filter: must mention this bot
    mention_ids = {getattr(m, "id", None) for m in (message.mentions or [])}
    if bot_user_id not in mention_ids:
        return None

    text = _strip_mentions_for_user(message.content or "", bot_user_id)

    return DiscordMessageEvent(
        message_id=message.id,
        channel_id=message.channel.id,
        guild_id=message.guild.id,
        author_id=message.author.id,
        text_after_mention=text,
        is_mention=True,
    )
