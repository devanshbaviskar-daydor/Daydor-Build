"""Time, leave, benefits and expenses (FE-7).

`time_punch` is employee self-service by design (direct write, see access.py's DIRECT_WRITE_TABLES)
and needs no endpoint here. `validate_timecard` (punches -> a timecard) and `accrue_leave` are
plain functions run as `agent_time`, same as the backend's own tests, not queue handlers -- there
is no domain agent to register in worker.py for either. `elect_benefit` is real backend logic
(`agent_ben`), despite `benefit_election`'s table grant looking like self-service (finding 16: the
employee's own column access on `coverage_tier`/`employee_cost` is READ, not WRITE).

`expense` has no backend service at all: the model names workers
(`expense-policy-checker`, `expense-approval-router`) but no Python module implements either, even
though the table carries a real `E: WRITE` grant and `g_expense` is a registered platform gate
(`docs/model-findings.md` finding 9's `g_timecard` fix went in; `g_expense` was added at the same
time but nothing was ever built to raise it). `approval_request`'s own grant doesn't give an
employee INSERT access, so this endpoint does both the insert and the gate request in one
`agent_hr` session, the same shape as `daydor.hire.consent.request_consent`'s gap-fill.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from daydor.benefits.election import elect_benefit
from daydor.gates.hard import request_approval
from daydor.timekeeping.leave import accrue_leave
from daydor.timekeeping.timecard import route_for_approval, validate_timecard

from .. import access, idempotency
from ..deps import get_identity, idempotency_key
from ..errors import ApiError
from ..identity import Identity
from ..sessions import agent_session

router = APIRouter(tags=["timekeeping"])


def _self_or_manages(ident: Identity, employee_id: UUID) -> bool:
    return ident.role in ("tenant_hr", "tenant_founder", "daydor_ops") or str(ident.employee_id) == str(employee_id) \
        or ident.role == "tenant_manager"


class TimecardBody(BaseModel):
    employee_id: UUID
    period_start: date
    period_end: date


@router.post("/timekeeping/timecards", status_code=201)
def create_timecard(body: TimecardBody, ident: Identity = Depends(get_identity),
                    key: str | None = Depends(idempotency_key)):
    """Turns this period's punches into a timecard and raises it for the manager's g_timecard
    approval in one call -- there is no decision point in between; a timecard is always routed."""
    if not _self_or_manages(ident, body.employee_id):
        raise ApiError(403, "forbidden", "You can only build your own timecard.")

    def run() -> dict:
        with agent_session(ident, "agent_time") as conn:
            timecard_id = validate_timecard(conn, employee_id=body.employee_id,
                                            period_start=body.period_start, period_end=body.period_end)
            approval_id = route_for_approval(conn, timecard_id=timecard_id)
        return {"timecard_id": str(timecard_id), "approval_request_id": str(approval_id)}

    return idempotency.run(ident, "POST /timekeeping/timecards", key, run)


class AccrueBody(BaseModel):
    employee_id: UUID
    leave_policy_id: UUID
    as_of: date


@router.post("/timekeeping/leave-balances/accrue", status_code=200)
def accrue(body: AccrueBody, ident: Identity = Depends(get_identity)):
    if ident.role not in ("tenant_hr", "tenant_founder", "daydor_ops"):
        raise ApiError(403, "forbidden", "Your role cannot run leave accrual.")
    with agent_session(ident, "agent_time") as conn:
        balance_id = accrue_leave(conn, employee_id=body.employee_id, leave_policy_id=body.leave_policy_id,
                                  as_of=body.as_of)
    return {"leave_balance_id": str(balance_id)}


class ElectBody(BaseModel):
    employee_id: UUID
    benefit_plan_id: UUID
    coverage_tier: str
    employee_cost: Decimal
    effective_from: date


@router.post("/benefits/elections", status_code=201)
def elect(body: ElectBody, ident: Identity = Depends(get_identity), key: str | None = Depends(idempotency_key)):
    """The employee chooses a plan through this endpoint, but the write runs as agent_ben, not
    their own session -- finding 16: coverage_tier/employee_cost are C2-class, READ-only for the
    employee's own column access despite the table-level grant looking like self-service."""
    if not _self_or_manages(ident, body.employee_id):
        raise ApiError(403, "forbidden", "You can only elect your own benefits.")

    def run() -> dict:
        with agent_session(ident, "agent_ben") as conn:
            election_id = elect_benefit(conn, employee_id=body.employee_id, benefit_plan_id=body.benefit_plan_id,
                                        coverage_tier=body.coverage_tier, employee_cost=body.employee_cost,
                                        effective_from=body.effective_from)
        return {"benefit_election_id": str(election_id)}

    return idempotency.run(ident, "POST /benefits/elections", key, run)


class ExpenseBody(BaseModel):
    amount: Decimal
    category: str
    receipt_document_id: UUID | None = None


@router.post("/expenses", status_code=201)
def submit_expense(body: ExpenseBody, ident: Identity = Depends(get_identity),
                   key: str | None = Depends(idempotency_key)):
    if ident.employee_id is None:
        raise ApiError(403, "forbidden", "Only an employee can submit an expense.")
    if access.table_level(access.table_or_404("expense"), ident) < 4:
        raise ApiError(403, "forbidden", "Your role cannot submit expenses.")

    def run() -> dict:
        with agent_session(ident, "agent_hr") as conn:
            expense_id = conn.execute(text(
                "INSERT INTO expense (employee_id, amount, category, receipt_document_id, policy_flags) "
                "VALUES (:e, :a, :c, :r, '{}'::jsonb) RETURNING id"),
                {"e": ident.employee_id, "a": body.amount, "c": body.category, "r": body.receipt_document_id},
            ).scalar_one()
            approval_id = request_approval(conn, "g_expense", "expense", expense_id)
        return {"expense_id": str(expense_id), "approval_request_id": str(approval_id)}

    return idempotency.run(ident, "POST /expenses", key, run)
