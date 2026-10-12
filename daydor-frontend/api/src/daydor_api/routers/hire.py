from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from daydor.hire.workflow import start_hire
from daydor.workflow.engine import WorkflowEngine, WorkflowError

from .. import access, idempotency
from ..deps import get_identity, idempotency_key
from ..errors import ApiError
from ..identity import Identity
from ..sessions import agent_session

router = APIRouter(prefix="/hire", tags=["hire"])
_ENGINE = WorkflowEngine()


class StartHire(BaseModel):
    """What the backend's start_hire needs today. Interview time and the offer inputs are read from
    the workflow context by later steps (a Sprint 2 simplification), so they are collected here.

    The fields below `proposed_equity` are read the same way, later still: by the employee/
    employment_record writers (steps 10-11) and the payroll-profile writer (step 18). A real system
    would collect these at offer acceptance, not at the start of the hire; this prototype has no
    such step, so -- same simplification, pushed one step further -- they ride in context from the
    start too (see docs/integration-notes.md). Optional here: a hire can still run up through the
    offer without them, it will just fail at employee creation if they're missing by then."""
    position_id: UUID
    hiring_manager_id: UUID
    target_start_date: date
    channel: str = "company_site"
    pay_range_min: Decimal
    pay_range_max: Decimal
    interviewer_employee_id: UUID | None = None
    scheduled_at: datetime | None = None
    comp_band_id: UUID | None = None
    proposed_base: Decimal | None = None
    proposed_equity: Decimal | None = None
    # employee (step 10) / employment_record (step 11)
    legal_entity_id: UUID | None = None
    location_id: UUID | None = None
    state_code: str | None = None
    employment_type: str | None = None
    date_of_birth: date | None = None
    personal_address: str | None = None
    aadhaar_last4: str | None = None
    basic_da_monthly: Decimal | None = None
    tax_regime_election: str | None = None
    # document (step 13) -- retention_class is, despite the name, a retention_policy id: global,
    # admin-entered reference data (daydor.hire.documents's module docstring), not computed here.
    retention_class_id: UUID | None = None
    # payroll_profile (step 18)
    pay_frequency: str | None = None
    payment_method: str | None = None
    work_state: str | None = None
    tax_state: str | None = None
    uan_number: str | None = None
    esic_ip_number: str | None = None


@router.post("/start", status_code=201)
def start(body: StartHire, ident: Identity = Depends(get_identity), key: str | None = Depends(idempotency_key)):
    t = access.table_or_404("job_requisition")
    if access.table_level(t, ident) < 4:
        raise ApiError(403, "forbidden", "Your role cannot open a requisition.")
    if body.pay_range_min > body.pay_range_max:
        raise ApiError(422, "check_violation", "The pay range minimum cannot be above the maximum.")

    def run() -> dict:
        extra = {"channel": body.channel, "pay_range_min": str(body.pay_range_min),
                 "pay_range_max": str(body.pay_range_max)}
        if body.interviewer_employee_id:
            extra["interviewer_employee_id"] = str(body.interviewer_employee_id)
        if body.scheduled_at:
            extra["scheduled_at"] = body.scheduled_at.isoformat()
        if body.comp_band_id:
            extra["comp_band_id"] = str(body.comp_band_id)
        if body.proposed_base is not None:
            extra["proposed_base"] = str(body.proposed_base)
        if body.proposed_equity is not None:
            extra["proposed_equity"] = str(body.proposed_equity)
        for field in ("legal_entity_id", "location_id", "state_code", "employment_type", "date_of_birth",
                     "personal_address", "aadhaar_last4", "basic_da_monthly", "tax_regime_election",
                     "retention_class_id", "pay_frequency", "payment_method", "work_state", "tax_state",
                     "uan_number", "esic_ip_number"):
            value = getattr(body, field)
            if value is not None:
                extra[field] = str(value)
        # Workflow instances can only be inserted by agent roles, so this runs as agent_ta with the
        # person's user id in the session. Nothing here uses an elevated role.
        with agent_session(ident, "agent_ta") as conn:
            # A position can have one hire in progress. A second start (a double click, or two people)
            # gets the existing one back instead of an error.
            existing = conn.execute(text(
                "SELECT wi.id, wi.subject_id FROM app.workflow_instance wi "
                "JOIN public.job_requisition jr ON jr.id = wi.subject_id "
                "WHERE wi.definition_name = 'hire' AND jr.position_id = :p "
                "AND wi.status IN ('running', 'waiting_gate') ORDER BY wi.created_at LIMIT 1"),
                {"p": body.position_id}).first()
            if existing:
                return {"instance_id": str(existing.id), "requisition_id": str(existing.subject_id), "existing": True}
            try:
                instance_id = start_hire(conn, _ENGINE, position_id=body.position_id,
                                         hiring_manager_id=body.hiring_manager_id,
                                         target_start_date=body.target_start_date, **extra)
            except WorkflowError:
                raise ApiError(409, "hire_in_progress", "A hire is already in progress for this position.")
            requisition_id = conn.execute(text("SELECT subject_id FROM app.workflow_instance WHERE id = :i"),
                                          {"i": instance_id}).scalar_one()
        return {"instance_id": str(instance_id), "requisition_id": str(requisition_id)}

    return idempotency.run(ident, "POST /hire/start", key, run)
