from __future__ import annotations

import httpx
import pytest
import respx

from config_client import ConfigClient, ConfigClientError


@respx.mock
async def test_fetch_effective_config_success():
    respx.get("http://config-service:8080/api/v1/config/me/effective").mock(
        return_value=httpx.Response(200, json={"lark": {"x": 1}, "_meta": {"team_id": "t1"}})
    )
    client = ConfigClient(base_url="http://config-service:8080", team_token="tok")
    cfg = await client.fetch_effective()
    assert cfg["lark"]["x"] == 1
    await client.aclose()


@respx.mock
async def test_fetch_effective_config_401_raises():
    respx.get("http://config-service:8080/api/v1/config/me/effective").mock(
        return_value=httpx.Response(401, json={"error": "unauthorized"})
    )
    client = ConfigClient(base_url="http://config-service:8080", team_token="bad")
    with pytest.raises(ConfigClientError):
        await client.fetch_effective()
    await client.aclose()
