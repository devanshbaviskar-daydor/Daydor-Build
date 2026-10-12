"""Exit flow step 3: termination-checklist-builder. Same `checklist`/`checklist_task` tables as
`daydor.hire.checklist`'s onboarding builder, distinguished by `kind='termination'`.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import Connection, text

from daydor.queue.worker import Job
from daydor.workflow.engine import WorkflowEngine

# (title, owner_domain, days_before_last_day, blocking)
TERMINATION_TASKS = (
    ("Transfer owned documents and approvals", "hr", 3, True),
    ("Collect company property", "it", 1, True),
    ("Exit interview", "hr", 0, False),
)


def build_termination_checklist(conn: Connection, *, employee_id: UUID, last_working_day: date) -> dict:
    """Idempotent on employee_id: one termination checklist per employee."""
    existing = conn.execute(
        text("SELECT id FROM checklist WHERE employee_id = :e AND kind = 'termination'"),
        {"e": employee_id}).scalar_one_or_none()
    if existing is not None:
        task_ids = conn.execute(text("SELECT id FROM checklist_task WHERE checklist_id = :c"),
                                {"c": existing}).scalars().all()
        return {"checklist_id": existing, "task_ids": task_ids}

    checklist_id = conn.execute(
        text("INSERT INTO checklist (employee_id, kind, template_key, status, due_date) "
             "VALUES (:e, 'termination', 'default-termination-v1', 'open', :due) RETURNING id"),
        {"e": employee_id, "due": last_working_day}).scalar_one()

    task_ids = []
    for title, owner_domain, days_before, blocking in TERMINATION_TASKS:
        due_at = datetime.combine(last_working_day - timedelta(days=days_before), time(17, 0),
                                  tzinfo=timezone.utc)
        task_ids.append(conn.execute(
            text("INSERT INTO checklist_task (checklist_id, owner_domain, title, status, due_at, blocking) "
                 "VALUES (:c, :o, :t, 'open', :due, :b) RETURNING id"),
            {"c": checklist_id, "o": owner_domain, "t": title, "due": due_at, "b": blocking}).scalar_one())
    return {"checklist_id": checklist_id, "task_ids": task_ids}


def handle_termination_checklist_builder(engine: WorkflowEngine):
    """Queue handler for kind 'termination_checklist_builder' (exit flow step 3, queue 'hr')."""
    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        employee_id = UUID(ctx["employee_id"])
        last_working_day = conn.execute(
            text("SELECT last_working_day FROM termination WHERE employee_id = :e"),
            {"e": employee_id}).scalar_one()
        result = build_termination_checklist(conn, employee_id=employee_id,
                                             last_working_day=last_working_day)
        engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}",
                   context_patch={"checklist_id": str(result["checklist_id"])})
        return {"checklist_id": str(result["checklist_id"]), "task_count": len(result["task_ids"])}
    return handle
