"""Payroll run actions: build, anomaly pre-check, disbursal and payslip issuance.

Unlike Hire and Exit, Payroll is not driven through `WorkflowEngine` -- `payroll_run.status`
carries its own bookkeeping, and each step is a plain function in `daydor.payroll` the caller
invokes directly as the worker that owns it (`payroll-run-builder`, `direct-deposit-disburser`, `gl-poster`, ...),
not a queue-triggered handler reached through a state machine
(see `daydor.payroll.run_builder`'s module docstring). There is nothing to register in
`worker.py` for any of this; these endpoints are the only way these steps run.

`build_payroll_run` always needs to be followed by its own anomaly check before anything else can
happen (the soft gate is shadow-mode, so it always escalates -- see `daydor.payroll.anomaly`'s
module docstring), so `POST /runs` runs both (as two workers, in two transactions) in one call rather than making the caller chain two
requests with no real decision point in between.
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from daydor.payroll.anomaly import check_payroll_run
from daydor.payroll.disbursement import disburse_payroll_run, request_disbursal_approval
from daydor.payroll.gl_posting import open_journal_entry, post_journal_entry, request_gl_close_approval
from daydor.payroll.payslip_issuer import PayrollRunNotDisbursed, issue_payslips
from daydor.payroll.run_builder import build_payroll_run
from daydor.payroll.tax_filing import file_payroll_run
from daydor.payroll.tax_withholding import UnsupportedJurisdiction

from .. import access, idempotency
from ..deps import get_identity, idempotency_key
from ..errors import ApiError
from ..identity import Identity
from ..sessions import worker_session

router = APIRouter(prefix="/payroll", tags=["payroll"])


def _can_run_payroll(ident: Identity) -> bool:
    return access.table_level(access.table_or_404("payroll_run"), ident) >= 4


class CreateRun(BaseModel):
    legal_entity_id: UUID
    period_start: date
    period_end: date
    retention_class_id: UUID


@router.post("/runs", status_code=201)
def create_run(body: CreateRun, ident: Identity = Depends(get_identity), key: str | None = Depends(idempotency_key)):
    if not _can_run_payroll(ident):
        raise ApiError(403, "forbidden", "Your role cannot run payroll.")

    def run() -> dict:
        with worker_session(ident, "payroll-run-builder") as conn:
            built = build_payroll_run(conn, legal_entity_id=body.legal_entity_id, period_start=body.period_start,
                                      period_end=body.period_end, retention_class_id=body.retention_class_id)
        # The anomaly pre-check is its own worker (and its own transaction); build is idempotent on the period.
        with worker_session(ident, "payroll-anomaly-detector") as conn:
            outcome = check_payroll_run(conn, payroll_run_id=built["payroll_run_id"])
        return {
            "payroll_run_id": str(built["payroll_run_id"]), "payslip_ids": [str(p) for p in built["payslip_ids"]],
            "anomaly_check": {"effective_decision": outcome.effective_decision,
                              "approval_request_id": str(outcome.approval_request_id) if outcome.approval_request_id else None},
        }

    return idempotency.run(ident, "POST /payroll/runs", key, run)


@router.post("/runs/{run_id}/request-disbursal", status_code=202)
def request_disbursal(run_id: UUID, ident: Identity = Depends(get_identity), key: str | None = Depends(idempotency_key)):
    if not _can_run_payroll(ident):
        raise ApiError(403, "forbidden", "Your role cannot request disbursal.")

    def run() -> dict:
        with worker_session(ident, "direct-deposit-disburser") as conn:
            approval_id = request_disbursal_approval(conn, payroll_run_id=run_id)
        return {"approval_request_id": str(approval_id)}

    return idempotency.run(ident, f"POST /payroll/runs/{run_id}/request-disbursal", key, run)


class Disburse(BaseModel):
    approval_request_id: UUID


@router.post("/runs/{run_id}/disburse", status_code=200)
def disburse(run_id: UUID, body: Disburse, ident: Identity = Depends(get_identity), key: str | None = Depends(idempotency_key)):
    if not _can_run_payroll(ident):
        raise ApiError(403, "forbidden", "Your role cannot disburse payroll.")

    def run() -> dict:
        with worker_session(ident, "direct-deposit-disburser") as conn:
            try:
                disburse_payroll_run(conn, payroll_run_id=run_id, approval_request_id=body.approval_request_id)
            except Exception as exc:  # the database enforces this via app.enforce_gate_guard, not a Python check
                raise ApiError(409, "disbursal_not_approved",
                               "This payroll run cannot be disbursed without an approved g_pay_disburse request.") from exc
        return {"payroll_run_id": str(run_id), "status": "disbursed"}

    return idempotency.run(ident, f"POST /payroll/runs/{run_id}/disburse", key, run)


@router.post("/runs/{run_id}/issue-payslips", status_code=200)
def issue(run_id: UUID, ident: Identity = Depends(get_identity), key: str | None = Depends(idempotency_key)):
    if not _can_run_payroll(ident):
        raise ApiError(403, "forbidden", "Your role cannot issue payslips.")

    def run() -> dict:
        with worker_session(ident, "payslip-issuer") as conn:
            try:
                payslip_ids = issue_payslips(conn, payroll_run_id=run_id)
            except PayrollRunNotDisbursed as exc:
                raise ApiError(409, "not_disbursed", "This payroll run has not been disbursed yet.") from exc
        return {"payslip_ids": [str(p) for p in payslip_ids]}

    return idempotency.run(ident, f"POST /payroll/runs/{run_id}/issue-payslips", key, run)


class FileReturns(BaseModel):
    period: str  # "YYYY-MM"
    retention_class_id: UUID


@router.post("/runs/{run_id}/file", status_code=201)
def file_returns(run_id: UUID, body: FileReturns, ident: Identity = Depends(get_identity),
                 key: str | None = Depends(idempotency_key)):
    """One filing_record per statutory scheme for the run's jurisdiction -- illustrative scheme
    lists, same scope note as the tax-withholding computation (daydor.payroll.tax_filing)."""
    if not _can_run_payroll(ident):
        raise ApiError(403, "forbidden", "Your role cannot file returns.")

    def run() -> dict:
        with worker_session(ident, "tax-filing-submitter") as conn:
            try:
                filing_ids = file_payroll_run(conn, payroll_run_id=run_id, period=body.period,
                                              retention_class_id=body.retention_class_id)
            except UnsupportedJurisdiction as exc:
                raise ApiError(422, "unsupported_jurisdiction", str(exc)) from exc
        return {"filing_ids": [str(f) for f in filing_ids]}

    return idempotency.run(ident, f"POST /payroll/runs/{run_id}/file", key, run)


@router.post("/runs/{run_id}/gl", status_code=201)
def open_gl_entry(run_id: UUID, ident: Identity = Depends(get_identity), key: str | None = Depends(idempotency_key)):
    """Opens the run's summary journal entry and requests its g_close approval in one call --
    same reasoning as build run + anomaly check: nothing decides whether to open the entry, only
    whether to approve posting it."""
    if not _can_run_payroll(ident):
        raise ApiError(403, "forbidden", "Your role cannot post to the ledger.")

    def run() -> dict:
        with worker_session(ident, "gl-poster") as conn:
            gl_id = open_journal_entry(conn, payroll_run_id=run_id)
            approval_id = request_gl_close_approval(conn, gl_journal_entry_id=gl_id)
        return {"gl_journal_entry_id": str(gl_id), "approval_request_id": str(approval_id)}

    return idempotency.run(ident, f"POST /payroll/runs/{run_id}/gl", key, run)


class PostGl(BaseModel):
    approval_request_id: UUID


@router.post("/gl/{gl_id}/post", status_code=200)
def post_gl_entry(gl_id: UUID, body: PostGl, ident: Identity = Depends(get_identity),
                  key: str | None = Depends(idempotency_key)):
    if not _can_run_payroll(ident):
        raise ApiError(403, "forbidden", "Your role cannot post to the ledger.")

    def run() -> dict:
        with worker_session(ident, "gl-poster") as conn:
            try:
                post_journal_entry(conn, gl_journal_entry_id=gl_id, approval_request_id=body.approval_request_id)
            except Exception as exc:  # enforced by app.enforce_gate_guard, not a Python check
                raise ApiError(409, "close_not_approved",
                               "This journal entry cannot be posted without an approved g_close request.") from exc
        return {"gl_journal_entry_id": str(gl_id), "status": "posted"}

    return idempotency.run(ident, f"POST /payroll/gl/{gl_id}/post", key, run)
