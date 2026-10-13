"""Hire flow step 14: i9-e-verify-initiator.

US only (the model's own step description). Whether it applies is determined here, from the
employee's own legal_entity.country_code, not from a context flag the caller has to remember to
set -- same reasoning as daydor.hire.employee_record fetching department_id from the DB instead
of duplicating it into context.

The I-9 clock ("the 3-business-day clock runs from the first day worked") is a real
app.timer row, scheduled with app.add_business_days against the 'US-FED' calendar
(see migrations/sql/0005_queue.sql / tests/test_queue.py for the calendar convention).
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, text

from daydor.adapters.everify import EVerifyAdapter, EVerifyRequest, FakeEVerifyAdapter
from daydor.queue import emit_event, schedule_timer
from daydor.queue.worker import Job
from daydor.workflow.engine import WorkflowEngine

I9_CALENDAR = "US-FED"
I9_BUSINESS_DAYS = 3


def initiate_work_authorization(conn: Connection, adapter: EVerifyAdapter, *, employee_id: UUID) -> dict:
    """Idempotent on employee_id. No-ops (applicable=False) outside the US."""
    country_code = conn.execute(
        text("SELECT le.country_code FROM employee e JOIN legal_entity le ON le.id = e.legal_entity_id "
             "WHERE e.id = :e"), {"e": employee_id}).scalar_one()
    if country_code != "US":
        return {"applicable": False}

    existing = conn.execute(text("SELECT id FROM work_authorization WHERE employee_id = :e"),
                            {"e": employee_id}).scalar_one_or_none()
    if existing is not None:
        return {"applicable": True, "work_authorization_id": existing}

    result = adapter.submit(EVerifyRequest(employee_id=str(employee_id)))
    date_of_joining = conn.execute(text("SELECT date_of_joining FROM employee WHERE id = :e"),
                                   {"e": employee_id}).scalar_one()
    due_at = conn.execute(text("SELECT app.add_business_days(:d, :n, :cal)::timestamptz + interval '9 hours'"),
                          {"d": date_of_joining, "n": I9_BUSINESS_DAYS, "cal": I9_CALENDAR}).scalar_one()

    work_authorization_id = conn.execute(
        text("INSERT INTO work_authorization (employee_id, auth_type, status, everify_case_no, "
             "everify_status, sponsor_flag, next_action_due) "
             "VALUES (:e, 'citizen_or_national', 'pending', :c, :s, false, :due) RETURNING id"),
        {"e": employee_id, "c": result.case_number, "s": result.status, "due": due_at.date()},
    ).scalar_one()
    schedule_timer(conn, timer_key=f"i9-section2-{employee_id}", queue="hr", kind="i9_section2_due",
                   fire_at=due_at, payload={"employee_id": str(employee_id),
                                           "work_authorization_id": str(work_authorization_id)})
    return {"applicable": True, "work_authorization_id": work_authorization_id}


def handle_i9_e_verify_initiator(engine: WorkflowEngine, adapter: EVerifyAdapter | None = None):
    """Queue handler for kind 'i9_e_verify_initiator' (hire flow step 14, queue 'hr')."""
    adapter = adapter or FakeEVerifyAdapter()

    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        result = initiate_work_authorization(conn, adapter, employee_id=UUID(ctx["employee_id"]))
        engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}")
        return {k: str(v) for k, v in result.items()}
    return handle


def check_i9_section2(conn: Connection, *, employee_id: UUID, work_authorization_id: UUID) -> dict:
    """The I-9 section 2 deadline passed: say so if section 2 is still not done. Silent when it was
    completed in time or the employee has left. The timer fires once, so the event is not repeated."""
    row = conn.execute(
        text("SELECT wa.i9_section2_completed_at, e.is_active FROM work_authorization wa "
             "JOIN employee e ON e.id = wa.employee_id WHERE wa.id = :w AND wa.employee_id = :e"),
        {"w": work_authorization_id, "e": employee_id}).one_or_none()
    if row is None or row.i9_section2_completed_at is not None or not row.is_active:
        return {"overdue": False}
    emit_event(conn, "i9.section2_overdue", "work_authorization", work_authorization_id,
               {"employee_id": str(employee_id)})
    return {"overdue": True}


def handle_i9_section2_due(conn: Connection, job: Job) -> dict:
    """Queue handler for the timer kind 'i9_section2_due' (queue 'hr', scheduled in step 14)."""
    result = check_i9_section2(conn, employee_id=UUID(job.payload["employee_id"]),
                               work_authorization_id=UUID(job.payload["work_authorization_id"]))
    return {"overdue": result["overdue"]}
