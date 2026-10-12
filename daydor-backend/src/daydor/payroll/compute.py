"""Gross-to-net computation (docs/sprint-plan.md Sprint 7): component 8 in docs/backend-plan.md
("jurisdiction packs"), not started before this sprint.

**Scope boundary, discovered this sprint (finding 17): this module computes, it does not
persist.** `payslip_line.payslip_id` is NOT NULL, and `payslip.payroll_run_id` is NOT NULL --
exactly finding 15's shape again, one level down. A `payslip_line` cannot exist until a
`payroll_run` and a `payslip` exist, and those are Sprint 8's `payroll-run-builder`'s job (it
"ties Sprints 6-7 together", per the plan's own words -- the tying-together is itself the work
of persisting what this module computes). So `compute_gross_to_net` returns a plain
`GrossToNetResult`, not row ids. Sprint 8 calls it, creates the `payroll_run`/`payslip` rows,
and writes its `lines` into real `payslip_line` rows with the `payslip_id` filled in.

This mirrors `daydor.hire.workflow`'s own corrections: a sprint's job is to get the computation
or the state transition right, not to force a write that a later sprint's prerequisite row makes
impossible today.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Connection

from daydor.payroll.garnishment import GarnishmentLine, compute_garnishments
from daydor.payroll.gross_pay import current_gross_pay
from daydor.payroll.tax_withholding import WithholdingLine, compute_withholding


@dataclass(frozen=True)
class GrossToNetResult:
    gross: Decimal
    withholding: list[WithholdingLine]
    garnishments: list[GarnishmentLine]
    net: Decimal


def compute_gross_to_net(conn: Connection, *, employee_id: UUID, as_of: date) -> GrossToNetResult:
    gross = current_gross_pay(conn, employee_id=employee_id, as_of=as_of)
    withholding = compute_withholding(conn, employee_id=employee_id, gross=gross, as_of=as_of)
    after_withholding = gross - sum((w.amount for w in withholding), Decimal("0"))
    garnishments = compute_garnishments(conn, employee_id=employee_id, base=after_withholding, as_of=as_of)
    net = after_withholding - sum((g.amount for g in garnishments), Decimal("0"))
    return GrossToNetResult(gross=gross, withholding=withholding, garnishments=garnishments, net=net)
