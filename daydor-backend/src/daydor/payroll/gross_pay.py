"""gross-pay-calculator: the employee's monthly gross from their current employment_record.

Scope simplification: gross = ctc_annual / 12. `employment_record` has no separate "monthly base
salary" column (only the annual `ctc_annual` the hire flow sets from the accepted offer), and this
prototype doesn't model allowance breakdowns (HRA, bonuses, ...) -- a real payroll engine would.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Connection, text


def current_gross_pay(conn: Connection, *, employee_id: UUID, as_of) -> Decimal:
    """The gross for the employment_record effective on `as_of`."""
    ctc_annual = conn.execute(
        text("SELECT ctc_annual FROM employment_record WHERE employee_id = :e "
             "AND effective_from <= :d AND (effective_to IS NULL OR effective_to >= :d) "
             "ORDER BY effective_from DESC LIMIT 1"),
        {"e": employee_id, "d": as_of}).scalar_one()
    return (ctc_annual / Decimal(12)).quantize(Decimal("0.01"))
