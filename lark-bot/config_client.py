from __future__ import annotations

from typing import Any

import httpx


class ConfigClientError(Exception):
    pass


class ConfigClient:
    def __init__(self, *, base_url: str, team_token: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {team_token}"},
        )

    async def fetch_effective(self) -> dict[str, Any]:
        try:
            resp = await self._http.get("/api/v1/config/me/effective")
        except httpx.HTTPError as e:
            raise ConfigClientError(f"transport error: {e}") from e
        if resp.status_code != 200:
            raise ConfigClientError(f"status {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    async def aclose(self) -> None:
        await self._http.aclose()
