from __future__ import annotations

import pytest

from event_router import LarkEvent
from investigation_handler import InvestigationHandler


class FakeLarkApi:
    def __init__(self) -> None:
        self.posted: list[dict] = []
        self.patched: list[tuple[str, dict]] = []
        self._next_msg_id = "om_card_1"

    async def post_card(self, *, chat_id: str, root_id, card: dict) -> str:
        self.posted.append({"chat_id": chat_id, "root_id": root_id, "card": card})
        return self._next_msg_id

    async def patch_card(self, *, message_id: str, card: dict) -> None:
        self.patched.append((message_id, card))


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
async def test_investigation_posts_status_card_then_finalizes():
    api = FakeLarkApi()
    orch = FakeOrchestrator()
    handler = InvestigationHandler(
        lark_api=api,
        orchestrator=orch,
        org_id="org",
        team_id="team",
        debounce_ms=0,
    )
    evt = LarkEvent(
        event_type="im.message.receive_v1",
        event_id="evt1",
        tenant_key="tk",
        chat_id="oc_x",
        message_id="om_user_1",
        text_after_mention="why is checkout slow?",
        is_mention=True,
    )
    await handler.handle(evt)
    assert len(api.posted) == 1
    assert "Investigating" in api.posted[0]["card"]["body"]["elements"][0]["text"]["content"]
    assert len(api.patched) >= 1
    final_card = api.patched[-1][1]
    assert final_card["header"]["template"] == "green"


@pytest.mark.asyncio
async def test_investigation_renders_error_card_on_orchestrator_failure():
    class BoomOrchestrator:
        async def stream_agent(self, **kwargs):
            raise RuntimeError("orchestrator unreachable")
            yield  # unreachable; makes function a generator

        async def aclose(self): pass

    api = FakeLarkApi()
    handler = InvestigationHandler(
        lark_api=api, orchestrator=BoomOrchestrator(),
        org_id="o", team_id="t", debounce_ms=0,
    )
    await handler.handle(LarkEvent(
        event_type="im.message.receive_v1", chat_id="c", message_id="m",
        text_after_mention="x", is_mention=True,
    ))
    final_card = api.patched[-1][1]
    assert final_card["header"]["template"] == "red"
    body = final_card["body"]["elements"]
    assert any("orchestrator unreachable" in el.get("text", {}).get("content", "") for el in body)
