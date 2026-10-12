"""Producer helpers. Call these inside a tenant_session so the work, the event and the job
commit together (or not at all)."""
from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import Connection, text


def enqueue(conn: Connection, queue: str, kind: str, payload: dict | None = None, *,
            idempotency_key: str | None = None, run_at: datetime | None = None,
            max_attempts: int = 5, priority: int = 100) -> UUID:
    return conn.execute(
        text("SELECT app.enqueue(:q, :k, CAST(:p AS jsonb), :ik, coalesce(:ra, now()), :ma, :pr)"),
        {"q": queue, "k": kind, "p": json.dumps(payload or {}), "ik": idempotency_key, "ra": run_at,
         "ma": max_attempts, "pr": priority},
    ).scalar_one()


def emit_event(conn: Connection, topic: str, subject_table: str | None = None,
               subject_id: UUID | None = None, payload: dict | None = None) -> int:
    return conn.execute(
        text("SELECT app.emit_event(:t, :st, :sid, CAST(:p AS jsonb))"),
        {"t": topic, "st": subject_table, "sid": subject_id, "p": json.dumps(payload or {}, default=str)},
    ).scalar_one()


def schedule_timer(conn: Connection, timer_key: str, queue: str, kind: str, fire_at: datetime,
                   payload: dict | None = None) -> UUID | None:
    return conn.execute(
        text("SELECT app.schedule_timer(:k, :q, :kind, :f, CAST(:p AS jsonb))"),
        {"k": timer_key, "q": queue, "kind": kind, "f": fire_at, "p": json.dumps(payload or {}, default=str)},
    ).scalar_one()


def cancel_timer(conn: Connection, timer_key: str) -> bool:
    return conn.execute(text("SELECT app.cancel_timer(:k)"), {"k": timer_key}).scalar_one()
