"""Exit flow step 5: equipment-return-tracker. No gate -- a device return confirmation, not a
financial or access-security action."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, text

from daydor.queue.worker import Job
from daydor.workflow.engine import WorkflowEngine


def mark_devices_returned(conn: Connection, *, employee_id: UUID) -> list[UUID]:
    """Idempotent: only touches rows not already marked returned."""
    return conn.execute(
        text("UPDATE device_assignment SET returned_at = now() WHERE employee_id = :e "
             "AND returned_at IS NULL RETURNING id"), {"e": employee_id}).scalars().all()


def handle_equipment_return_tracker(engine: WorkflowEngine):
    """Queue handler for kind 'equipment_return_tracker' (exit flow step 5, queue 'it')."""
    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        returned = mark_devices_returned(conn, employee_id=UUID(ctx["employee_id"]))
        engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}")
        return {"returned_device_assignment_ids": [str(i) for i in returned]}
    return handle
