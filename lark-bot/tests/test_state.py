from __future__ import annotations

import re

from state import ConversationState, Investigation, generate_session_id


def test_session_id_stable_for_same_chat_and_thread():
    a = generate_session_id(chat_id="oc_abc", root_id="om_xyz")
    b = generate_session_id(chat_id="oc_abc", root_id="om_xyz")
    assert a == b
    assert a.startswith("lark-")
    assert len(a) <= 63  # K8s RFC 1123 label limit


def test_session_id_dm_when_no_thread():
    sid = generate_session_id(chat_id="p2p_user1", root_id=None)
    assert sid.startswith("lark-")


def test_session_id_sanitizes_non_alphanumeric():
    sid = generate_session_id(chat_id="oc_AbC.123", root_id="om/xyz_456")
    assert sid.replace("-", "").islower()
    assert re.fullmatch(r"[a-z0-9-]+", sid)


def test_conversation_state_get_set():
    s = ConversationState()
    inv = Investigation(session_id="lark-abc", message_id="om_123", status="running")
    s.put("lark-abc", inv)
    assert s.get("lark-abc") is inv
    assert s.get("missing") is None


def test_conversation_state_clear():
    s = ConversationState()
    s.put("k", Investigation(session_id="k", message_id="m", status="running"))
    s.clear("k")
    assert s.get("k") is None
