"""The webhook inbox (migration 0046).

A vendor posts an event to a per-tenant secret URL. The API verifies the signature (`verify_signature`) and calls `app.receive_webhook`,
which stores the event once (idempotent on the vendor's event id) and enqueues `webhook.received`. `handle_webhook_received` (queue
'webhooks', run as the `root-orchestrator` platform actor) hands the event to the handler registered for its integration:

    webhooks.register("bank", handle_bank_event)         # fn(conn, event) -> dict

No integration has a real vendor yet, so no handler is registered and every event ends `ignored`, kept, and replayable by ops once one
ships (`app.replay_webhook`). A handler that raises ends the event `failed` (kept, alerting, replayable); the job itself does not retry.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any, Callable

from sqlalchemy import Connection, text

from daydor.queue.worker import Job

QUEUE, KIND = "webhooks", "webhook.received"
MAX_BODY_BYTES = 256 * 1024
TOLERANCE_S = 300
HANDLERS: dict[str, Callable[[Connection, dict], dict | None]] = {}


def register(integration: str, fn: Callable[[Connection, dict], dict | None]) -> None:
    HANDLERS[integration] = fn


def token_sha256(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def secret_for(integration: str) -> str | None:
    """DAYDOR_WEBHOOK_SECRETS is a JSON object {integration: secret}. No secret, no webhooks: fail closed."""
    try:
        return json.loads(os.environ.get("DAYDOR_WEBHOOK_SECRETS") or "{}").get(integration) or None
    except ValueError:
        return None


def sign(secret: str, body: bytes, timestamp: str | None = None) -> str:
    msg = (timestamp.encode() + b"." + body) if timestamp else body
    return "sha256=" + hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def verify_signature(secret: str, body: bytes, signature: str | None, timestamp: str | None = None, *, now: float | None = None) -> bool:
    """HMAC-SHA256 over the body (or `timestamp.body` when a timestamp header is sent, which must be within five minutes: replay protection)."""
    if not signature:
        return False
    if timestamp is not None:
        try:
            if abs((now if now is not None else time.time()) - float(timestamp)) > TOLERANCE_S:
                return False
        except ValueError:
            return False
    return hmac.compare_digest(sign(secret, body, timestamp), signature.strip())


def external_id(payload: dict, body: bytes, header_id: str | None) -> str:
    return str(header_id or payload.get("id") or hashlib.sha256(body).hexdigest())


def handle_webhook_received(conn: Connection, job: Job) -> dict:
    event_id = job.payload["event_id"]
    event = conn.execute(text("SELECT * FROM app.webhook_event_load(:i)"), {"i": event_id}).one_or_none()
    if event is None:
        return {"missing": str(event_id)}
    if event.status == "processed":
        return {"skipped": "processed"}
    fn = HANDLERS.get(event.integration)
    if fn is None:
        conn.execute(text("SELECT app.webhook_event_mark(:i, 'ignored', 'no handler for this integration yet')"), {"i": event_id})
        return {"ignored": event.integration}
    try:
        with conn.begin_nested():
            result: Any = fn(conn, {"id": event.id, "integration": event.integration, "external_id": event.external_id,
                                    "payload": event.payload})
    except Exception as exc:  # noqa: BLE001 - kept and alerting; ops replays it
        conn.execute(text("SELECT app.webhook_event_mark(:i, 'failed', :e)"), {"i": event_id, "e": f"{type(exc).__name__}: {exc}"})
        return {"failed": type(exc).__name__}
    conn.execute(text("SELECT app.webhook_event_mark(:i, 'processed')"), {"i": event_id})
    return {"processed": event.integration, **(result or {})}
