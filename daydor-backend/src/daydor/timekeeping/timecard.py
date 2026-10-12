"""timecard: punch-validator (turns time_punch rows into a timecard) and
timecard-approval-router (sends it to the manager via g_timecard).

Resolves finding 9 (docs/model-findings.md): no gate in the model names the manager as an
approver, though this step needs one. See daydor.gates.registry.PLATFORM_HARD_GATES for
`g_timecard`.

Unlike the hire flow, a timecard's approval isn't tracked by a WorkflowEngine instance -- pay
periods recur for every employee, there's no single "start" and "done" the way a hire has one.
So `g_timecard`'s resolution needs its own delivery path back to the timecard row: see
`handle_timekeeping_gate_resolved`, subscribed to the same `gate.resolved` topic the workflow
engine uses, on its own 'timekeeping' queue (migrations/sql/0019_timecard_gates.sql).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Connection, text

from daydor.gates.hard import request_approval
from daydor.queue.worker import Job

REGULAR_HOURS_PER_PERIOD_CAP = Decimal("40")


def validate_timecard(conn: Connection, *, employee_id: UUID, period_start: date, period_end: date) -> UUID:
    """Pairs consecutive (in, out) time_punch rows in [period_start, period_end] into total
    hours, splits them into regular (up to 40) and overtime, and opens a timecard pending
    approval. Idempotent on (employee_id, period_start, period_end)."""
    existing = conn.execute(
        text("SELECT id FROM timecard WHERE employee_id = :e AND period_start = :s AND period_end = :f"),
        {"e": employee_id, "s": period_start, "f": period_end}).scalar_one_or_none()
    if existing is not None:
        return existing

    punches = conn.execute(
        text("SELECT punched_at, kind FROM time_punch WHERE employee_id = :e "
             "AND punched_at::date BETWEEN :s AND :f ORDER BY punched_at"),
        {"e": employee_id, "s": period_start, "f": period_end}).all()

    total_hours = Decimal("0")
    pending_in = None
    for p in punches:
        if p.kind == "in":
            pending_in = p.punched_at
        elif p.kind == "out" and pending_in is not None:
            total_hours += Decimal((p.punched_at - pending_in).total_seconds()) / 3600
            pending_in = None

    regular_hours = min(total_hours, REGULAR_HOURS_PER_PERIOD_CAP)
    overtime_hours = max(total_hours - REGULAR_HOURS_PER_PERIOD_CAP, Decimal("0"))

    return conn.execute(
        text("INSERT INTO timecard (employee_id, period_start, period_end, regular_hours, "
             "overtime_hours, status) VALUES (:e, :s, :f, :r, :o, 'pending_approval') RETURNING id"),
        {"e": employee_id, "s": period_start, "f": period_end, "r": regular_hours, "o": overtime_hours},
    ).scalar_one()


def route_for_approval(conn: Connection, *, timecard_id: UUID) -> UUID:
    """Idempotent via request_approval's own idempotency key (gate_id:subject_table:subject_id)."""
    return request_approval(conn, "g_timecard", "timecard", timecard_id)


def handle_timekeeping_gate_resolved(conn: Connection, job: Job) -> dict:
    """Queue handler for kind 'timekeeping.gate_resolved' (queue 'timekeeping'). Every
    gate.resolved event fans out here (see migrations/sql/0019_timecard_gates.sql); anything
    that isn't a g_timecard resolution is a no-op, the same way the workflow engine's own
    gate_resolved_handler no-ops for gates no instance is waiting on."""
    data = job.payload["data"]
    if data["gate_id"] != "g_timecard":
        return {"handled": False}
    timecard_id = UUID(job.payload["subject_id"])
    if data["decision"] == "approved":
        conn.execute(text("UPDATE timecard SET status = 'approved', approved_by_user_id = "
                          "(SELECT resolved_by_user_id FROM approval_request WHERE id = :a) "
                          "WHERE id = :t"), {"a": data["approval_request_id"], "t": timecard_id})
    else:
        conn.execute(text("UPDATE timecard SET status = 'rejected' WHERE id = :t"), {"t": timecard_id})
    return {"handled": True, "timecard_id": str(timecard_id), "decision": data["decision"]}
