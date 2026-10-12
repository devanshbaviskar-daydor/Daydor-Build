"""employee-record-writer: the hire flow's writer for `employee`, `employment_record` (and,
later, `payroll_profile`). See docs/model-findings.md finding 10 for why the 4 PII columns on
`employee` start NULL here and are populated afterwards through daydor.privacy.pii.encrypt_pii,
once consent_record rows exist to reference the now-created employee_id.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Connection, text

from daydor.queue import emit_event
from daydor.queue.worker import Job
from daydor.workflow.engine import WorkflowEngine


def hire_employee(conn: Connection, *, hire_event_id: str, full_name: str, work_email: str,
                  employment_type: str, legal_entity_id: UUID, department_id: UUID, location_id: UUID,
                  state_code: str, date_of_joining: date, date_of_birth: date, personal_address: str,
                  aadhaar_last4: str, position_id: UUID | None = None) -> UUID:
    """Create the employee row if hire_event_id has not been seen for this tenant before, and
    return its id either way. The 4 encrypted PII columns are left NULL; populate them with
    daydor.privacy.pii.encrypt_pii once consent_record rows exist for this employee."""
    row = conn.execute(
        text("INSERT INTO employee (hire_event_id, full_name, work_email, employment_type, "
             "legal_entity_id, department_id, location_id, position_id, state_code, date_of_joining, "
             "is_active, date_of_birth, personal_address, aadhaar_last4) "
             "VALUES (:hire_event_id, :full_name, :work_email, :employment_type, :legal_entity_id, "
             ":department_id, :location_id, :position_id, :state_code, :date_of_joining, true, "
             ":date_of_birth, :personal_address, :aadhaar_last4) "
             "ON CONFLICT (tenant_id, hire_event_id) DO NOTHING RETURNING id"),
        {"hire_event_id": hire_event_id, "full_name": full_name, "work_email": work_email,
         "employment_type": employment_type, "legal_entity_id": legal_entity_id,
         "department_id": department_id, "location_id": location_id, "position_id": position_id,
         "state_code": state_code, "date_of_joining": date_of_joining, "date_of_birth": date_of_birth,
         "personal_address": personal_address, "aadhaar_last4": aadhaar_last4},
    ).scalar_one_or_none()
    if row is not None:
        emit_event(conn, "employee.hired", "employee", row, {"hire_event_id": hire_event_id})
        return row
    return conn.execute(text("SELECT id FROM employee WHERE hire_event_id = :h"),
                        {"h": hire_event_id}).scalar_one()


def open_employment_record(conn: Connection, *, employee_id: UUID, effective_from: date,
                           job_profile_id: UUID, fte: Decimal, ctc_annual: Decimal,
                           basic_da_monthly: Decimal, tax_regime_election: str, flsa_status: str,
                           comp_band_id: UUID | None = None, wage_floor_compliant: bool = True,
                           other_allowances: dict | None = None) -> UUID:
    """Open the first (or a later) effective-dated employment_record for an employee. Idempotent
    on (employee_id, effective_from): re-running with the same date returns the existing row."""
    row = conn.execute(
        text("INSERT INTO employment_record (employee_id, effective_from, job_profile_id, comp_band_id, "
             "fte, ctc_annual, basic_da_monthly, other_allowances_json, wage_floor_compliant, "
             "tax_regime_election, flsa_status) "
             "VALUES (:employee_id, :effective_from, :job_profile_id, :comp_band_id, :fte, :ctc_annual, "
             ":basic_da_monthly, CAST(:other_allowances AS jsonb), :wage_floor_compliant, "
             ":tax_regime_election, :flsa_status) "
             "ON CONFLICT (tenant_id, employee_id, effective_from) DO NOTHING RETURNING id"),
        {"employee_id": employee_id, "effective_from": effective_from, "job_profile_id": job_profile_id,
         "comp_band_id": comp_band_id, "fte": fte, "ctc_annual": ctc_annual,
         "basic_da_monthly": basic_da_monthly, "other_allowances": json.dumps(other_allowances or {}),
         "wage_floor_compliant": wage_floor_compliant, "tax_regime_election": tax_regime_election,
         "flsa_status": flsa_status},
    ).scalar_one_or_none()
    if row is not None:
        emit_event(conn, "employment_record.opened", "employment_record", row,
                   {"employee_id": str(employee_id)})
        return row
    return conn.execute(
        text("SELECT id FROM employment_record WHERE employee_id = :e AND effective_from = :f"),
        {"e": employee_id, "f": effective_from}).scalar_one()


def open_payroll_profile(conn: Connection, *, employee_id: UUID, pay_frequency: str, payment_method: str,
                         work_state: str, tax_state: str, state_registration_status: str = "registered",
                         reciprocity_agreement_flag: bool = False, w4_elections: dict | None = None,
                         uan_number: str = "", esic_ip_number: str = "") -> UUID:
    """Idempotent on employee_id: one payroll_profile per employee. uan_number/esic_ip_number are
    India-specific and w4_elections is US-specific; whichever doesn't apply is left at its empty
    default rather than guessed at (see daydor.hire.workflow's finding-15 note)."""
    existing = conn.execute(text("SELECT id FROM payroll_profile WHERE employee_id = :e"),
                            {"e": employee_id}).scalar_one_or_none()
    if existing is not None:
        return existing
    return conn.execute(
        text("INSERT INTO payroll_profile (employee_id, pay_frequency, payment_method, work_state, "
             "tax_state, reciprocity_agreement_flag, state_registration_status, w4_elections, "
             "uan_number, esic_ip_number) "
             "VALUES (:e, :pf, :pm, :ws, :ts, :r, :sr, CAST(:w4 AS jsonb), :uan, :esic) RETURNING id"),
        {"e": employee_id, "pf": pay_frequency, "pm": payment_method, "ws": work_state, "ts": tax_state,
         "r": reciprocity_agreement_flag, "sr": state_registration_status,
         "w4": json.dumps(w4_elections or {}), "uan": uan_number, "esic": esic_ip_number},
    ).scalar_one()


def handle_employee_record_writer_create(engine: WorkflowEngine):
    """Queue handler for kind 'employee_record_writer_create' (hire flow step 10, queue 'hr').

    The model names the same worker (employee-record-writer) for both step 10 (`employee`) and
    step 11 (`employment_record`); distinct kind strings here avoid the two steps' enter_jobs
    colliding on one registered handler (see daydor.hire.workflow's module docstring).

    department_id comes from the requisition's own position, not context, since it's already in
    the database by this point and shouldn't be duplicated into every instance's context.
    """
    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        requisition_id = UUID(job.payload["subject_id"])
        department_id = conn.execute(
            text("SELECT p.department_id FROM job_requisition jr JOIN position p ON p.id = jr.position_id "
                 "WHERE jr.id = :r"), {"r": requisition_id}).scalar_one()
        employee_id = hire_employee(
            conn, hire_event_id=f"hire-{requisition_id}", full_name=ctx["full_name"],
            work_email=ctx["email"], employment_type=ctx["employment_type"],
            legal_entity_id=UUID(ctx["legal_entity_id"]), department_id=department_id,
            location_id=UUID(ctx["location_id"]), position_id=UUID(ctx["position_id"]),
            state_code=ctx["state_code"], date_of_joining=date.fromisoformat(ctx["target_start_date"]),
            date_of_birth=date.fromisoformat(ctx["date_of_birth"]), personal_address=ctx["personal_address"],
            aadhaar_last4=ctx["aadhaar_last4"])
        engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}",
                   context_patch={"employee_id": str(employee_id)})
        return {"employee_id": str(employee_id)}
    return handle


