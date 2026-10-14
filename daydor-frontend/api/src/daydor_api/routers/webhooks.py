"""Inbound vendor webhooks (backend 0046, `daydor.webhooks`). No sign-in: the credential is the signature and the URL secret.

    POST /api/webhooks/{integration}/{token}     X-Signature: sha256=<hmac>      [X-Timestamp: <unix seconds>]   [X-Event-Id: <id>]

The signature is checked first (so a bad caller learns nothing about which tokens exist), then the event is stored once for the tenant that
owns the token. Replies are deliberately terse. With no secret configured for the integration the endpoint is closed (503)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from daydor import webhooks
from daydor.db.session import tenant_session

from ..errors import ApiError
from ..state import get_engine

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/{integration}/{token}")
async def receive(integration: str, token: str, request: Request):
    secret = webhooks.secret_for(integration)
    if secret is None:
        raise ApiError(503, "not_configured", "This webhook is not switched on.")
    body = await request.body()
    if len(body) > webhooks.MAX_BODY_BYTES:
        raise ApiError(413, "too_large", "That payload is too large.")
    if not webhooks.verify_signature(secret, body, request.headers.get("x-signature"), request.headers.get("x-timestamp")):
        raise ApiError(401, "invalid_signature", "The signature did not match.")
    try:
        payload = json.loads(body)
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        raise ApiError(422, "invalid_request", "The body must be a JSON object.")
    with tenant_session(get_engine(), "daydor_worker") as conn:
        row = conn.execute(text("SELECT * FROM app.receive_webhook(:t, :i, :e, CAST(:p AS jsonb))"),
                           {"t": webhooks.token_sha256(token), "i": integration,
                            "e": webhooks.external_id(payload, body, request.headers.get("x-event-id")), "p": body.decode()}).one()
    if row.outcome == "unknown":
        raise ApiError(404, "not_found", "Not found.")
    return JSONResponse({"status": row.outcome}, status_code=200 if row.outcome == "duplicate" else 202)
