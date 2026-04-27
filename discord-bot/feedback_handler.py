from __future__ import annotations

import enum
import json
from datetime import datetime, timezone
from typing import Any

import httpx
from state import ConversationState


def _log(event: str, **fields: Any) -> None:
    try:
        print(json.dumps({"service": "discord-bot", "component": "feedback", "event": event, **fields}, default=str))
    except Exception:
        print(f"{event} {fields}")


class ReactionType(str, enum.Enum):
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"


class FeedbackHandler:
    def __init__(
        self,
        *,
        config_service_url: str,
        team_token: str,
        state: ConversationState,
        timeout: float = 5.0,
    ) -> None:
        self._url = config_service_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"Authorization": f"Bearer {team_token}", "Content-Type": "application/json"},
        )
        self._state = state

    async def handle_reaction(
        self,
        *,
        reaction: ReactionType,
        bot_message_id: int,
        user_id: int,
    ) -> None:
        inv = self._state.get(bot_message_id)
        if inv is None:
            _log("reaction_on_unknown_message", bot_message_id=bot_message_id)
            return

        body = {
            "session_id": inv.session_id,
            "user_id": str(user_id),
            "reaction": reaction.value,
            "source": "discord",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            resp = await self._http.post(f"{self._url}/api/v1/feedback", json=body)
            if resp.status_code >= 400:
                _log("feedback_post_non_2xx", status=resp.status_code, body=resp.text[:200])
            else:
                _log("feedback_recorded", session_id=inv.session_id, reaction=reaction.value)
        except httpx.HTTPError as e:
            _log("feedback_post_failed", error=str(e))

    async def aclose(self) -> None:
        await self._http.aclose()