def handle_employee_record_writer_open(engine: WorkflowEngine):
    """Queue handler for kind 'employee_record_writer_open' (hire flow step 11, queue 'hr').

    job_profile_id comes from the requisition's own position, same reasoning as department_id in
    handle_employee_record_writer_create. ctc_annual is the offer's own proposed_base: this
    prototype does not model a separate post-offer comp-finalization step (see
    docs/sprint-plan.md's hire-flow scope notes).
    """
    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        requisition_id = UUID(job.payload["subject_id"])
        job_profile_id, flsa_status = conn.execute(
            text("SELECT p.job_profile_id, jp.flsa_default FROM job_requisition jr "
                 "JOIN position p ON p.id = jr.position_id JOIN job_profile jp ON jp.id = p.job_profile_id "
                 "WHERE jr.id = :r"), {"r": requisition_id}).one()
        employment_record_id = open_employment_record(
            conn, employee_id=UUID(ctx["employee_id"]), effective_from=date.fromisoformat(ctx["target_start_date"]),
            job_profile_id=job_profile_id, comp_band_id=UUID(ctx["comp_band_id"]), fte=Decimal("1.0"),
            ctc_annual=Decimal(str(ctx["proposed_base"])), basic_da_monthly=Decimal(str(ctx["basic_da_monthly"])),
            tax_regime_election=ctx["tax_regime_election"], flsa_status=flsa_status)
        engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}",
                   context_patch={"employment_record_id": str(employment_record_id)})
        return {"employment_record_id": str(employment_record_id)}
    return handle


def handle_employee_record_writer_payroll(engine: WorkflowEngine):
    """Queue handler for kind 'employee_record_writer_payroll' (hire flow step 18, queue 'pay').
    Third split of the same model worker, same reasoning as _create/_open above."""
    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        payroll_profile_id = open_payroll_profile(
            conn, employee_id=UUID(ctx["employee_id"]), pay_frequency=ctx["pay_frequency"],
            payment_method=ctx["payment_method"], work_state=ctx["work_state"], tax_state=ctx["tax_state"],
            uan_number=ctx.get("uan_number", ""), esic_ip_number=ctx.get("esic_ip_number", ""),
            w4_elections=ctx.get("w4_elections"))
        engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}",
                   context_patch={"payroll_profile_id": str(payroll_profile_id)})
        return {"payroll_profile_id": str(payroll_profile_id)}
    return handle


def handle_employee_record_writer(conn: Connection, job: Job) -> dict:
    """Queue handler for kind 'employee_record_writer' (queue 'hr', role agent_hr). Expects the
    hire_employee()/open_employment_record() keyword arguments nested under job.payload["data"]:
    {"employee": {...}, "employment_record": {...}}. The generated hire-flow skeleton does not
    yet carry this payload on its own (see daydor.workflow.definitions); callers that enqueue
    this job directly must supply it."""
    data = job.payload.get("data", {})
    employee_id = hire_employee(conn, **data["employee"])
    open_employment_record(conn, employee_id=employee_id, **data["employment_record"])
    return {"employee_id": str(employee_id)}
