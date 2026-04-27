from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Protocol

from fastapi import FastAPI, Request

from event_router import EventValidationError, normalize_event


class _Handler(Protocol):
    async def handle(self, evt) -> None: ...


def build_app(*, handler: _Handler, dedup_window: int = 1024) -> FastAPI:
    app = FastAPI(title="incidentfox-lark-bot")
    seen: deque[str] = deque(maxlen=dedup_window)
    seen_set: set[str] = set()
    lock = asyncio.Lock()

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/internal/lark/event")
    async def event(request: Request) -> dict[str, Any]:
        payload = await request.json()
        try:
            evt = normalize_event(payload)
        except EventValidationError:
            return {"ok": False, "reason": "unsupported_event"}

        if evt.event_type == "url_verification":
            return {"challenge": evt.url_verification_challenge}

        if evt.event_id:
            async with lock:
                if evt.event_id in seen_set:
                    return {"ok": True, "deduped": True}
                if len(seen) == seen.maxlen:
                    seen_set.discard(seen[0])
                seen.append(evt.event_id)
                seen_set.add(evt.event_id)

        # Schedule handler in background — Lark expects <3s response.
        asyncio.create_task(handler.handle(evt))
        return {"ok": True}

    return app
