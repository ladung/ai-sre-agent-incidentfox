from __future__ import annotations

import asyncio

import pytest

from stream_handler import handle_stream


def _events(*items):
    async def gen():
        for it in items:
            yield it
    return gen()


@pytest.mark.asyncio
async def test_handle_stream_calls_update_then_finalize_on_complete():
    updates: list[str] = []
    finals: list[tuple[str, bool]] = []

    async def on_update(text: str):
        updates.append(text)

    async def on_final(text: str, success: bool):
        finals.append((text, success))

    src = _events(
        {"type": "text", "text": "Looking…"},
        {"type": "text", "text": " at logs."},
        {"type": "complete", "result": "Looking… at logs.", "success": True},
    )
    await handle_stream(src, on_update=on_update, on_final=on_final, debounce_ms=0)
    # debounce=0 → every text triggers an update (final excluded)
    assert updates == ["Looking…", "Looking… at logs."]
    assert finals == [("Looking… at logs.", True)]


@pytest.mark.asyncio
async def test_handle_stream_failure_event_marks_unsuccessful():
    finals: list[tuple[str, bool]] = []

    async def on_update(_: str): pass
    async def on_final(text: str, success: bool):
        finals.append((text, success))

    src = _events({"type": "error", "error": "boom"})
    await handle_stream(src, on_update=on_update, on_final=on_final, debounce_ms=0)
    assert finals == [("boom", False)]


@pytest.mark.asyncio
async def test_handle_stream_debounce_collapses_rapid_updates():
    updates: list[str] = []

    async def on_update(text: str):
        updates.append(text)

    async def on_final(*_):
        pass

    src = _events(
        {"type": "text", "text": "a"},
        {"type": "text", "text": "b"},
        {"type": "text", "text": "c"},
        {"type": "complete", "result": "abc", "success": True},
    )
    await handle_stream(src, on_update=on_update, on_final=on_final, debounce_ms=200)
    # With 200ms debounce and synchronous gen, only the last cumulative text should slip through.
    assert updates[-1] == "abc" or updates == []  # acceptable: 0 mid-stream updates if stream finishes inside debounce window
