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
    last_flush_ms = None
    last_flushed_text = ""  # Track the last flushed content to avoid duplicates
    final_called = False

    def now_ms() -> int:
        return int(time.monotonic() * 1000)

    async for evt in events:
        etype = evt.get("type")
        if etype == "text":
            buffer += evt.get("text", "")
            current_ms = now_ms()
            # On first event, only flush if debounce_ms is 0
            # Otherwise, only flush if debounce_ms has passed since last flush
            should_flush = last_flush_ms is None and debounce_ms == 0
            if should_flush or (last_flush_ms is not None and current_ms - last_flush_ms >= debounce_ms):
                await on_update(buffer)
                last_flushed_text = buffer
                last_flush_ms = current_ms
        elif etype == "complete":
            final_called = True
            # Flush any pending buffer before final, but only if it's different from last flush
            if buffer and buffer != last_flushed_text and (last_flush_ms is None or (now_ms() - last_flush_ms >= debounce_ms)):
                await on_update(buffer)
            result = evt.get("result", buffer)
            await on_final(result, bool(evt.get("success", True)))
            return
        elif etype == "error":
            final_called = True
            await on_final(str(evt.get("error", "unknown error")), False)
            return

    if not final_called:
        await on_final(buffer, True)
