from __future__ import annotations

from event_router import DiscordMessageEvent, normalize_message


class _FakeAuthor:
    def __init__(self, id: int, bot: bool = False) -> None:
        self.id = id
        self.bot = bot


class _FakeMessage:
    def __init__(
        self,
        *,
        msg_id: int = 1,
        channel_id: int = 100,
        guild_id: int = 1000,
        author: _FakeAuthor,
        content: str = "",
        mentions: list[_FakeAuthor] | None = None,
    ) -> None:
        self.id = msg_id
        self.channel = type("C", (), {"id": channel_id})()
        self.guild = type("G", (), {"id": guild_id})()
        self.author = author
        self.content = content
        self.mentions = mentions or []


def test_normalize_at_mention_strips_mention_and_returns_event():
    bot_user_id = 999
    user = _FakeAuthor(id=42)
    bot = _FakeAuthor(id=bot_user_id, bot=True)
    msg = _FakeMessage(
        author=user,
        content="<@999> why is checkout slow?",
        mentions=[bot],
    )
    evt = normalize_message(msg, bot_user_id=bot_user_id)
    assert isinstance(evt, DiscordMessageEvent)
    assert evt.message_id == 1
    assert evt.channel_id == 100
    assert evt.guild_id == 1000
    assert evt.author_id == 42
    assert evt.is_mention is True
    assert evt.text_after_mention == "why is checkout slow?"


def test_normalize_handles_nickname_mention_format():
    """Discord uses both <@123> and <@!123> (the nickname form)."""
    bot_user_id = 999
    user = _FakeAuthor(id=42)
    bot = _FakeAuthor(id=bot_user_id, bot=True)
    msg = _FakeMessage(
        author=user,
        content="<@!999> hello",
        mentions=[bot],
    )
    evt = normalize_message(msg, bot_user_id=bot_user_id)
    assert evt.text_after_mention == "hello"


def test_normalize_returns_none_when_message_is_from_bot_itself():
    bot_user_id = 999
    msg = _FakeMessage(author=_FakeAuthor(id=bot_user_id, bot=True), content="anything")
    assert normalize_message(msg, bot_user_id=bot_user_id) is None


def test_normalize_returns_none_when_message_has_no_bot_mention():
    bot_user_id = 999
    other_bot = _FakeAuthor(id=111, bot=True)
    msg = _FakeMessage(
        author=_FakeAuthor(id=42),
        content="<@111> hi",
        mentions=[other_bot],
    )
    assert normalize_message(msg, bot_user_id=bot_user_id) is None


def test_normalize_returns_none_when_outside_bound_guild():
    bot_user_id = 999
    msg = _FakeMessage(
        msg_id=1, channel_id=100, guild_id=8888,
        author=_FakeAuthor(id=42),
        content="<@999> hello",
        mentions=[_FakeAuthor(id=bot_user_id, bot=True)],
    )
    assert normalize_message(msg, bot_user_id=bot_user_id, bound_guild_id=1000) is None


def test_normalize_passes_when_in_bound_guild():
    bot_user_id = 999
    msg = _FakeMessage(
        msg_id=1, channel_id=100, guild_id=1000,
        author=_FakeAuthor(id=42),
        content="<@999> hello",
        mentions=[_FakeAuthor(id=bot_user_id, bot=True)],
    )
    evt = normalize_message(msg, bot_user_id=bot_user_id, bound_guild_id=1000)
    assert evt is not None
