"""Statutory clocks: the daily scan that raises clock.due_soon and clock.overdue events (0039).

`handle_statutory_clock_scan` is a queue handler for the timer kind 'statutory_clock_scan' (queue 'platform'). Each
run scans the job's tenant (`app.scan_statutory_clocks`: idempotent, so a retry or a second runner emits nothing new)
and then schedules the next day's run, so one `start_clock_scan` per tenant keeps the chain going. Run it as the
`root-orchestrator` platform actor.

The I-9 Section 2 deadline predates this and has its own timer (daydor.hire.work_authorization); the clocks here are
the ones that are a dated column on a row some flow already wrote.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import Connection, text

from daydor.queue import schedule_timer
from daydor.queue.worker import Job

QUEUE, KIND = "platform", "statutory_clock_scan"
RUN_AT = time(2, 0, tzinfo=timezone.utc)          # after midnight UTC, before any working day starts in IN or the US


def timer_key(day: date) -> str:
    return f"statutory-clock-scan-{day.isoformat()}"


def start_clock_scan(conn: Connection, *, first_day: date | None = None) -> None:
    """Begin (or re-assert) this tenant's daily scan. Idempotent: the timer key is per day."""
    day = first_day or date.today()
    schedule_timer(conn, timer_key=timer_key(day), queue=QUEUE, kind=KIND,
                   fire_at=datetime.combine(day, RUN_AT), payload={"day": day.isoformat()})


def scan_now(conn: Connection, *, as_of: date | None = None) -> int:
    return conn.execute(text("SELECT app.scan_statutory_clocks(:d)"), {"d": as_of or date.today()}).scalar_one()


def handle_statutory_clock_scan(conn: Connection, job: Job) -> dict:
    day = date.fromisoformat(job.payload.get("day") or date.today().isoformat())
    emitted = scan_now(conn, as_of=max(day, date.today()))      # a late run scans as of today, not the day it was set for
    start_clock_scan(conn, first_day=day + timedelta(days=1))   # tomorrow's run
    return {"emitted": emitted, "day": day.isoformat()}
