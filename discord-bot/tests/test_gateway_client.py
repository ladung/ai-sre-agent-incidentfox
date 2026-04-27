from __future__ import annotations

from gateway_client import DiscordGatewayClient


class StubInvestigationHandler:
    async def handle(self, evt) -> None:
        pass

    @property
    def state(self):
        return None


class StubFeedbackHandler:
    async def handle_reaction(self, **kwargs) -> None:
        pass


def test_constructor_accepts_handlers_and_token():
    """Smoke test — construct without network access."""
    client = DiscordGatewayClient(
        bot_token="fake-token",
        guild_id=1234567890,
        investigation_handler=StubInvestigationHandler(),
        feedback_handler=StubFeedbackHandler(),
    )
    assert client is not None


def test_intents_include_message_content_and_reactions():
    """Critical: privileged intents must be enabled for the bot to receive messages and reactions."""
    client = DiscordGatewayClient(
        bot_token="fake",
        guild_id=1,
        investigation_handler=StubInvestigationHandler(),
        feedback_handler=StubFeedbackHandler(),
    )
    intents = client._intents()
    assert intents.message_content is True
    assert intents.guild_messages is True
    assert intents.guild_reactions is True
    assert intents.guilds is True
