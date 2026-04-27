from __future__ import annotations

import base64
import hashlib
import json
import os

import pytest
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from incidentfox_orchestrator.webhooks.signatures import (
    SignatureVerificationError,
    decrypt_lark_payload,
    verify_lark_signature,
)


def _sign(timestamp: str, nonce: str, encrypt_key: str, body: str) -> str:
    return hashlib.sha256((timestamp + nonce + encrypt_key + body).encode()).hexdigest()


def test_verify_lark_signature_passes_with_correct_inputs():
    body = '{"a":1}'
    sig = _sign("1700", "n1", "ek", body)
    verify_lark_signature(timestamp="1700", nonce="n1", encrypt_key="ek", body=body, signature=sig)


def test_verify_lark_signature_fails_with_wrong_signature():
    with pytest.raises(SignatureVerificationError):
        verify_lark_signature(timestamp="1700", nonce="n1", encrypt_key="ek", body="{}", signature="bad")


def _encrypt_lark(plain: str, encrypt_key: str) -> str:
    key = hashlib.sha256(encrypt_key.encode()).digest()
    iv = os.urandom(16)
    cipher = AES.new(key, AES.MODE_CBC, iv=iv)
    ct = cipher.encrypt(pad(plain.encode(), AES.block_size))
    return base64.b64encode(iv + ct).decode()


def test_decrypt_lark_payload_roundtrip():
    inner = json.dumps({"hello": "world"})
    encrypted = _encrypt_lark(inner, "test-key")
    out = decrypt_lark_payload(encrypted=encrypted, encrypt_key="test-key")
    assert out == {"hello": "world"}


def test_decrypt_lark_payload_wrong_key_raises():
    inner = json.dumps({"x": 1})
    encrypted = _encrypt_lark(inner, "real-key")
    with pytest.raises(SignatureVerificationError):
        decrypt_lark_payload(encrypted=encrypted, encrypt_key="WRONG-KEY")
