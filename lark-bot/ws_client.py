from __future__ import annotations

import asyncio
import threading
from typing import Any, Protocol

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

from event_router import EventValidationError, normalize_event


class _Handler(Protocol):
    async def handle(self, evt) -> None: ...


def _decode_oapi_event(oapi_event: Any) -> dict[str, Any]:
    """Reshape a lark-oapi P2ImMessageReceiveV1 (or similar) into the dict shape event_router expects."""
    header = oapi_event.header
    msg = oapi_event.event.message
    sender = oapi_event.event.sender
    return {
        "schema": "2.0",
        "header": {
            "event_id": getattr(header, "event_id", "") or "",
            "event_type": getattr(header, "event_type", "") or "",
            "tenant_key": getattr(header, "tenant_key", "") or "",
            "create_time": getattr(header, "create_time", "") or "",
        },
        "event": {
            "sender": {
                "sender_id": {
                    "open_id": getattr(getattr(sender, "sender_id", None), "open_id", "") or "",
                },
            },
            "message": {
                "message_id": getattr(msg, "message_id", "") or "",
                "chat_id": getattr(msg, "chat_id", "") or "",
                "chat_type": getattr(msg, "chat_type", "") or "",
                "message_type": getattr(msg, "message_type", "") or "",
                "content": getattr(msg, "content", "") or "",
                "root_id": getattr(msg, "root_id", None),
                "mentions": getattr(msg, "mentions", None) or [],
            },
        },
    }


class LarkWsClient:
    """Long-connection WebSocket client using lark-oapi SDK.

    The lark-oapi ws.Client is created lazily in run() rather than __init__
    so that construction does not require network access or valid credentials.
    This allows the smoke-test constructor check to work without Lark tokens.
    """

    def __init__(
        self,
        *,
        app_id: str,
        app_secret: str,
        api_base: str,
        handler: _Handler,
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        # lark.LARK_DOMAIN = "https://open.larksuite.com"
        # lark.FEISHU_DOMAIN = "https://open.feishu.cn"
        self._domain = lark.LARK_DOMAIN if "larksuite" in api_base else lark.FEISHU_DOMAIN
        self._handler = handler
        self._loop: asyncio.AbstractEventLoop | None = None

    def _build_client(self) -> lark.ws.Client:
        """Build the lark-oapi ws.Client with an IM message dispatcher."""

        def on_message(oapi_evt: P2ImMessageReceiveV1) -> None:
            try:
                payload = _decode_oapi_event(oapi_evt)
                norm = normalize_event(payload)
            except EventValidationError:
                return
            assert self._loop is not None
            asyncio.run_coroutine_threadsafe(self._handler.handle(norm), self._loop)

        dispatcher = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(on_message)
            .build()
        )
        return lark.ws.Client(
            self._app_id,
            self._app_secret,
            event_handler=dispatcher,
            domain=self._domain,
        )

    async def run(self) -> None:
        """Run the long-connection client until cancelled.

        Captures the asyncio event loop on the main thread, then runs lark-oapi's
        blocking ws.Client.start() inside a dedicated thread that owns its own
        fresh event loop. The dedicated loop is required because Client.start()
        internally calls loop.run_until_complete(), which conflicts with the
        already-running main loop if asyncio.to_thread is used (the worker
        thread would otherwise inherit / look up the main loop).

        The on_message callback runs on this dedicated thread and bridges back
        to the main loop via asyncio.run_coroutine_threadsafe.
        """
        self._loop = asyncio.get_running_loop()
        client = self._build_client()
        done = threading.Event()
        error: list[BaseException] = []

        def _thread_main() -> None:
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                client.start()
            except BaseException as e:  # noqa: BLE001 — surface back to caller
                error.append(e)
            finally:
                try:
                    new_loop.close()
                except Exception:
                    pass
                done.set()

        thread = threading.Thread(target=_thread_main, name="lark-ws", daemon=True)
        thread.start()

        try:
            while not done.is_set():
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            # lark-oapi's Client doesn't expose a clean stop API — daemon=True
            # ensures the thread won't block process exit.
            raise

        if error:
            raise error[0]
