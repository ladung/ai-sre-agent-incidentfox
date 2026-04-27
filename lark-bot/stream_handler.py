from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any, Awaitable, Callable

OnUpdate = Callable[[str], Awaitable[None]]
OnFinal = Callable[[str, bool], Awaitable[None]]


async def handle_stream(
    events: AsyncIterator[dict[str, Any]],
    *,
    on_update: OnUpdate,
    on_final: OnFinal,
    debounce_ms: int = 250,
) -> None:
    """Consume agent SSE events, drive on_update (debounced) and on_final."""
    buffer = ""
    last_sent = ""  # Track what we've already sent to detect pending updates
    final_called = False

    def now_ms() -> int:
        return int(time.monotonic() * 1000)

    last_flush_ms = now_ms()

    async for evt in events:
        etype = evt.get("type")
        if etype == "text":
            buffer += evt.get("text", "")
            if now_ms() - last_flush_ms >= debounce_ms:
                await on_update(buffer)
                last_sent = buffer
                last_flush_ms = now_ms()
        elif etype == "complete":
            final_called = True
            # Emit pending buffer before finalize if it hasn't been sent yet
            if buffer != last_sent:
                await on_update(buffer)
            result = evt.get("result", buffer)
            await on_final(result, bool(evt.get("success", True)))
            return
        elif etype == "error":
            final_called = True
            await on_final(str(evt.get("error", "unknown error")), False)
            return
        # other event types (tool_use, etc.) are ignored in Phase 1

    if not final_called:
        # Stream ended without explicit complete — treat buffer as final success.
        await on_final(buffer, True)
