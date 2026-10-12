"""Signed session tokens (HMAC-SHA256), stdlib only. Swapped for the real identity provider's
tokens later; the rest of the API only sees `get_identity`."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign(payload: dict, secret: str, ttl_seconds: int) -> str:
    body = _b64(json.dumps({**payload, "exp": int(time.time()) + ttl_seconds}).encode())
    sig = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify(token: str, secret: str) -> dict | None:
    try:
        body, sig = token.split(".", 1)
        expected = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_unb64(body))
        return payload if payload.get("exp", 0) >= time.time() else None
    except (ValueError, TypeError):
        return None
