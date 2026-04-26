from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

SUPPORTED_EVENT_TYPES = {"im.message.receive_v1", "url_verification"}


class EventValidationError(Exception):
    pass


@dataclass
class LarkEvent:
    event_type: str
    event_id: str = ""
    tenant_key: str = ""
    chat_id: str = ""
    chat_type: str = ""               # "p2p" | "group"
    message_id: str = ""
    root_id: Optional[str] = None
    sender_open_id: str = ""
    message_type: str = ""             # "text" | "image" | ...
    text_after_mention: str = ""
    is_mention: bool = False
    is_dm: bool = False
    url_verification_challenge: str = ""


def _strip_mentions(text: str, mention_keys: list[str]) -> str:
    out = text
    for key in mention_keys:
        out = out.replace(key, "")
    return out.strip()


def normalize_event(payload: dict[str, Any]) -> LarkEvent:
    if payload.get("type") == "url_verification":
        return LarkEvent(
            event_type="url_verification",
            url_verification_challenge=str(payload.get("challenge", "")),
        )

    header = payload.get("header") or {}
    event_type = header.get("event_type", "")
    if event_type not in SUPPORTED_EVENT_TYPES:
        raise EventValidationError(f"unsupported event_type: {event_type!r}")

    body = payload.get("event") or {}
    msg = body.get("message") or {}
    sender = (body.get("sender") or {}).get("sender_id") or {}
    mentions = msg.get("mentions") or []
    chat_type = msg.get("chat_type", "")
    message_type = msg.get("message_type", "")

    text = ""
    if message_type == "text":
        try:
            content = json.loads(msg.get("content", "{}"))
            text = content.get("text", "")
        except json.JSONDecodeError:
            text = ""

    mention_keys = [m.get("key", "") for m in mentions if m.get("key")]
    is_mention = bool(mention_keys)
    text_after_mention = _strip_mentions(text, mention_keys) if text else ""

    return LarkEvent(
        event_type=event_type,
        event_id=header.get("event_id", ""),
        tenant_key=header.get("tenant_key", ""),
        chat_id=msg.get("chat_id", ""),
        chat_type=chat_type,
        message_id=msg.get("message_id", ""),
        root_id=msg.get("root_id") or None,
        sender_open_id=sender.get("open_id", ""),
        message_type=message_type,
        text_after_mention=text_after_mention,
        is_mention=is_mention,
        is_dm=(chat_type == "p2p"),
    )
