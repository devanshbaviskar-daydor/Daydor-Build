"""Approval deadlines and escalation: an hourly sweep per tenant (0044).

`handle_approval_sweep` is a queue handler for the timer kind 'approval_sweep' (queue 'platform'), run as the `root-orchestrator`
platform actor. Each run gives every pending approval a deadline (the gate's response window, app.gate_sla), escalates the ones past it
(`approval.escalated`, once each) and schedules the next hour. Escalation only notifies: it never changes who may resolve a gate.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import Connection, text

from daydor.queue import schedule_timer
from daydor.queue.worker import Job

QUEUE, KIND = "platform", "approval_sweep"


def _hour(at: datetime) -> datetime:
    return at.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def timer_key(hour: datetime) -> str:
    return f"approval-sweep-{hour:%Y%m%d%H}"


def start_sweep(conn: Connection, *, at: datetime | None = None) -> None:
    """Begin (or re-assert) this tenant's hourly sweep. Idempotent: the timer key is per hour."""
    hour = _hour(at or datetime.now(timezone.utc))
    schedule_timer(conn, timer_key=timer_key(hour), queue=QUEUE, kind=KIND, fire_at=hour, payload={"hour": hour.isoformat()})


def sweep_now(conn: Connection) -> int:
    return conn.execute(text("SELECT app.sweep_approvals()")).scalar_one()


def handle_approval_sweep(conn: Connection, job: Job) -> dict:
    escalated = sweep_now(conn)
    start_sweep(conn, at=datetime.now(timezone.utc) + timedelta(hours=1))
    return {"escalated": escalated}
