from __future__ import annotations

import httpx
import respx
from feedback_handler import FeedbackHandler, ReactionType
from state import ConversationState, Investigation


@respx.mock
async def test_thumbs_up_posts_to_config_service():
    state = ConversationState()
    state.put(42, Investigation(session_id="discord-c-m", bot_message_id=42, status="completed"))

    route = respx.post("http://config:8080/api/v1/feedback").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    handler = FeedbackHandler(
        config_service_url="http://config:8080",
        team_token="tok",
        state=state,
    )
    await handler.handle_reaction(
        reaction=ReactionType.THUMBS_UP,
        bot_message_id=42,
        user_id=12345,
    )

    assert route.called
    body = route.calls.last.request.read().decode()
    assert "discord-c-m" in body
    assert "thumbs_up" in body
    assert "12345" in body
    await handler.aclose()


@respx.mock
async def test_thumbs_down_posts_with_correct_reaction_field():
    state = ConversationState()
    state.put(42, Investigation(session_id="s", bot_message_id=42, status="completed"))

    route = respx.post("http://config:8080/api/v1/feedback").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    handler = FeedbackHandler(config_service_url="http://config:8080", team_token="t", state=state)
    await handler.handle_reaction(reaction=ReactionType.THUMBS_DOWN, bot_message_id=42, user_id=1)
    body = route.calls.last.request.read().decode()
    assert "thumbs_down" in body
    await handler.aclose()


@respx.mock
async def test_reaction_on_unknown_message_is_silently_ignored():
    state = ConversationState()  # empty
    route = respx.post("http://config:8080/api/v1/feedback").mock(
        return_value=httpx.Response(200)
    )
    handler = FeedbackHandler(config_service_url="http://config:8080", team_token="t", state=state)
    await handler.handle_reaction(reaction=ReactionType.THUMBS_UP, bot_message_id=99999, user_id=1)
    assert not route.called  # No POST when message_id has no investigation
    await handler.aclose()


@respx.mock
async def test_config_service_failure_is_swallowed():
    state = ConversationState()
    state.put(42, Investigation(session_id="s", bot_message_id=42, status="completed"))

    respx.post("http://config:8080/api/v1/feedback").mock(
        return_value=httpx.Response(503, json={"error": "down"})
    )
    handler = FeedbackHandler(config_service_url="http://config:8080", team_token="t", state=state)
    # Must NOT raise — feedback failures are non-fatal.
    await handler.handle_reaction(reaction=ReactionType.THUMBS_UP, bot_message_id=42, user_id=1)
    await handler.aclose()
