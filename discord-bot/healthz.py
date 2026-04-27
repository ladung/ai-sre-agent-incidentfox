from __future__ import annotations

import asyncio

from aiohttp import web


def build_healthz_app() -> web.Application:
    app = web.Application()

    async def healthz(request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    app.router.add_get("/healthz", healthz)
    return app


async def run_healthz(port: int) -> None:
    """Run the healthz server on the given port. Blocks until cancelled."""
    app = build_healthz_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
