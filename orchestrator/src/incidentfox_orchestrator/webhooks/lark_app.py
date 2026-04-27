"""
Lark (Feishu) webhook handler for IncidentFox orchestrator.

Receives encrypted Lark platform events, verifies signatures, decrypts
payloads, and forwards normalized events to the lark-bot internal endpoint.

Supported event types:
- url_verification: Lark platform verification handshake
- im.message.receive_v1 (and others): forwarded to lark-bot
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Request

from incidentfox_orchestrator.webhooks.signatures import (
    SignatureVerificationError,
    decrypt_lark_payload,
    verify_lark_signature,
)


def _log(event: str, **fields: Any) -> None:
    try:
        print(json.dumps({"service": "orchestrator", "component": "lark", "event": event, **fields}, default=str))
    except Exception:
        print(f"{event} {fields}")


def build_lark_router() -> APIRouter:
    """Build a router with /webhooks/lark registered (no prefix on this router itself)."""
    router = APIRouter()

    @router.post("/webhooks/lark")
    async def lark_webhook(
        request: Request,
        x_lark_signature: str = Header(default=""),
        x_lark_request_timestamp: str = Header(default=""),
        x_lark_request_nonce: str = Header(default=""),
    ):
        """
        Handle Lark platform webhook events.

        Lark sends encrypted, signed payloads. This handler:
        1. Verifies HMAC-SHA256 signature (when encrypt_key is configured)
        2. Decrypts AES-CBC payload
        3. Validates the verification token
        4. Handles url_verification challenge (returns echo)
        5. Forwards all other events to lark-bot's /internal/lark/event
        """
        verification_token = os.environ.get("LARK_VERIFICATION_TOKEN", "")
        encrypt_key = os.environ.get("LARK_ENCRYPT_KEY", "")
        lark_bot_url = os.environ.get("LARK_BOT_INTERNAL_URL", "")

        if not verification_token or not lark_bot_url:
            _log("lark_webhook_not_configured")
            raise HTTPException(status_code=503, detail="lark webhook not configured")

        raw_body = (await request.body()).decode("utf-8")

        # Signature verification is required when encrypt_key is configured.
        if encrypt_key:
            try:
                verify_lark_signature(
                    timestamp=x_lark_request_timestamp,
                    nonce=x_lark_request_nonce,
                    encrypt_key=encrypt_key,
                    body=raw_body,
                    signature=x_lark_signature,
                )
            except SignatureVerificationError as e:
                _log("lark_signature_verify_failed", reason=str(e))
                raise HTTPException(status_code=401, detail="signature_invalid")

        try:
            outer = json.loads(raw_body)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="invalid_json")

        if "encrypt" in outer:
            if not encrypt_key:
                _log("lark_got_encrypted_payload_without_key")
                raise HTTPException(status_code=401, detail="encrypted_but_no_key")
            try:
                payload = decrypt_lark_payload(encrypted=outer["encrypt"], encrypt_key=encrypt_key)
            except SignatureVerificationError:
                raise HTTPException(status_code=401, detail="decrypt_failed")
        else:
            payload = outer

        # Token appears in both url_verification and event payloads.
        if payload.get("token") and payload["token"] != verification_token:
            _log("lark_token_mismatch")
            raise HTTPException(status_code=401, detail="token_mismatch")

        # Lark url_verification handshake — echo the challenge back.
        if payload.get("type") == "url_verification":
            _log("lark_url_verification", challenge=payload.get("challenge", ""))
            return {"challenge": payload.get("challenge", "")}

        # Forward all other events to lark-bot.
        _log(
            "lark_event_forwarding",
            event_type=payload.get("header", {}).get("event_type", "unknown"),
        )
        async with httpx.AsyncClient(timeout=10.0) as http:
            try:
                r = await http.post(
                    f"{lark_bot_url.rstrip('/')}/internal/lark/event",
                    json=payload,
                )
                r.raise_for_status()
            except httpx.HTTPError as e:
                _log("lark_forward_failed", error=str(e))
                raise HTTPException(status_code=502, detail="lark_bot_unreachable")

        return {"ok": True}

    return router
