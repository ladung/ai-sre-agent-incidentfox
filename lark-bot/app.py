from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from dataclasses import dataclass
from typing import Optional

import uvicorn
from dotenv import load_dotenv

from http_server import build_app
from investigation_handler import InvestigationHandler
from lark_api import LarkApi
from orchestrator_client import OrchestratorClient

logger = logging.getLogger("lark-bot")


class SettingsError(Exception):
    pass


@dataclass
class Settings:
    app_id: str
    app_secret: str
    tenant_key: str
    transport_mode: str
    api_base: str
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
    if os.environ.get("LARK_OAUTH_ENABLED", "false").lower() == "true":
        raise SettingsError("LARK_OAUTH_ENABLED=true is not supported in Phase 1 (single-tenant only)")
    transport = os.environ.get("LARK_TRANSPORT_MODE", "long_connection").lower()
    if transport not in {"long_connection", "webhook", "hybrid"}:
        raise SettingsError(f"invalid LARK_TRANSPORT_MODE: {transport!r}")
    return Settings(
        app_id=_require("LARK_APP_ID"),
        app_secret=_require("LARK_APP_SECRET"),
        tenant_key=_require("LARK_TENANT_KEY"),
        transport_mode=transport,
        api_base=os.environ.get("LARK_API_BASE", "https://open.larksuite.com"),
        orchestrator_url=os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8000"),
        config_service_url=os.environ.get("CONFIG_SERVICE_URL", "http://config-service:8080"),
        team_token=_require("INCIDENTFOX_TEAM_TOKEN"),
        org_id=_require("INCIDENTFOX_ORG_ID"),
        team_id=_require("INCIDENTFOX_TEAM_ID"),
        internal_http_port=int(os.environ.get("INTERNAL_HTTP_PORT", "8080")),
    )


async def _serve(s: Settings) -> None:
    lark_api = LarkApi(api_base=s.api_base, app_id=s.app_id, app_secret=s.app_secret)
    orchestrator = OrchestratorClient(base_url=s.orchestrator_url, team_token=s.team_token)
    handler = InvestigationHandler(
        lark_api=lark_api,
        orchestrator=orchestrator,
        org_id=s.org_id,
        team_id=s.team_id,
    )

    tasks: list[asyncio.Task] = []

    # HTTP server is always started — needed for K8s /healthz probes even in
    # long_connection mode. The /internal/lark/event endpoint is also harmless
    # to expose: it only acts on events forwarded by orchestrator's webhook
    # endpoint, and the lark-bot Service is ClusterIP-only.
    app = build_app(handler=handler)
    config = uvicorn.Config(
        app, host="0.0.0.0", port=s.internal_http_port,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )
    server = uvicorn.Server(config)
    tasks.append(asyncio.create_task(server.serve(), name="http_server"))

    if s.transport_mode in {"long_connection", "hybrid"}:
        from ws_client import LarkWsClient
        ws = LarkWsClient(
            app_id=s.app_id, app_secret=s.app_secret,
            api_base=s.api_base, handler=handler,
        )
        tasks.append(asyncio.create_task(ws.run(), name="ws_client"))

    if not tasks:
        raise SettingsError(f"no transports active for mode {s.transport_mode!r}")

    stop = asyncio.Event()

    def _signal_handler(*_: object) -> None:
        stop.set()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass

    done, pending = await asyncio.wait(
        [*tasks, asyncio.create_task(stop.wait(), name="stop")],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for t in pending:
        t.cancel()

    await lark_api.aclose()
    await orchestrator.aclose()


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = build_settings()
    print(json.dumps({"service": "lark-bot", "event": "starting", "transport": settings.transport_mode}))
    asyncio.run(_serve(settings))


if __name__ == "__main__":
    main()
