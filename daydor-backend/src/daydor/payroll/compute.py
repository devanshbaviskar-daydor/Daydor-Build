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

from sqlalchemy import Connection, Engine

from daydor.agents.session import worker_session
from daydor.payroll.garnishment import GarnishmentLine, compute_garnishments
from daydor.payroll.gross_pay import current_gross_pay
from daydor.payroll.tax_withholding import WithholdingLine, compute_withholding


@dataclass(frozen=True)
class GrossToNetResult:
    gross: Decimal
    withholding: list[WithholdingLine]
    garnishments: list[GarnishmentLine]
    net: Decimal


def after_withholding(gross: Decimal, withholding: list[WithholdingLine]) -> Decimal:
    return gross - sum((w.amount for w in withholding), Decimal("0"))


def assemble(gross: Decimal, withholding: list[WithholdingLine], garnishments: list[GarnishmentLine]) -> GrossToNetResult:
    net = after_withholding(gross, withholding) - sum((g.amount for g in garnishments), Decimal("0"))
    return GrossToNetResult(gross=gross, withholding=withholding, garnishments=garnishments, net=net)


def compute_gross_to_net(conn: Connection, *, employee_id: UUID, as_of: date) -> GrossToNetResult:
    """The whole computation on one connection (a payroll person's own session, or a test). A payroll run does
    not use this: it stages the same three steps across the workers that own them (`compute_staged`)."""
    gross = current_gross_pay(conn, employee_id=employee_id, as_of=as_of)
    withholding = compute_withholding(conn, employee_id=employee_id, gross=gross, as_of=as_of)
    garnishments = compute_garnishments(conn, employee_id=employee_id, base=after_withholding(gross, withholding),
                                        as_of=as_of)
    return assemble(gross, withholding, garnishments)


def compute_staged(engine: Engine, tenant_id: UUID, employee_ids: list[UUID], as_of: date, *,
                   user_id: UUID | None = None) -> dict[UUID, GrossToNetResult]:
    """Gross to net for many employees, one worker at a time: `gross-pay-calculator`, then
    `tax-withholding-calculator`, then `garnishment-processor`, each in its own transaction under its own
    database role (so each reads only what its scope allows). Pure reads: nothing is written, and the
    arithmetic is `compute_gross_to_net`'s, so the two agree."""
    with worker_session(engine, "gross-pay-calculator", tenant_id, user_id=user_id) as conn:
        gross = {e: current_gross_pay(conn, employee_id=e, as_of=as_of) for e in employee_ids}
    with worker_session(engine, "tax-withholding-calculator", tenant_id, user_id=user_id) as conn:
        withholding = {e: compute_withholding(conn, employee_id=e, gross=gross[e], as_of=as_of) for e in employee_ids}
    with worker_session(engine, "garnishment-processor", tenant_id, user_id=user_id) as conn:
        garnishments = {e: compute_garnishments(conn, employee_id=e, base=after_withholding(gross[e], withholding[e]),
                                                as_of=as_of) for e in employee_ids}
    return {e: assemble(gross[e], withholding[e], garnishments[e]) for e in employee_ids}
