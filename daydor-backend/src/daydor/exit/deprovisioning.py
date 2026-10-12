"""Exit flow step 4: deprovisioning-agent, gated by `g_it_deprov`.

Unlike the hire flow's gates, this one is **not** modelled as an engine-level transition gate:
`app.enforce_gate_guard` (migrations/sql/0006_gates.sql) checks the approval's own `subject_id`
against the row being written (`identity_account.id`), not against the workflow instance's fixed
subject (`termination.id`). Using the engine's native `gate` field here would request a *second*,
redundant approval against the wrong subject -- one that could never satisfy the real DB-enforced
guard on `deprovisioned_at`. So `request_deprovisioning_approval` and `deprovision_identity` are
direct calls, the same two-step shape `daydor.payroll.disbursement` uses for `g_pay_disburse`;
`deprovision_identity` only advances the workflow instance once the guarded write has actually
succeeded, which is impossible without an approved `g_it_deprov` request for this exact
`identity_account` row.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, text

from daydor.gates.hard import request_approval
from daydor.workflow.engine import TransitionResult, WorkflowEngine


def request_deprovisioning_approval(conn: Connection, *, identity_account_id: UUID) -> UUID:
    """Idempotent via request_approval's own idempotency key."""
    return request_approval(conn, "g_it_deprov", "identity_account", identity_account_id)


def deprovision_identity(conn: Connection, engine: WorkflowEngine, instance_id: UUID, *,
                         identity_account_id: UUID, approval_request_id: UUID) -> TransitionResult:
    """Raises (via app.enforce_gate_guard, not a Python-side check) if approval_request_id isn't
    an approved g_it_deprov request for this exact identity_account row."""
    conn.execute(
        text("UPDATE identity_account SET approval_request_id = :a, deprovisioned_at = now(), "
             "status = 'deprovisioned' WHERE id = :i"),
        {"a": approval_request_id, "i": identity_account_id})
    conn.execute(
        text("UPDATE app_access_grant SET revoked_at = now() WHERE identity_account_id = :i "
             "AND revoked_at IS NULL"), {"i": identity_account_id})
    return engine.fire(conn, instance_id, "advance")


def handle_deprovisioning_agent(engine: WorkflowEngine):
    """Queue handler for kind 'deprovisioning_agent' (exit flow step 4, queue 'it'). Only opens
    the approval request; does not advance the instance (see module docstring)."""
    def handle(conn: Connection, job) -> dict:
        ctx = job.payload["context"]
        employee_id = UUID(ctx["employee_id"])
        identity_account_id = conn.execute(
            text("SELECT id FROM identity_account WHERE employee_id = :e"),
            {"e": employee_id}).scalar_one()
        approval_id = request_deprovisioning_approval(conn, identity_account_id=identity_account_id)
        return {"identity_account_id": str(identity_account_id), "approval_request_id": str(approval_id)}
    return handle
