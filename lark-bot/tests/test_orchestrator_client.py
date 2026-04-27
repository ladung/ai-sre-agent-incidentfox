from __future__ import annotations

import httpx
import pytest
import respx

from orchestrator_client import OrchestratorClient, OrchestratorError


@respx.mock
async def test_stream_yields_events():
    sse = b'data: {"type":"tool_use","name":"kubectl"}\n\ndata: {"type":"complete"}\n\n'
    respx.post("http://orch:8000/api/v1/agents/dispatch-stream").mock(
        return_value=httpx.Response(200, content=sse, headers={"content-type": "text/event-stream"})
    )
    client = OrchestratorClient(base_url="http://orch:8000", team_token="tok")
    events = [e async for e in client.stream_agent(message="hi", session_id="s")]
    assert [e["type"] for e in events] == ["tool_use", "complete"]
    await client.aclose()


@respx.mock
async def test_stream_raises_on_4xx():
    respx.post("http://orch:8000/api/v1/agents/dispatch-stream").mock(
        return_value=httpx.Response(401, json={"error": "unauthorized"})
    )
    client = OrchestratorClient(base_url="http://orch:8000", team_token="bad")
    with pytest.raises(OrchestratorError):
        async for _ in client.stream_agent(message="hi", session_id="s"):
            pass
    await client.aclose()
