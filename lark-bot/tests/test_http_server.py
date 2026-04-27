from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from http_server import build_app


class _StubInv:
    def __init__(self) -> None:
        self.calls = []

    async def handle(self, evt) -> None:
        self.calls.append(evt)


def test_healthz_returns_ok():
    inv = _StubInv()
    app = build_app(handler=inv)
    client = TestClient(app)
    assert client.get("/healthz").json() == {"status": "ok"}


def test_url_verification_echoes_challenge():
    inv = _StubInv()
    app = build_app(handler=inv)
    client = TestClient(app)
    r = client.post("/internal/lark/event", json={"type": "url_verification", "challenge": "xyz"})
    assert r.status_code == 200
    assert r.json() == {"challenge": "xyz"}
    assert inv.calls == []  # url_verification is not dispatched to handler


def test_message_event_dispatches_to_handler():
    inv = _StubInv()
    app = build_app(handler=inv)
    client = TestClient(app)
    payload = {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1", "event_id": "evt", "tenant_key": "tk"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_id": "om_1", "chat_id": "oc_x", "chat_type": "group",
                "message_type": "text",
                "content": '{"text": "@_user_1 hello"}',
                "mentions": [{"key": "@_user_1", "id": {"open_id": "ou_bot"}}],
            },
        },
    }
    r = client.post("/internal/lark/event", json=payload)
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert len(inv.calls) == 1
    assert inv.calls[0].text_after_mention == "hello"


def test_dedup_event_id_is_idempotent():
    inv = _StubInv()
    app = build_app(handler=inv, dedup_window=64)
    client = TestClient(app)
    payload = {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1", "event_id": "dup_1", "tenant_key": "tk"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_id": "om_1", "chat_id": "c", "chat_type": "group",
                "message_type": "text",
                "content": '{"text":"hi"}',
                "mentions": [{"key": "@_b", "id": {"open_id": "b"}}],
            },
        },
    }
    client.post("/internal/lark/event", json=payload)
    client.post("/internal/lark/event", json=payload)
    assert len(inv.calls) == 1
