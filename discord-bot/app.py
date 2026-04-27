from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from dataclasses import dataclass

from dotenv import load_dotenv

from feedback_handler import FeedbackHandler
from gateway_client import DiscordGatewayClient
from healthz import run_healthz
from investigation_handler import InvestigationHandler
from orchestrator_client import OrchestratorClient
from state import ConversationState

logger = logging.getLogger("discord-bot")


class SettingsError(Exception):
    pass


@dataclass
class Settings:
    bot_token: str
    app_id: str
    guild_id: int
    orchestrator_url: str
    config_service_url: str
    team_token: str
    org_id: str
    team_id: str
    internal_http_port: int


def _require(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        raise SettingsError(f"missing required env: {name}")
    return v


def build_settings() -> Settings:
    guild_id_raw = _require("DISCORD_GUILD_ID")
    try:
        guild_id = int(guild_id_raw)
    except ValueError as e:
        raise SettingsError(f"DISCORD_GUILD_ID must be an integer, got: {guild_id_raw!r}") from e

    return Settings(
        bot_token=_require("DISCORD_BOT_TOKEN"),
        app_id=_require("DISCORD_APP_ID"),
        guild_id=guild_id,
        orchestrator_url=os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8070"),
        config_service_url=os.environ.get("CONFIG_SERVICE_URL", "http://config-service:8080"),
        team_token=_require("INCIDENTFOX_TEAM_TOKEN"),
        org_id=_require("INCIDENTFOX_ORG_ID"),
        team_id=_require("INCIDENTFOX_TEAM_ID"),
        internal_http_port=int(os.environ.get("INTERNAL_HTTP_PORT", "8080")),
    )


async def _serve(s: Settings) -> None:
    state = ConversationState()
    orchestrator = OrchestratorClient(base_url=s.orchestrator_url, team_token=s.team_token)
    feedback = FeedbackHandler(
        config_service_url=s.config_service_url,
        team_token=s.team_token,
        state=state,
    )

    # InvestigationHandler is constructed with a placeholder discord adapter; the real adapter
    # is injected by gateway_client at on_message time (since the discord.Client must be
    # constructed before the adapter can hold a reference to it).
    class _DiscordPlaceholder:
        async def send_embed(self, **kw): raise RuntimeError("adapter not yet wired")
        async def edit_embed(self, **kw): raise RuntimeError("adapter not yet wired")
        async def add_reaction(self, **kw): raise RuntimeError("adapter not yet wired")

    investigation = InvestigationHandler(
        discord=_DiscordPlaceholder(),
        orchestrator=orchestrator,
        org_id=s.org_id,
        team_id=s.team_id,
        state=state,
    )

    gateway = DiscordGatewayClient(
        bot_token=s.bot_token,
        guild_id=s.guild_id,
        investigation_handler=investigation,
        feedback_handler=feedback,
    )

    stop = asyncio.Event()

    def _signal_handler(*_: object) -> None:
        stop.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass

    tasks = [
        asyncio.create_task(gateway.run(), name="gateway"),
        asyncio.create_task(run_healthz(s.internal_http_port), name="healthz"),
        asyncio.create_task(stop.wait(), name="stop"),
    ]

    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()

    await orchestrator.aclose()
    await feedback.aclose()


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = build_settings()
    print(json.dumps({"service": "discord-bot", "event": "starting", "guild_id": settings.guild_id}))
    asyncio.run(_serve(settings))


if __name__ == "__main__":
    main()
