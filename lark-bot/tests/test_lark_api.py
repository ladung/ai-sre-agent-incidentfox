from __future__ import annotations

import httpx
import pytest
import respx

from lark_api import LarkApi, LarkApiError


@respx.mock
async def test_post_card_returns_message_id():
    respx.post("https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal").mock(
        return_value=httpx.Response(200, json={"code": 0, "tenant_access_token": "t_abc", "expire": 7200})
    )
    respx.post("https://open.larksuite.com/open-apis/im/v1/messages").mock(
        return_value=httpx.Response(200, json={"code": 0, "data": {"message_id": "om_xyz"}})
    )
    api = LarkApi(api_base="https://open.larksuite.com", app_id="cli_x", app_secret="s")
    mid = await api.post_card(chat_id="oc_1", root_id=None, card={"schema": "2.0"})
    assert mid == "om_xyz"
    await api.aclose()


@respx.mock
async def test_post_card_with_root_id_includes_reply_in_content():
    respx.post("https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal").mock(
        return_value=httpx.Response(200, json={"code": 0, "tenant_access_token": "t", "expire": 7200})
    )
    route = respx.post("https://open.larksuite.com/open-apis/im/v1/messages").mock(
        return_value=httpx.Response(200, json={"code": 0, "data": {"message_id": "om_1"}})
    )
    api = LarkApi(api_base="https://open.larksuite.com", app_id="x", app_secret="s")
    await api.post_card(chat_id="oc_1", root_id="om_root", card={"schema": "2.0"})
    body = route.calls.last.request.read().decode()
    assert "om_root" in body
    await api.aclose()


@respx.mock
async def test_patch_card_calls_correct_endpoint():
    respx.post("https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal").mock(
        return_value=httpx.Response(200, json={"code": 0, "tenant_access_token": "t", "expire": 7200})
    )
    route = respx.patch("https://open.larksuite.com/open-apis/im/v1/messages/om_1").mock(
        return_value=httpx.Response(200, json={"code": 0})
    )
    api = LarkApi(api_base="https://open.larksuite.com", app_id="x", app_secret="s")
    await api.patch_card(message_id="om_1", card={"schema": "2.0"})
    assert route.called
    await api.aclose()


@respx.mock
async def test_lark_error_code_raises():
    respx.post("https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal").mock(
        return_value=httpx.Response(200, json={"code": 0, "tenant_access_token": "t", "expire": 7200})
    )
    respx.post("https://open.larksuite.com/open-apis/im/v1/messages").mock(
        return_value=httpx.Response(200, json={"code": 99991663, "msg": "rate limited"})
    )
    api = LarkApi(api_base="https://open.larksuite.com", app_id="x", app_secret="s")
    with pytest.raises(LarkApiError):
        await api.post_card(chat_id="c", root_id=None, card={})
    await api.aclose()
