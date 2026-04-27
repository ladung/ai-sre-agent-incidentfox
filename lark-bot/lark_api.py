from __future__ import annotations

import json
import time
from typing import Any, Optional

import httpx


class LarkApiError(Exception):
    def __init__(self, code: int, msg: str) -> None:
        self.code = code
        self.msg = msg
        super().__init__(f"Lark API error {code}: {msg}")


class LarkApi:
    """Minimal Lark Open Platform API client (Phase 1).

    Manages tenant_access_token caching and exposes two operations:
      - post_card: send a new interactive card message to a chat (optionally as a thread reply).
      - patch_card: update an existing card-typed message in place.
    """

    def __init__(
        self,
        *,
        api_base: str,
        app_id: str,
        app_secret: str,
        timeout: float = 30.0,
    ) -> None:
        self._api_base = api_base.rstrip("/")
        self._app_id = app_id
        self._app_secret = app_secret
        self._http = httpx.AsyncClient(timeout=timeout)
        self._token: str = ""
        self._token_expires_at: float = 0.0

    async def _ensure_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires_at - 300:
            return self._token
        resp = await self._http.post(
            f"{self._api_base}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self._app_id, "app_secret": self._app_secret},
        )
        body = resp.json()
        if body.get("code") != 0:
            raise LarkApiError(body.get("code", -1), body.get("msg", "token fetch failed"))
        self._token = body["tenant_access_token"]
        self._token_expires_at = time.monotonic() + int(body.get("expire", 7200))
        return self._token

    async def _auth_headers(self) -> dict[str, str]:
        tok = await self._ensure_token()
        return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

    async def post_card(self, *, chat_id: str, root_id: Optional[str], card: dict[str, Any]) -> str:
        body: dict[str, Any] = {
            "receive_id": chat_id,
            "msg_type": "interactive",
            "content": json.dumps(card),
        }
        if root_id:
            body["reply_in_thread"] = True
            body["root_id"] = root_id
        params = {"receive_id_type": "chat_id"}
        resp = await self._http.post(
            f"{self._api_base}/open-apis/im/v1/messages",
            params=params,
            json=body,
            headers=await self._auth_headers(),
        )
        data = resp.json()
        if data.get("code") != 0:
            raise LarkApiError(data.get("code", -1), data.get("msg", "post failed"))
        return data["data"]["message_id"]

    async def patch_card(self, *, message_id: str, card: dict[str, Any]) -> None:
        body = {"content": json.dumps(card)}
        resp = await self._http.patch(
            f"{self._api_base}/open-apis/im/v1/messages/{message_id}",
            json=body,
            headers=await self._auth_headers(),
        )
        data = resp.json()
        if data.get("code") != 0:
            raise LarkApiError(data.get("code", -1), data.get("msg", "patch failed"))

    async def aclose(self) -> None:
        await self._http.aclose()
