from __future__ import annotations

import pytest

from ws_client import LarkWsClient, _decode_oapi_event


def test_decode_oapi_event_extracts_payload():
    """Given a lark-oapi event-dispatcher payload, return the raw dict shape we feed to event_router."""
    class FakeHeader:
        event_id = "evt1"
        event_type = "im.message.receive_v1"
        tenant_key = "tk"
        create_time = "1700000000000"

    class FakeMsg:
        message_id = "om_1"
        chat_id = "oc_x"
        chat_type = "group"
        message_type = "text"
        content = '{"text":"@_user_1 hi"}'
        root_id = None
        mentions = [{"key": "@_user_1", "id": {"open_id": "ou_bot"}}]

    class FakeEvent:
        header = FakeHeader()
        event = type("E", (), {
            "sender": type("S", (), {"sender_id": type("I", (), {"open_id": "ou_1"})()})(),
            "message": FakeMsg(),
        })()

    payload = _decode_oapi_event(FakeEvent())
    assert payload["header"]["event_type"] == "im.message.receive_v1"
    assert payload["event"]["message"]["chat_id"] == "oc_x"


def test_ws_client_constructor_accepts_handler():
    """Smoke: object constructs without error given a stub handler."""
    class StubHandler:
        async def handle(self, evt): pass

    c = LarkWsClient(
        app_id="cli_x", app_secret="s", api_base="https://open.larksuite.com",
        handler=StubHandler(),
    )
    assert c is not None
