from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Optional

import httpx


class OrchestratorError(Exception):
    pass


class OrchestratorClient:
    def __init__(
        self,
        *,
        base_url: str,
        team_token: str,
        agent_name: str = "sre",
        timeout: float = 600.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._team_token = team_token
        self._agent_name = agent_name
        self._http = httpx.AsyncClient(timeout=timeout)

    async def stream_agent(
        self,
        *,
        message: str,
        session_id: str,
        tenant_id: Optional[str] = None,
        team_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        body = {
            "agent_name": self._agent_name,
            "message": message,
            "session_id": session_id,
            "tenant_id": tenant_id,
            "team_id": team_id,
            "correlation_id": correlation_id,
        }
        headers = {
            "Authorization": f"Bearer {self._team_token}",
            "Accept": "text/event-stream",
        }
        async with self._http.stream(
            "POST",
            f"{self._base_url}/api/v1/agents/dispatch-stream",
            json=body,
            headers=headers,
        ) as resp:
            if resp.status_code >= 400:
                text = await resp.aread()
                raise OrchestratorError(f"status {resp.status_code}: {text[:200]!r}")
            async for line in resp.aiter_lines():
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                payload = line[len("data:"):].strip()
                if not payload:
                    continue
                try:
                    yield json.loads(payload)
                except json.JSONDecodeError:
                    continue

    async def aclose(self) -> None:
        await self._http.aclose()
