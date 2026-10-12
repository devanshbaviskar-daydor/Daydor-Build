"""Hire flow step 15: onboarding-checklist-builder.

Builds one `checklist` row (kind='onboarding') and a fixed set of `checklist_task` rows under it.
A real builder would vary tasks by role/location/jurisdiction; this one is a fixed template,
documented as a simplification rather than guessed-at business logic.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import Connection, text

from daydor.queue.worker import Job
from daydor.workflow.engine import WorkflowEngine

# (title, owner_domain, days_after_joining, blocking)
ONBOARDING_TASKS = (
    ("Set up workstation", "it", 0, True),
    ("Complete tax and banking forms", "hr", 0, True),
    ("Attend orientation", "ob", 2, False),
)


def build_onboarding_checklist(conn: Connection, *, employee_id: UUID, date_of_joining: date) -> dict:
    """Idempotent on employee_id: one onboarding checklist per employee."""
    existing = conn.execute(text("SELECT id FROM checklist WHERE employee_id = :e AND kind = 'onboarding'"),
                            {"e": employee_id}).scalar_one_or_none()
    if existing is not None:
        task_ids = conn.execute(text("SELECT id FROM checklist_task WHERE checklist_id = :c"),
                                {"c": existing}).scalars().all()
        return {"checklist_id": existing, "task_ids": task_ids}

    checklist_id = conn.execute(
        text("INSERT INTO checklist (employee_id, kind, template_key, status, due_date) "
             "VALUES (:e, 'onboarding', 'default-onboarding-v1', 'open', :due) RETURNING id"),
        {"e": employee_id, "due": date_of_joining + timedelta(days=7)}).scalar_one()

    task_ids = []
    for title, owner_domain, days_after, blocking in ONBOARDING_TASKS:
        due_at = datetime.combine(date_of_joining + timedelta(days=days_after), time(9, 0), tzinfo=timezone.utc)
        task_ids.append(conn.execute(
            text("INSERT INTO checklist_task (checklist_id, owner_domain, title, status, due_at, blocking) "
                 "VALUES (:c, :o, :t, 'open', :due, :b) RETURNING id"),
            {"c": checklist_id, "o": owner_domain, "t": title, "due": due_at, "b": blocking}).scalar_one())
    return {"checklist_id": checklist_id, "task_ids": task_ids}


def handle_onboarding_checklist_builder(engine: WorkflowEngine):
    """Queue handler for kind 'onboarding_checklist_builder' (hire flow step 15, queue 'ob')."""
    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        employee_id = UUID(ctx["employee_id"])
        date_of_joining = conn.execute(text("SELECT date_of_joining FROM employee WHERE id = :e"),
                                       {"e": employee_id}).scalar_one()
        result = build_onboarding_checklist(conn, employee_id=employee_id, date_of_joining=date_of_joining)
        engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}",
                   context_patch={"checklist_id": str(result["checklist_id"])})
        return {"checklist_id": str(result["checklist_id"]), "task_count": len(result["task_ids"])}
    return handle
