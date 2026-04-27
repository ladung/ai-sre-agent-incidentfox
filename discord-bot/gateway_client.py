from __future__ import annotations

import json
from typing import Any, Protocol

import discord

from event_router import normalize_message
from feedback_handler import ReactionType


def _log(event: str, **fields: Any) -> None:
    try:
        print(json.dumps({"service": "discord-bot", "component": "gateway", "event": event, **fields}, default=str))
    except Exception:
        print(f"{event} {fields}")


class _InvestigationHandler(Protocol):
    async def handle(self, evt) -> None: ...

    @property
    def state(self): ...


class _FeedbackHandler(Protocol):
    async def handle_reaction(self, *, reaction: ReactionType, bot_message_id: int, user_id: int) -> None: ...


class ChannelAwareDiscordAdapter:
    """Adapter that retains discord.Message objects so edit/react are possible without a channel hint.

    Satisfies the _Discord Protocol expected by InvestigationHandler.
    """

    def __init__(self, client: "discord.Client") -> None:
        self._client = client
        self._messages: dict[int, "discord.Message"] = {}

    async def send_embed(self, *, channel_id: int, reply_to_message_id: int, embed: dict) -> int:
        channel = self._client.get_channel(channel_id) or await self._client.fetch_channel(channel_id)
        ref_msg = await channel.fetch_message(reply_to_message_id)
        sent = await ref_msg.reply(embed=discord.Embed.from_dict(embed))
        self._messages[sent.id] = sent
        return sent.id

    async def edit_embed(self, *, message_id: int, embed: dict) -> None:
        msg = self._messages.get(message_id)
        if msg is None:
            return
        await msg.edit(embed=discord.Embed.from_dict(embed))

    async def add_reaction(self, *, message_id: int, emoji: str) -> None:
        msg = self._messages.get(message_id)
        if msg is None:
            return
        await msg.add_reaction(emoji)


class DiscordGatewayClient:
    """discord.py Client wired to investigation_handler + feedback_handler."""

    def __init__(
        self,
        *,
        bot_token: str,
        guild_id: int,
        investigation_handler: _InvestigationHandler,
        feedback_handler: _FeedbackHandler,
    ) -> None:
        self._token = bot_token
        self._guild_id = guild_id
        self._investigation = investigation_handler
        self._feedback = feedback_handler
        self._client = discord.Client(intents=self._intents())
        self._adapter = ChannelAwareDiscordAdapter(self._client)
        self._register_handlers()

    def _intents(self) -> discord.Intents:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guild_messages = True
        intents.guild_reactions = True
        intents.guilds = True
        return intents

    def _register_handlers(self) -> None:
        @self._client.event
        async def on_ready():
            _log("gateway_ready", bot_user_id=self._client.user.id)

        @self._client.event
        async def on_message(message: discord.Message):
            try:
                evt = normalize_message(
                    message,
                    bot_user_id=self._client.user.id,
                    bound_guild_id=self._guild_id,
                )
                if evt is None:
                    return
                # Inject the adapter into the investigation handler. Investigation_handler
                # was constructed with a placeholder; we inject the real one here so edits
                # and reactions go through this client's adapter.
                self._investigation._discord = self._adapter  # type: ignore[attr-defined]
                await self._investigation.handle(evt)
            except Exception as e:
                _log("on_message_error", error=str(e))

        @self._client.event
        async def on_reaction_add(reaction: discord.Reaction, user: discord.User):
            try:
                # Ignore bot's own reactions
                if user.bot or user.id == self._client.user.id:
                    return
                # Only act on reactions on the bot's own messages
                if reaction.message.author.id != self._client.user.id:
                    return
                rtype = _emoji_to_reaction_type(str(reaction.emoji))
                if rtype is None:
                    return
                await self._feedback.handle_reaction(
                    reaction=rtype,
                    bot_message_id=reaction.message.id,
                    user_id=user.id,
                )
            except Exception as e:
                _log("on_reaction_add_error", error=str(e))

    async def run(self) -> None:
        await self._client.start(self._token)


def _emoji_to_reaction_type(emoji: str):
    """Map a Discord emoji string to a ReactionType (or None)."""
    if emoji == "👍":
        return ReactionType.THUMBS_UP
    if emoji == "👎":
        return ReactionType.THUMBS_DOWN
    return None
