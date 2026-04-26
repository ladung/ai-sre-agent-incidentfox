from __future__ import annotations

import pytest

from event_router import LarkEvent, normalize_event, EventValidationError


def _msg_event_payload(*, message_text="@_user_1 hello", chat_id="oc_abc", root_id=None):
    return {
        "schema": "2.0",
        "header": {
            "event_id": "evt_1",
            "event_type": "im.message.receive_v1",
            "tenant_key": "tk_123",
            "create_time": "1700000000000",
        },
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_id": "om_1",
                "root_id": root_id,
                "chat_id": chat_id,
                "chat_type": "group",
                "message_type": "text",
                "content": '{"text": "' + message_text + '"}',
                "mentions": [{"key": "@_user_1", "id": {"open_id": "ou_bot"}}],
            },
        },
    }


def test_normalize_at_mention_message():
    evt = normalize_event(_msg_event_payload(message_text="@_user_1 why is checkout slow?"))
    assert isinstance(evt, LarkEvent)
    assert evt.event_id == "evt_1"
    assert evt.tenant_key == "tk_123"
    assert evt.chat_id == "oc_abc"
    assert evt.message_id == "om_1"
    assert evt.root_id is None
    assert evt.is_mention is True
    assert evt.text_after_mention == "why is checkout slow?"
    assert evt.sender_open_id == "ou_1"


def test_normalize_thread_followup_uses_root_id():
    evt = normalize_event(_msg_event_payload(root_id="om_thread_root"))
    assert evt.root_id == "om_thread_root"


def test_normalize_p2p_dm_no_mention_required():
    payload = _msg_event_payload(message_text="hi")
    payload["event"]["message"]["chat_type"] = "p2p"
    payload["event"]["message"]["mentions"] = []
    evt = normalize_event(payload)
    assert evt.is_mention is False
    assert evt.is_dm is True
    assert evt.text_after_mention == "hi"


def test_url_verification_returns_special_marker():
    payload = {"type": "url_verification", "challenge": "abc123"}
    evt = normalize_event(payload)
    assert evt.event_type == "url_verification"
    assert evt.url_verification_challenge == "abc123"


def test_unknown_event_type_raises():
    payload = {"schema": "2.0", "header": {"event_type": "im.message.something_unsupported"}}
    with pytest.raises(EventValidationError):
        normalize_event(payload)


def test_non_text_message_returns_none_text():
    payload = _msg_event_payload()
    payload["event"]["message"]["message_type"] = "image"
    payload["event"]["message"]["content"] = '{"image_key": "img_x"}'
    evt = normalize_event(payload)
    assert evt.text_after_mention == ""
