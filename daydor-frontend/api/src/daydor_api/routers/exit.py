"""Exit flow actions: start, and the three steps that are real hard gates but -- unlike every
Hire-flow gate -- not engine-level transition gates (daydor.exit.workflow's module docstring):
`g_it_deprov`, `g_pay_disburse` and `g_cobra` each guard a column on a row that isn't the
workflow's own fixed subject (`identity_account`/`final_settlement`/`cobra_event`, not
`termination`). Their queue handlers only *raise* the approval automatically; the matching
`deprovision_identity`/`disburse_final_settlement`/`send_cobra_notice` functions are what actually
advance the instance, each reachable only once its own guarded write has succeeded -- so these
three endpoints are the only actions a person triggers here. Everything else (legal hold check,
checklist, device return, final settlement calculation, COBRA detection, closeout) runs
automatically once the workflow enters that state, the same as most of Hire.
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from daydor.exit.cobra import send_cobra_notice
from daydor.exit.deprovisioning import deprovision_identity
from daydor.exit.final_settlement import disburse_final_settlement
from daydor.exit.workflow import start_exit
from daydor.workflow.engine import WorkflowEngine, WorkflowError

from .. import access, idempotency
from ..deps import get_identity, idempotency_key
from ..errors import ApiError
from ..identity import Identity
from ..sessions import worker_session

router = APIRouter(prefix="/exit", tags=["exit"])
_ENGINE = WorkflowEngine()


def _instance_id_for_employee(conn, employee_id) -> UUID:
    return conn.execute(text(
        "SELECT wi.id FROM app.workflow_instance wi JOIN public.termination t ON t.id = wi.subject_id "
        "WHERE wi.definition_name = 'exit' AND wi.subject_table = 'termination' AND t.employee_id = :e "
        "ORDER BY wi.created_at DESC LIMIT 1"), {"e": employee_id}).scalar_one()


class StartExit(BaseModel):
    employee_id: UUID
    termination_type: str
    reason_code: str
    notice_date: date
    last_working_day: date


@router.post("/start", status_code=201)
def start(body: StartExit, ident: Identity = Depends(get_identity), key: str | None = Depends(idempotency_key)):
    if ident.role not in ("tenant_hr", "tenant_founder"):
        raise ApiError(403, "forbidden", "Your role cannot initiate a termination.")

    def run() -> dict:
        with worker_session(ident, "exit-intake") as conn:
            # start_exit's `initiate_termination` is idempotent on employee_id (returns the
            # existing row rather than raising), but start_exit itself is not: it unconditionally
            # fires "advance" twice with no event_id after engine.start(), which for an
            # already-existing instance skips fire()'s own duplicate check (only applied when an
            # event_id is given) and blindly advances the CURRENT state by two steps regardless of
            # what it is -- corrupting an in-progress exit. Short-circuit before ever reaching that
            # path for a duplicate call.
            existing = conn.execute(text("SELECT 1 FROM termination WHERE employee_id = :e"),
                                    {"e": body.employee_id}).first()
            if existing is not None:
                raise ApiError(409, "exit_in_progress", "An exit is already in progress for this employee.")
            try:
                instance_id = start_exit(conn, _ENGINE, employee_id=body.employee_id,
                                         termination_type=body.termination_type, reason_code=body.reason_code,
                                         notice_date=body.notice_date, last_working_day=body.last_working_day,
                                         initiated_by_user_id=ident.user_id)
            except WorkflowError:
                raise ApiError(409, "exit_in_progress", "An exit is already in progress for this employee.")
            termination_id = conn.execute(text("SELECT subject_id FROM app.workflow_instance WHERE id = :i"),
                                          {"i": instance_id}).scalar_one()
        return {"instance_id": str(instance_id), "termination_id": str(termination_id)}

    return idempotency.run(ident, "POST /exit/start", key, run)


class WithApproval(BaseModel):
    approval_request_id: UUID


@router.post("/identity-accounts/{identity_account_id}/deprovision", status_code=200)
def deprovision(identity_account_id: UUID, body: WithApproval, ident: Identity = Depends(get_identity),
               key: str | None = Depends(idempotency_key)):
    if ident.role not in ("tenant_it", "daydor_ops"):
        raise ApiError(403, "forbidden", "Your role cannot deprovision this identity.")

    def run() -> dict:
        with worker_session(ident, "deprovisioning-agent") as conn:
            employee_id = conn.execute(text("SELECT employee_id FROM identity_account WHERE id = :i"),
                                       {"i": identity_account_id}).scalar_one()
            instance_id = _instance_id_for_employee(conn, employee_id)
            try:
                deprovision_identity(conn, _ENGINE, instance_id, identity_account_id=identity_account_id,
                                     approval_request_id=body.approval_request_id)
            except Exception as exc:  # enforced by app.enforce_gate_guard, not a Python check
                raise ApiError(409, "deprovisioning_not_approved",
                               "This identity cannot be deprovisioned without an approved g_it_deprov request.") from exc
        return {"identity_account_id": str(identity_account_id), "status": "deprovisioned"}

    return idempotency.run(ident, f"POST /exit/identity-accounts/{identity_account_id}/deprovision", key, run)


@router.post("/final-settlements/{final_settlement_id}/disburse", status_code=200)
def disburse(final_settlement_id: UUID, body: WithApproval, ident: Identity = Depends(get_identity),
            key: str | None = Depends(idempotency_key)):
    if not (access.table_level(access.table_or_404("final_settlement"), ident) >= 4):
        raise ApiError(403, "forbidden", "Your role cannot disburse a final settlement.")

    def run() -> dict:
        with worker_session(ident, "direct-deposit-disburser") as conn:
            employee_id = conn.execute(text("SELECT employee_id FROM final_settlement WHERE id = :i"),
                                       {"i": final_settlement_id}).scalar_one()
            instance_id = _instance_id_for_employee(conn, employee_id)
            try:
                disburse_final_settlement(conn, _ENGINE, instance_id, final_settlement_id=final_settlement_id,
                                          approval_request_id=body.approval_request_id)
            except Exception as exc:
                raise ApiError(409, "disbursal_not_approved",
                               "This settlement cannot be disbursed without an approved g_pay_disburse request.") from exc
        return {"final_settlement_id": str(final_settlement_id), "status": "disbursed"}

    return idempotency.run(ident, f"POST /exit/final-settlements/{final_settlement_id}/disburse", key, run)


@router.post("/cobra-events/{cobra_event_id}/send-notice", status_code=200)
def send_notice(cobra_event_id: UUID, body: WithApproval, ident: Identity = Depends(get_identity),
                key: str | None = Depends(idempotency_key)):
    if ident.role != "tenant_hr":
        raise ApiError(403, "forbidden", "Your role cannot send a COBRA notice.")

    def run() -> dict:
        with worker_session(ident, "cobra-notice-generator") as conn:
            employee_id = conn.execute(text("SELECT employee_id FROM cobra_event WHERE id = :i"),
                                       {"i": cobra_event_id}).scalar_one()
            instance_id = _instance_id_for_employee(conn, employee_id)
            try:
                send_cobra_notice(conn, _ENGINE, instance_id, cobra_event_id=cobra_event_id,
                                  approval_request_id=body.approval_request_id)
            except Exception as exc:
                raise ApiError(409, "notice_not_approved",
                               "This COBRA notice cannot be sent without an approved g_cobra request.") from exc
        return {"cobra_event_id": str(cobra_event_id), "status": "notice_sent"}

    return idempotency.run(ident, f"POST /exit/cobra-events/{cobra_event_id}/send-notice", key, run)
