"""Exit flow steps 6-10: final-pay-calculator (reads `leave_balance` + `gratuity_accrual_balance`,
never recomputes either), `g_finalpay` (a workflow-level checkpoint on the calculated amounts --
see `daydor.exit.workflow`'s module docstring for why it has no guarded column of its own, unlike
`g_it_deprov`), then direct-deposit-disburser reusing Sprint 8's `g_pay_disburse` pattern.

Finding 20 (docs/model-findings.md): `final_settlement.total_settlement` is `derived` and
`approval_request_id` was modelled NOT NULL -- the same "can't reference what doesn't exist yet"
shape as findings 10/19. `approval_request_id` is now nullable
(`migrations/sql/0022_exit_gate_guards.sql`); `open_final_settlement_record` creates the row
through `app.open_final_settlement`, a SECURITY DEFINER function, same pattern as
`daydor.payroll.run_builder`'s `app.open_payroll_run`.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Connection, text

from daydor.gates.hard import request_approval
from daydor.queue.worker import Job
from daydor.workflow.engine import TransitionResult, WorkflowEngine

PENDING_WAGES_PLACEHOLDER = Decimal("0.00")  # illustrative: a real calculator prorates the last pay period
RECOVERIES_PLACEHOLDER = Decimal("0.00")     # illustrative: real recoveries come from loan/advance ledgers


def calculate_final_settlement(conn: Connection, *, employee_id: UUID) -> dict:
    leave = conn.execute(
        text("SELECT balance_days FROM leave_balance WHERE employee_id = :e ORDER BY as_of DESC LIMIT 1"),
        {"e": employee_id}).scalar_one_or_none()
    gratuity = conn.execute(
        text("SELECT accrued_amount FROM gratuity_accrual_balance WHERE employee_id = :e"),
        {"e": employee_id}).scalar_one_or_none()
    daily_rate = conn.execute(
        text("SELECT ctc_annual / 365 FROM employment_record WHERE employee_id = :e "
             "ORDER BY effective_from DESC LIMIT 1"), {"e": employee_id}).scalar_one()

    leave_encashment = ((leave or Decimal("0")) * daily_rate).quantize(Decimal("0.01"))
    return {"pending_wages": str(PENDING_WAGES_PLACEHOLDER),
           "gratuity_payout": str(gratuity or Decimal("0.00")),
           "leave_encashment": str(leave_encashment),
           "recoveries": str(RECOVERIES_PLACEHOLDER)}


def open_final_settlement_record(conn: Connection, *, employee_id: UUID, termination_id: UUID,
                                 pending_wages: Decimal, gratuity_payout: Decimal,
                                 leave_encashment: Decimal, recoveries: Decimal) -> UUID:
    """Idempotent on termination_id: one settlement per termination."""
    existing = conn.execute(text("SELECT id FROM final_settlement WHERE termination_id = :t"),
                            {"t": termination_id}).scalar_one_or_none()
    if existing is not None:
        return existing
    return conn.execute(
        text("SELECT app.open_final_settlement(:e, :t, :pw, :gp, :le, :r)"),
        {"e": employee_id, "t": termination_id, "pw": pending_wages, "gp": gratuity_payout,
         "le": leave_encashment, "r": recoveries}).scalar_one()


def request_disbursal_approval(conn: Connection, *, final_settlement_id: UUID) -> UUID:
    """Idempotent via request_approval's own idempotency key."""
    return request_approval(conn, "g_pay_disburse", "final_settlement", final_settlement_id)


def disburse_final_settlement(conn: Connection, engine: WorkflowEngine, instance_id: UUID, *,
                              final_settlement_id: UUID, approval_request_id: UUID) -> TransitionResult:
    """Raises (via app.enforce_gate_guard, not a Python-side check) if approval_request_id isn't
    an approved g_pay_disburse request for this exact final_settlement row."""
    conn.execute(
        text("UPDATE final_settlement SET approval_request_id = :a, disbursed_at = now() "
             "WHERE id = :i"), {"a": approval_request_id, "i": final_settlement_id})
    return engine.fire(conn, instance_id, "advance")


def handle_final_pay_calculator(engine: WorkflowEngine):
    """Queue handler for kind 'final_pay_calculator' (exit flow step 6-8, queue 'pay'). Fires its
    own 'advance', gated natively by g_finalpay (the calculated amounts are only known once this
    handler runs -- same "gate the outgoing transition" correction as hire's g_aedt/g_offer_band)."""
    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        amounts = calculate_final_settlement(conn, employee_id=UUID(ctx["employee_id"]))
        engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}",
                   context_patch=amounts)
        return amounts
    return handle


def handle_final_settlement_opener(engine: WorkflowEngine):
    """Queue handler for kind 'final_settlement_opener' (exit flow step 9, queue 'pay'). Only
    reachable once g_finalpay has approved (the previous transition is gated); materializes the
    approved amounts as a real final_settlement row and advances, ungated."""
    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        final_settlement_id = open_final_settlement_record(
            conn, employee_id=UUID(ctx["employee_id"]), termination_id=UUID(ctx["termination_id"]),
            pending_wages=Decimal(ctx["pending_wages"]), gratuity_payout=Decimal(ctx["gratuity_payout"]),
            leave_encashment=Decimal(ctx["leave_encashment"]), recoveries=Decimal(ctx["recoveries"]))
        engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}",
                   context_patch={"final_settlement_id": str(final_settlement_id)})
        return {"final_settlement_id": str(final_settlement_id)}
    return handle


def handle_direct_deposit_disburser(engine: WorkflowEngine):
    """Queue handler for kind 'direct_deposit_disburser' (exit flow step 10, queue 'pay'). Only
    opens the approval request; does not advance the instance -- see module docstring and
    disburse_final_settlement, which is what actually advances once approved."""
    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        approval_id = request_disbursal_approval(conn, final_settlement_id=UUID(ctx["final_settlement_id"]))
        return {"approval_request_id": str(approval_id)}
    return handle
