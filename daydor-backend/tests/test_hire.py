"""employee-record-writer: the hire flow's writer for employee/employment_record, and the full
create -> consent -> encrypt sequence that resolves the ordering conflict in finding 10."""
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import text

from daydor.agents.session import worker_session
from daydor.db.session import tenant_session
from daydor.hire.employee_record import handle_employee_record_writer, hire_employee, open_employment_record
from daydor.privacy.pii import decrypt_pii, encrypt_pii
from daydor.queue import Worker, enqueue
from tests.factories import insert


def _hire_kwargs(hire_org, hire_event_id):
    return dict(hire_event_id=hire_event_id, full_name="New Hire", work_email=f"{hire_event_id}@acme.test",
               employment_type="full_time", legal_entity_id=hire_org["legal_entity"],
               department_id=hire_org["department"], location_id=hire_org["location"], state_code="KA",
               date_of_joining=date(2026, 2, 1), date_of_birth=date(1995, 3, 10),
               personal_address="1 Infinite Loop, Bengaluru", aadhaar_last4="1234")


def test_hire_employee_is_idempotent_on_hire_event_id(engine, hire_org):
    kw = _hire_kwargs(hire_org, f"hire-{uuid.uuid4().hex[:10]}")
    tenant = hire_org["tenant"]

    with worker_session(engine, "employee-record-writer", tenant) as conn:
        a = hire_employee(conn, **kw)
    with worker_session(engine, "employee-record-writer", tenant) as conn:
        b = hire_employee(conn, **kw)
    assert a == b

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        full_name = conn.execute(text("SELECT full_name FROM employee WHERE id = :e"), {"e": a}).scalar_one()
    assert full_name == "New Hire"

    # pan_encrypted itself carries no grant for any role (ADR-002); check via the masked view.
    with tenant_session(engine, "tenant_founder", tenant) as conn:
        on_file = conn.execute(text("SELECT pan_encrypted_on_file FROM employee_masked WHERE id = :e"),
                               {"e": a}).scalar_one()
    assert on_file is False  # not yet collected


def test_hire_then_consent_then_encrypt(engine, hire_org):
    kw = _hire_kwargs(hire_org, f"hire-{uuid.uuid4().hex[:10]}")
    tenant = hire_org["tenant"]

    with worker_session(engine, "employee-record-writer", tenant) as conn:
        employee_id = hire_employee(conn, **kw)

    # consent_record can now reference the employee that exists.
    with engine.begin() as conn:
        insert(conn, "consent_record", tenant_id=tenant, employee_id=employee_id, data_category="pan",
              purpose="identity_verification", status="granted", granted_at="2026-02-01",
              consent_artifact_ref="doc-new-hire")

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        encrypt_pii(conn, "employee", "pan_encrypted", employee_id, "ABCDE1234F")
    with tenant_session(engine, "tenant_payroll", tenant) as conn:
        value = decrypt_pii(conn, "employee", "pan_encrypted", employee_id, "tax_filing")
    assert value == "ABCDE1234F"


def test_open_employment_record_is_idempotent(engine, hire_org):
    kw = _hire_kwargs(hire_org, f"hire-{uuid.uuid4().hex[:10]}")
    tenant, job_profile = hire_org["tenant"], hire_org["job_profile"]

    with worker_session(engine, "employee-record-writer", tenant) as conn:
        employee_id = hire_employee(conn, **kw)
        a = open_employment_record(conn, employee_id=employee_id, effective_from=date(2026, 2, 1),
                                   job_profile_id=job_profile, fte=Decimal("1.0"),
                                   ctc_annual=Decimal("1200000"), basic_da_monthly=Decimal("50000"),
                                   tax_regime_election="new", flsa_status="exempt")
        b = open_employment_record(conn, employee_id=employee_id, effective_from=date(2026, 2, 1),
                                   job_profile_id=job_profile, fte=Decimal("1.0"),
                                   ctc_annual=Decimal("1200000"), basic_da_monthly=Decimal("50000"),
                                   tax_regime_election="new", flsa_status="exempt")
    assert a == b


def test_employee_record_writer_queue_handler(engine, hire_org):
    kw = _hire_kwargs(hire_org, f"hire-{uuid.uuid4().hex[:10]}")
    tenant, job_profile = hire_org["tenant"], hire_org["job_profile"]

    payload = {"data": {
        "employee": {k: (str(v) if v is not None else None) for k, v in kw.items()},
        "employment_record": {"effective_from": "2026-02-01", "job_profile_id": str(job_profile),
                              "fte": "1.0", "ctc_annual": "1200000", "basic_da_monthly": "50000",
                              "tax_regime_election": "new", "flsa_status": "exempt"},
    }}
    with worker_session(engine, "employee-record-writer", tenant) as conn:
        enqueue(conn, "hr", "employee_record_writer", payload)

    w = Worker(engine, "hr", "w1")
    w.register("employee_record_writer", worker="employee-record-writer", fn=handle_employee_record_writer)
    outcome = w.tick()
    assert outcome["succeeded"] == 1

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        n = conn.execute(text("SELECT count(*) FROM employment_record er JOIN employee e "
                              "ON e.id = er.employee_id WHERE e.hire_event_id = :h"),
                         {"h": kw["hire_event_id"]}).scalar_one()
    assert n == 1
