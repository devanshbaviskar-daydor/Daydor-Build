"""Exit flow step 11: cobra-trigger-detector + cobra-notice-generator, US only, gated by
`g_cobra` (`cobra_event.notice_sent_at`, guarded same as `g_it_deprov`/`g_pay_disburse` --
migrations/sql/0022_exit_gate_guards.sql).

Jurisdiction check reads the employee's legal_entity.country_code, same convention as
daydor.hire.work_authorization's I-9 applicability check and daydor.payroll.tax_filing's scheme
lookup: no COBRA-qualifying event outside the US, no-op rather than erroring.
"""
from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import Connection, text

from daydor.gates.hard import request_approval
from daydor.queue.worker import Job
from daydor.workflow.engine import TransitionResult, WorkflowEngine

NOTICE_WINDOW_DAYS = 44  # illustrative: the real federal COBRA deadline is 44 days from the event


def detect_cobra_event(conn: Connection, *, employee_id: UUID, event_date: date) -> UUID | None:
    """Returns None outside the US (no COBRA-qualifying event). Idempotent on employee_id."""
    country_code = conn.execute(
        text("SELECT le.country_code FROM employee e JOIN legal_entity le ON le.id = e.legal_entity_id "
             "WHERE e.id = :e"), {"e": employee_id}).scalar_one()
    if country_code != "US":
        return None

    existing = conn.execute(text("SELECT id FROM cobra_event WHERE employee_id = :e"),
                            {"e": employee_id}).scalar_one_or_none()
    if existing is not None:
        return existing
    return conn.execute(
        text("INSERT INTO cobra_event (employee_id, qualifying_event, event_date, notice_due_at, "
             "election_status) VALUES (:e, 'termination', :ed, :due, 'pending') RETURNING id"),
        {"e": employee_id, "ed": event_date, "due": event_date + timedelta(days=NOTICE_WINDOW_DAYS)},
    ).scalar_one()


def request_cobra_notice_approval(conn: Connection, *, cobra_event_id: UUID) -> UUID:
    """Idempotent via request_approval's own idempotency key."""
    return request_approval(conn, "g_cobra", "cobra_event", cobra_event_id)


def send_cobra_notice(conn: Connection, engine: WorkflowEngine, instance_id: UUID, *,
                      cobra_event_id: UUID, approval_request_id: UUID) -> TransitionResult:
    """Raises (via app.enforce_gate_guard, not a Python-side check) if approval_request_id isn't
    an approved g_cobra request for this exact cobra_event row."""
    conn.execute(
        text("UPDATE cobra_event SET approval_request_id = :a, notice_sent_at = now() WHERE id = :i"),
        {"a": approval_request_id, "i": cobra_event_id})
    return engine.fire(conn, instance_id, "advance")


def handle_cobra_trigger_detector(engine: WorkflowEngine):
    """Queue handler for kind 'cobra_trigger_detector' (exit flow step 11, queue 'hr')."""
    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        employee_id = UUID(ctx["employee_id"])
        event_date = conn.execute(text("SELECT last_working_day FROM termination WHERE employee_id = :e"),
                                  {"e": employee_id}).scalar_one()
        cobra_event_id = detect_cobra_event(conn, employee_id=employee_id, event_date=event_date)
        if cobra_event_id is None:
            engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}")
            return {"cobra_event_id": None}
        approval_id = request_cobra_notice_approval(conn, cobra_event_id=cobra_event_id)
        return {"cobra_event_id": str(cobra_event_id), "approval_request_id": str(approval_id)}
    return handle
