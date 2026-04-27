from __future__ import annotations

import pytest

from event_router import DiscordMessageEvent
from investigation_handler import InvestigationHandler


class FakeDiscordChannel:
    def __init__(self) -> None:
        self.posted: list[dict] = []
        self.edits: list[tuple[int, dict]] = []
        self.reactions: list[tuple[int, str]] = []
        self._next_msg_id = 5000

    async def send_embed(self, *, channel_id: int, reply_to_message_id: int, embed: dict) -> int:
        self.posted.append({"channel_id": channel_id, "reply_to": reply_to_message_id, "embed": embed})
        msg_id = self._next_msg_id
        self._next_msg_id += 1
        return msg_id

    async def edit_embed(self, *, message_id: int, embed: dict) -> None:
        self.edits.append((message_id, embed))

    async def add_reaction(self, *, message_id: int, emoji: str) -> None:
        self.reactions.append((message_id, emoji))


class FakeOrchestrator:
    async def stream_agent(self, **kwargs):
        async def gen():
            yield {"type": "text", "text": "Looking at pods… "}
            yield {"type": "text", "text": "found OOMKilled."}
            yield {"type": "complete", "result": "Looking at pods… found OOMKilled.", "success": True}
        async for e in gen():
            yield e

    async def aclose(self) -> None:
        pass


@pytest.mark.asyncio
async def test_investigation_full_happy_path():
    channel = FakeDiscordChannel()
    orch = FakeOrchestrator()
    handler = InvestigationHandler(
        discord=channel,
        orchestrator=orch,
        org_id="o",
        team_id="t",
        debounce_ms=0,
    )
    evt = DiscordMessageEvent(
        message_id=1, channel_id=100, guild_id=1000, author_id=42,
        text_after_mention="why is checkout slow?", is_mention=True,
    )
    await handler.handle(evt)

    # Posted initial embed
    assert len(channel.posted) == 1
    assert "Investigating" in channel.posted[0]["embed"]["description"]

    # Final embed edit is green/Complete
    assert len(channel.edits) >= 1
    final_msg_id, final_embed = channel.edits[-1]
    assert final_embed["title"] == "Investigation Complete"

    # Reactions added (👍 and 👎)
    emojis = [r[1] for r in channel.reactions]
    assert "👍" in emojis
    assert "👎" in emojis


@pytest.mark.asyncio
async def test_orchestrator_failure_yields_error_embed():
    class BoomOrchestrator:
        async def stream_agent(self, **kwargs):
            raise RuntimeError("orchestrator unreachable")
            yield  # pragma: no cover

        async def aclose(self): pass

    channel = FakeDiscordChannel()
    handler = InvestigationHandler(discord=channel, orchestrator=BoomOrchestrator(), org_id="o", team_id="t", debounce_ms=0)
    await handler.handle(DiscordMessageEvent(
        message_id=1, channel_id=100, guild_id=1000, author_id=42,
        text_after_mention="x", is_mention=True,
    ))
    final_embed = channel.edits[-1][1]
    assert final_embed["title"] == "Investigation Failed"
    assert "orchestrator unreachable" in final_embed["description"]


@pytest.mark.asyncio
async def test_empty_prompt_is_skipped():
    channel = FakeDiscordChannel()
    handler = InvestigationHandler(discord=channel, orchestrator=FakeOrchestrator(), org_id="o", team_id="t", debounce_ms=0)
    await handler.handle(DiscordMessageEvent(
        message_id=1, channel_id=100, guild_id=1000, author_id=42,
        text_after_mention="   ", is_mention=True,
    ))
    assert channel.posted == []
    assert channel.edits == []
