"""Hire flow step 7: interview-scheduler.

Scope simplification: there is no calendar/availability integration, so interviewer and time are
supplied as context (set when the hire starts -- see daydor.hire.workflow.start_hire) rather than
computed here. A real scheduler would need interviewer availability, which is its own adapter.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Connection, text

from daydor.queue.worker import Job
from daydor.workflow.engine import WorkflowEngine


def schedule_interview(conn: Connection, *, application_id: UUID, interviewer_employee_id: UUID,
                       scheduled_at: datetime) -> UUID:
    """Idempotent on application_id: one interview per application in this simplified flow."""
    existing = conn.execute(text("SELECT id FROM interview WHERE application_id = :a"),
                            {"a": application_id}).scalar_one_or_none()
    if existing is not None:
        return existing
    return conn.execute(
        text("INSERT INTO interview (application_id, interviewer_employee_id, scheduled_at) "
             "VALUES (:a, :i, :s) RETURNING id"),
        {"a": application_id, "i": interviewer_employee_id, "s": scheduled_at}).scalar_one()


def handle_interview_scheduler(engine: WorkflowEngine):
    """Queue handler for kind 'interview_scheduler' (hire flow step 7, queue 'ta')."""
    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        interview_id = schedule_interview(
            conn, application_id=UUID(ctx["application_id"]),
            interviewer_employee_id=UUID(ctx["interviewer_employee_id"]),
            scheduled_at=datetime.fromisoformat(ctx["scheduled_at"]))
        engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}",
                   context_patch={"interview_id": str(interview_id)})
        return {"interview_id": str(interview_id)}
    return handle
