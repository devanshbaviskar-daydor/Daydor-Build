"""direct-deposit-disburser + the g_pay_disburse hard gate: "no disbursal without an approved
gate" (docs/backend-plan.md principle 2), enforced by `app.gate_guard`
(migrations/sql/0006_gates.sql), not just by this module's own logic. `request_disbursal_approval`
and `disburse_payroll_run` are deliberately separate calls: approval can be requested, and sit
pending, independently of when (or whether) disbursal is actually attempted.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, text

from daydor.adapters.bank import BankAdapter, FakeBankAdapter, TransferRequest
from daydor.gates.hard import request_approval


def request_disbursal_approval(conn: Connection, *, payroll_run_id: UUID) -> UUID:
    """Idempotent via request_approval's own idempotency key."""
    return request_approval(conn, "g_pay_disburse", "payroll_run", payroll_run_id)


def disburse_payroll_run(conn: Connection, adapter: BankAdapter | None = None, *,
                         payroll_run_id: UUID, approval_request_id: UUID) -> None:
    """Raises (via app.enforce_gate_guard, not a Python-side check) if approval_request_id isn't
    an approved g_pay_disburse request for this exact row -- the database is the actual
    enforcement, this call doesn't duplicate that check beforehand."""
    adapter = adapter or FakeBankAdapter()
    net_total = conn.execute(text("SELECT net_total FROM payroll_run WHERE id = :r"),
                             {"r": payroll_run_id}).scalar_one()
    adapter.transfer(TransferRequest(reference=str(payroll_run_id), amount=net_total))
    conn.execute(
        text("UPDATE payroll_run SET approval_request_id = :a, disbursed_at = now() WHERE id = :r"),
        {"a": approval_request_id, "r": payroll_run_id})
