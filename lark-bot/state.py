from __future__ import annotations

import re
from dataclasses import dataclass
from threading import RLock
from typing import Optional


@dataclass
class Investigation:
    session_id: str
    message_id: str            # Lark message ID of the bot's reply card
    status: str                # "running" | "completed" | "failed"
    last_update_ms: int = 0    # For stream_handler debounce


def _sanitize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def generate_session_id(*, chat_id: str, root_id: Optional[str]) -> str:
    """K8s-safe session id: lark-<chat>-<thread>, max 63 chars."""
    chat = _sanitize(chat_id)[:20] if chat_id else "dm"
    thread = _sanitize(root_id)[:30] if root_id else "main"
    return f"lark-{chat}-{thread}"


class ConversationState:
    """Thread-safe in-memory store. Keyed by session_id."""

    def __init__(self) -> None:
        self._items: dict[str, Investigation] = {}
        self._lock = RLock()

    def put(self, session_id: str, inv: Investigation) -> None:
        with self._lock:
            self._items[session_id] = inv

    def get(self, session_id: str) -> Optional[Investigation]:
        with self._lock:
            return self._items.get(session_id)

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._items.pop(session_id, None)
