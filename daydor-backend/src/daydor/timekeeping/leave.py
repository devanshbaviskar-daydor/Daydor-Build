"""pto-accrual-calculator: writes leave_balance from leave_policy.accrual_rule.

Scope simplification: `accrual_rule` is modelled as free-form jsonb; this reads a single
convention, `{"days_per_month": <number>}`, and computes simple linear accrual from the
employee's date_of_joining to `as_of`, capped at `carry_forward_cap`. No recurring scheduler
calls this yet (there is no monthly cron in this backend); it's callable on demand, the same way
daydor.hire.offer.make_offer is callable on demand rather than tied to a timer.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Connection, text


def accrue_leave(conn: Connection, *, employee_id: UUID, leave_policy_id: UUID, as_of: date) -> UUID:
    """Idempotent on (employee_id, leave_policy_id): recomputes and updates the single tracked
    balance for this employee/policy rather than appending a new row each time."""
    policy = conn.execute(text("SELECT accrual_rule, carry_forward_cap FROM leave_policy WHERE id = :p"),
                          {"p": leave_policy_id}).one()
    date_of_joining = conn.execute(text("SELECT date_of_joining FROM employee WHERE id = :e"),
                                   {"e": employee_id}).scalar_one()

    months_elapsed = Decimal((as_of.year - date_of_joining.year) * 12 + (as_of.month - date_of_joining.month))
    days_per_month = Decimal(str(policy.accrual_rule.get("days_per_month", 0)))
    balance_days = min(months_elapsed * days_per_month, policy.carry_forward_cap)

    existing = conn.execute(text("SELECT id FROM leave_balance WHERE employee_id = :e AND leave_policy_id = :p"),
                            {"e": employee_id, "p": leave_policy_id}).scalar_one_or_none()
    if existing is not None:
        conn.execute(text("UPDATE leave_balance SET balance_days = :b, as_of = :a WHERE id = :i"),
                    {"b": balance_days, "a": as_of, "i": existing})
        return existing
    return conn.execute(
        text("INSERT INTO leave_balance (employee_id, leave_policy_id, balance_days, as_of) "
             "VALUES (:e, :p, :b, :a) RETURNING id"),
        {"e": employee_id, "p": leave_policy_id, "b": balance_days, "a": as_of}).scalar_one()
