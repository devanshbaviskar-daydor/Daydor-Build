"""Hire flow step 3: requisition-approval-router.

There is no business logic of its own here -- the budget-approval gate (`g_requisition_budget`,
docs/model-findings.md finding 11) is attached directly to this state's outgoing transition in
`daydor.hire.workflow.HIRE_DEFINITION`, so `WorkflowEngine.fire()` already raises the
`approval_request` and parks the instance in `waiting_gate` on its own (see
`WorkflowEngine.fire`'s `gate`/`request_approval` branch). This worker's whole job is to be the
thing that fires 'advance' when the state is entered, which is what actually triggers that gate
check. Keeping it as its own named step (queue 'platform', kind
'requisition_approval_router') matches the model's own step list and gives the step a place to
grow real routing logic later (e.g. picking an approver by cost center) without moving the gate.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection

from daydor.queue.worker import Job
from daydor.workflow.engine import WorkflowEngine


def handle_requisition_approval_router(engine: WorkflowEngine):
    """Queue handler for kind 'requisition_approval_router' (hire flow step 3, queue 'platform')."""
    def handle(conn: Connection, job: Job) -> dict:
        result = engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance",
                             event_id=f"job:{job.id}")
        return {"outcome": result.outcome, "approval_request_id": str(result.approval_request_id)
                if result.approval_request_id else None}
    return handle
