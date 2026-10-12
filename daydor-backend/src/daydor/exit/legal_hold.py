"""Exit flow step 2: `legal_hold`, read-only here ("root orchestrator" in the model: the flow
itself checks it, not a queued worker). Placing or releasing a hold is a direct `tenant_hr`/
`tenant_founder` write (`agent_runtime` only has READ on this table) -- no service needed, just a
real row to check against, per docs/sprint-plan.md.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, text

from daydor.queue.worker import Job
from daydor.workflow.engine import WorkflowEngine


def has_active_hold(conn: Connection, *, scope_type: str, scope_id: UUID) -> bool:
    return conn.execute(
        text("SELECT EXISTS (SELECT 1 FROM legal_hold WHERE scope_type = :st AND scope_id = :si "
             "AND released_at IS NULL)"), {"st": scope_type, "si": scope_id}).scalar_one()


def handle_legal_hold_checker(engine: WorkflowEngine):
    """Queue handler for kind 'legal_hold_checker' (exit flow step 2, queue 'hr'). The
    'root orchestrator' in the model -- the flow itself checks the hold, not a domain agent.
    Fires its own 'advance', gated natively by g_legalhold only when a hold is actually active
    (requires_g_legalhold, same conditional-gate shape as hire's g_aedt/g_offer_band)."""
    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        active = has_active_hold(conn, scope_type="employee", scope_id=UUID(ctx["employee_id"]))
        engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}",
                   context_patch={"requires_g_legalhold": active})
        return {"active_legal_hold": active}
    return handle
