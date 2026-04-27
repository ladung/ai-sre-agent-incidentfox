from __future__ import annotations

import base64
import hashlib
import json
import os

import httpx
import pytest
import respx
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from fastapi.testclient import TestClient

from incidentfox_orchestrator.webhooks.lark_app import build_lark_router


def _encrypt(plain: str, key: str) -> str:
    iv = os.urandom(16)
    aes = AES.new(hashlib.sha256(key.encode()).digest(), AES.MODE_CBC, iv=iv)
    return base64.b64encode(iv + aes.encrypt(pad(plain.encode(), AES.block_size))).decode()


def _sign(ts: str, nonce: str, ek: str, body: str) -> str:
    return hashlib.sha256((ts + nonce + ek + body).encode()).hexdigest()


@pytest.fixture
def app(monkeypatch):
    from fastapi import FastAPI
    monkeypatch.setenv("LARK_VERIFICATION_TOKEN", "vtok")
    monkeypatch.setenv("LARK_ENCRYPT_KEY", "ekey")
    monkeypatch.setenv("LARK_BOT_INTERNAL_URL", "http://lark-bot:8080")
    a = FastAPI()
    a.include_router(build_lark_router())
    return a


@respx.mock
def test_url_verification_decrypts_and_echoes(app):
    inner = json.dumps({"type": "url_verification", "challenge": "ch1", "token": "vtok"})
    encrypted = _encrypt(inner, "ekey")
    body = json.dumps({"encrypt": encrypted})
    sig = _sign("1700", "n1", "ekey", body)

    client = TestClient(app)
    r = client.post(
        "/webhooks/lark",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Lark-Signature": sig,
            "X-Lark-Request-Timestamp": "1700",
            "X-Lark-Request-Nonce": "n1",
        },
    )
    assert r.status_code == 200
    assert r.json() == {"challenge": "ch1"}


@respx.mock
def test_event_forwards_to_lark_bot_internal(app):
    inner_event = {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1", "event_id": "e1", "tenant_key": "tk"},
        "event": {"sender": {"sender_id": {"open_id": "ou_1"}},
                  "message": {"message_id": "om", "chat_id": "c", "chat_type": "p2p",
                              "message_type": "text", "content": '{"text":"hi"}',
                              "mentions": []}},
        "token": "vtok",
    }
    encrypted = _encrypt(json.dumps(inner_event), "ekey")
    body = json.dumps({"encrypt": encrypted})
    sig = _sign("1700", "n1", "ekey", body)

    forwarded = respx.post("http://lark-bot:8080/internal/lark/event").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    client = TestClient(app)
    r = client.post(
        "/webhooks/lark",
        content=body,
        headers={"X-Lark-Signature": sig, "X-Lark-Request-Timestamp": "1700", "X-Lark-Request-Nonce": "n1"},
    )
    assert r.status_code == 200
    assert forwarded.called
    forwarded_body = json.loads(forwarded.calls.last.request.read())
    assert forwarded_body["header"]["event_type"] == "im.message.receive_v1"


def test_bad_signature_returns_401(app):
    body = json.dumps({"encrypt": "anything"})
    client = TestClient(app)
    r = client.post(
        "/webhooks/lark",
        content=body,
        headers={"X-Lark-Signature": "bad", "X-Lark-Request-Timestamp": "1700", "X-Lark-Request-Nonce": "n1"},
    )
    assert r.status_code == 401


def test_token_mismatch_returns_401(app):
    inner = json.dumps({"type": "url_verification", "challenge": "ch", "token": "WRONG"})
    encrypted = _encrypt(inner, "ekey")
    body = json.dumps({"encrypt": encrypted})
    sig = _sign("1700", "n1", "ekey", body)
    client = TestClient(app)
    r = client.post(
        "/webhooks/lark",
        content=body,
        headers={"X-Lark-Signature": sig, "X-Lark-Request-Timestamp": "1700", "X-Lark-Request-Nonce": "n1"},
    )
    assert r.status_code == 401
