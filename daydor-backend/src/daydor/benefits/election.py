"""election-processor: processes an employee's benefit choice into `benefit_election`.

Not employee self-service, despite `benefit_election`'s table-level grant showing `E: WRITE`:
`coverage_tier` and `employee_cost` are C2-class, and the employee's own column-level access to
both is READ, not WRITE (only HR/ops/agents can write them) -- the table-level grant is a
summary, not the real per-column picture. This matches the model naming a real worker
(`election-processor`) for this table, which the employee-direct-write tables (`consent_record`,
`time_punch`) do not have. The employee chooses a plan through some front end this backend
doesn't model; `election-processor` is what actually validates and writes the row."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Connection, text


def elect_benefit(conn: Connection, *, employee_id: UUID, benefit_plan_id: UUID, coverage_tier: str,
                  employee_cost: Decimal, effective_from: date) -> UUID:
    """Idempotent on (employee_id, benefit_plan_id, effective_from)."""
    existing = conn.execute(
        text("SELECT id FROM benefit_election WHERE employee_id = :e AND benefit_plan_id = :p "
             "AND effective_from = :f"), {"e": employee_id, "p": benefit_plan_id, "f": effective_from},
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    return conn.execute(
        text("INSERT INTO benefit_election (employee_id, benefit_plan_id, coverage_tier, "
             "employee_cost, effective_from) VALUES (:e, :p, :t, :c, :f) RETURNING id"),
        {"e": employee_id, "p": benefit_plan_id, "t": coverage_tier, "c": employee_cost,
         "f": effective_from}).scalar_one()
