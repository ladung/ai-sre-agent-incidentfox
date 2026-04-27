from __future__ import annotations

import re
from dataclasses import dataclass
from threading import RLock
from typing import Optional


@dataclass
class Investigation:
    session_id: str
    bot_message_id: int   # The Discord message_id of the bot's reply embed
    status: str           # "running" | "completed" | "failed"
    last_update_ms: int = 0


def _sanitize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def generate_session_id(*, channel_id: int, message_id: int) -> str:
    """K8s-safe session id: discord-<channel>-<message>, max 63 chars."""
    chan = _sanitize(str(channel_id))[:25]
    msg = _sanitize(str(message_id))[:25]
    return f"discord-{chan}-{msg}"


class ConversationState:
    """Thread-safe in-memory store. Keyed by the bot's reply message_id."""

    def __init__(self) -> None:
        self._items: dict[int, Investigation] = {}
        self._lock = RLock()

    def put(self, bot_message_id: int, inv: Investigation) -> None:
        with self._lock:
            self._items[bot_message_id] = inv

    def get(self, bot_message_id: int) -> Optional[Investigation]:
        with self._lock:
            return self._items.get(bot_message_id)

    def clear(self, bot_message_id: int) -> None:
        with self._lock:
            self._items.pop(bot_message_id, None)
