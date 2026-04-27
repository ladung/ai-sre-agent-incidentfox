from __future__ import annotations

import json
from typing import Any, Protocol

from embed_builder import (
    build_error_embed,
    build_final_embed,
    build_status_embed,
    build_streaming_embed,
)
from event_router import DiscordMessageEvent
from state import ConversationState, Investigation, generate_session_id
from stream_handler import handle_stream


def _log(event: str, **fields: Any) -> None:
    try:
        print(json.dumps({"service": "discord-bot", "component": "investigation", "event": event, **fields}, default=str))
    except Exception:
        print(f"{event} {fields}")


class _Discord(Protocol):
    async def send_embed(self, *, channel_id: int, reply_to_message_id: int, embed: dict) -> int: ...
    async def edit_embed(self, *, message_id: int, embed: dict) -> None: ...
    async def add_reaction(self, *, message_id: int, emoji: str) -> None: ...


class _Orchestrator(Protocol):
    def stream_agent(self, **kwargs): ...
    async def aclose(self) -> None: ...


class InvestigationHandler:
    def __init__(
        self,
        *,
        discord: _Discord,
        orchestrator: _Orchestrator,
        org_id: str,
        team_id: str,
        state: ConversationState | None = None,
        debounce_ms: int = 250,
    ) -> None:
        self._discord = discord
        self._orch = orchestrator
        self._org_id = org_id
        self._team_id = team_id
        self._state = state or ConversationState()
        self._debounce_ms = debounce_ms

    @property
    def state(self) -> ConversationState:
        return self._state

    async def handle(self, evt: DiscordMessageEvent) -> None:
        prompt = (evt.text_after_mention or "").strip()
        if not prompt:
            _log("empty_prompt_skipped", message_id=evt.message_id)
            return

        session_id = generate_session_id(channel_id=evt.channel_id, message_id=evt.message_id)
        status_embed = build_status_embed(prompt=prompt)
        bot_message_id = await self._discord.send_embed(
            channel_id=evt.channel_id,
            reply_to_message_id=evt.message_id,
            embed=status_embed,
        )
        self._state.put(bot_message_id, Investigation(
            session_id=session_id, bot_message_id=bot_message_id, status="running",
        ))
        _log("posted_status_embed", session_id=session_id, bot_message_id=bot_message_id)

        try:
            async def on_update(text: str) -> None:
                embed = build_streaming_embed(prompt=prompt, partial_text=text)
                await self._discord.edit_embed(message_id=bot_message_id, embed=embed)

            async def on_final(text: str, success: bool) -> None:
                embed = build_final_embed(prompt=prompt, result_text=text, success=success)
                await self._discord.edit_embed(message_id=bot_message_id, embed=embed)
                # Add feedback reactions
                try:
                    await self._discord.add_reaction(message_id=bot_message_id, emoji="👍")
                    await self._discord.add_reaction(message_id=bot_message_id, emoji="👎")
                except Exception as e:
                    _log("reaction_add_failed", error=str(e))
                # Update state status (kept in state for reaction lookup)
                inv = self._state.get(bot_message_id)
                if inv:
                    inv.status = "completed" if success else "failed"

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
            await self._discord.edit_embed(
                message_id=bot_message_id,
                embed=build_error_embed(prompt=prompt, error=str(e)),
            )
