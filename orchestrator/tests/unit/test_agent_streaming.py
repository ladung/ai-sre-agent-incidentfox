from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest
import respx


from incidentfox_orchestrator.clients import AgentApiClient


def _sse_chunks(events: list[dict]) -> bytes:
    out = b""
    for e in events:
        out += b"data: " + json.dumps(e).encode() + b"\n\n"
    return out


@pytest.mark.asyncio
@respx.mock
async def test_stream_agent_yields_events_in_order():
    sse = _sse_chunks(
        [{"type": "tool_use", "name": "kubectl"}, {"type": "complete", "result": "done"}]
    )
    respx.post("http://orch:8000/api/v1/agents/dispatch-stream").mock(
        return_value=httpx.Response(
            200, content=sse, headers={"content-type": "text/event-stream"}
        )
    )
    client = AgentApiClient(base_url="http://orch:8000")
    events = []
    async for evt in client.stream_agent(
        team_token="tok", agent_name="sre", message="hi", session_id="lark-x"
    ):
        events.append(evt)
    assert [e["type"] for e in events] == ["tool_use", "complete"]


@pytest.mark.asyncio
@respx.mock
async def test_stream_agent_skips_keepalives_and_blank_lines():
    sse = b": ping\n\ndata: {\"type\":\"complete\"}\n\n"
    respx.post("http://orch:8000/api/v1/agents/dispatch-stream").mock(
        return_value=httpx.Response(
            200, content=sse, headers={"content-type": "text/event-stream"}
        )
    )
    client = AgentApiClient(base_url="http://orch:8000")
    events = [evt async for evt in client.stream_agent(
        team_token="t", agent_name="sre", message="hi", session_id="s"
    )]
    assert events == [{"type": "complete"}]
