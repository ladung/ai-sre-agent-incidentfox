from __future__ import annotations

import json
from typing import Any, Protocol

from card_builder import (
    build_error_card,
    build_final_card,
    build_status_card,
    build_streaming_card,
)
from event_router import LarkEvent
from state import ConversationState, Investigation, generate_session_id
from stream_handler import handle_stream


def _log(event: str, **fields: Any) -> None:
    try:
        print(json.dumps({"service": "lark-bot", "component": "investigation", "event": event, **fields}, default=str))
    except Exception:
        print(f"{event} {fields}")


class _LarkApi(Protocol):
    async def post_card(self, *, chat_id: str, root_id: str | None, card: dict) -> str: ...
    async def patch_card(self, *, message_id: str, card: dict) -> None: ...


class _Orchestrator(Protocol):
    def stream_agent(self, **kwargs): ...
    async def aclose(self) -> None: ...


class InvestigationHandler:
    def __init__(
        self,
        *,
        lark_api: _LarkApi,
        orchestrator: _Orchestrator,
        org_id: str,
        team_id: str,
        state: ConversationState | None = None,
        debounce_ms: int = 250,
    ) -> None:
        self._lark = lark_api
        self._orch = orchestrator
        self._org_id = org_id
        self._team_id = team_id
        self._state = state or ConversationState()
        self._debounce_ms = debounce_ms

    async def handle(self, evt: LarkEvent) -> None:
        prompt = (evt.text_after_mention or "").strip()
        if not prompt:
            _log("empty_prompt_skipped", event_id=evt.event_id)
            return

        session_id = generate_session_id(chat_id=evt.chat_id, root_id=evt.root_id or evt.message_id)
        status_card = build_status_card(prompt=prompt)
        message_id = await self._lark.post_card(
            chat_id=evt.chat_id, root_id=evt.root_id or evt.message_id, card=status_card
        )
        self._state.put(session_id, Investigation(
            session_id=session_id, message_id=message_id, status="running",
        ))
        _log("posted_status_card", session_id=session_id, message_id=message_id)

        try:
            async def on_update(text: str) -> None:
                card = build_streaming_card(prompt=prompt, partial_text=text)
                await self._lark.patch_card(message_id=message_id, card=card)

            async def on_final(text: str, success: bool) -> None:
                card = build_final_card(prompt=prompt, result_text=text, success=success)
                await self._lark.patch_card(message_id=message_id, card=card)
                self._state.clear(session_id)

            await handle_stream(
                self._orch.stream_agent(
                    message=prompt,
                    session_id=session_id,
                    tenant_id=self._org_id,
                    team_id=self._team_id,
                ),
                on_update=on_update,
                on_final=on_final,
                debounce_ms=self._debounce_ms,
            )
        except Exception as e:
            _log("orchestrator_call_failed", session_id=session_id, error=str(e))
            await self._lark.patch_card(
                message_id=message_id,
                card=build_error_card(prompt=prompt, error=str(e)),
            )
            self._state.clear(session_id)
