"""payslip-issuer: marks payslips issued, only after their payroll_run has actually disbursed."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, text


class PayrollRunNotDisbursed(RuntimeError):
    pass


def issue_payslips(conn: Connection, *, payroll_run_id: UUID) -> list[UUID]:
    disbursed_at = conn.execute(text("SELECT disbursed_at FROM payroll_run WHERE id = :r"),
                                {"r": payroll_run_id}).scalar_one()
    if disbursed_at is None:
        raise PayrollRunNotDisbursed(f"payroll_run {payroll_run_id} has not been disbursed yet")
    return conn.execute(
        text("UPDATE payslip SET issued_at = now() WHERE payroll_run_id = :r AND issued_at IS NULL "
             "RETURNING id"), {"r": payroll_run_id}).scalars().all()
