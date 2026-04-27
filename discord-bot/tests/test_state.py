from __future__ import annotations

import re

from state import ConversationState, Investigation, generate_session_id


def test_session_id_stable_for_same_channel_and_message():
    a = generate_session_id(channel_id=12345, message_id=67890)
    b = generate_session_id(channel_id=12345, message_id=67890)
    assert a == b
    assert a.startswith("discord-")
    assert len(a) <= 63
    assert re.fullmatch(r"[a-z0-9-]+", a)


def test_session_id_handles_large_snowflake_ids():
    sid = generate_session_id(channel_id=987654321098765432, message_id=123456789012345678)
    assert sid.startswith("discord-")
    assert len(sid) <= 63
    assert re.fullmatch(r"[a-z0-9-]+", sid)


def test_conversation_state_get_set():
    s = ConversationState()
    inv = Investigation(session_id="discord-abc", bot_message_id=12345, status="running")
    s.put(12345, inv)
    assert s.get(12345) is inv
    assert s.get(99999) is None


def test_conversation_state_clear():
    s = ConversationState()
    s.put(1, Investigation(session_id="s", bot_message_id=1, status="running"))
    s.clear(1)
    assert s.get(1) is None


def test_conversation_state_keyed_by_bot_message_id_for_reaction_lookup():
    """When a reaction arrives, we resolve via the bot's message_id (not the user's)."""
    s = ConversationState()
    inv = Investigation(session_id="discord-c-m", bot_message_id=42, status="completed")
    s.put(42, inv)
    assert s.get(42).session_id == "discord-c-m"
