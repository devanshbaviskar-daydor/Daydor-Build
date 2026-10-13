"""FE-11/FE-12: a termination driven end to end through the real API, queue workers and Postgres
-- legal hold check (not active), checklist, deprovisioning (g_it_deprov), device return, final
settlement (g_finalpay, then disbursal through g_pay_disburse -- the same pattern Payroll's own
disbursal uses, reused here per daydor.exit.workflow's module docstring), COBRA (US only), and
closeout. Unlike every Hire-flow gate, g_it_deprov/g_pay_disburse/g_cobra are not engine-level
transition gates: their queue handlers only raise the approval, and a dedicated endpoint (not the
queue) is what completes the guarded write and advances the instance -- see exit.py's module
docstring."""
import uuid
from datetime import date

from conftest import run_workers


def _hdr(h):
    return {**h, "Idempotency-Key": str(uuid.uuid4())}


def _hire_test_employee(engine, tenant, legal_entity, department, location, name, ctc=1800000):
    """A fully-provisioned employee ready to be exited, without driving the whole Hire flow first
    -- same shape as the backend's own `exit_org` fixture (tests/exit_helpers.py): an
    identity_account and app_access_grant (deprovisioning has nothing to revoke otherwise -- the
    exit flow assumes someone who exists this far along already has an identity), a device
    assignment (device return), and a gratuity balance (final settlement reads it)."""
    from sqlalchemy import text

    from daydor.agents.session import worker_session
    from daydor.db.session import tenant_session
    from daydor.hire.employee_record import hire_employee, open_employment_record

    with worker_session(engine, "employee-record-writer", tenant) as conn:
        employee_id = hire_employee(
            conn, hire_event_id=f"exit-test-{uuid.uuid4().hex[:10]}", full_name=name,
            work_email=f"{name.split()[0].lower()}.{uuid.uuid4().hex[:6]}@example.test",
            employment_type="full_time", legal_entity_id=legal_entity, department_id=department,
            location_id=location, state_code="KA", date_of_joining=date(2024, 1, 1),
            date_of_birth=date(1992, 6, 1), personal_address="1 Test Lane", aadhaar_last4="1234")
    with tenant_session(engine, "tenant_hr", tenant) as conn:
        job_profile = conn.execute(text("SELECT id FROM job_profile LIMIT 1")).scalar_one()
    with worker_session(engine, "employee-record-writer", tenant) as conn:
        open_employment_record(conn, employee_id=employee_id, effective_from=date(2024, 1, 1),
                               job_profile_id=job_profile, fte="1.0", ctc_annual=str(ctc),
                               basic_da_monthly=str(ctc / 24), tax_regime_election="new", flsa_status="exempt")
    with engine.begin() as conn:
        identity_account = conn.execute(text(
            "INSERT INTO identity_account (tenant_id, employee_id, directory_provider, external_id, "
            "status, provisioned_at) VALUES (:t, :e, 'fake-idp', :x, 'active', now()) RETURNING id"),
            {"t": tenant, "e": employee_id, "x": f"ext-{uuid.uuid4().hex[:8]}"}).scalar_one()
        conn.execute(text(
            "INSERT INTO app_access_grant (tenant_id, identity_account_id, app_name, permission_level, "
            "source, granted_at) VALUES (:t, :i, 'email', 'standard', 'template', now())"),
            {"t": tenant, "i": identity_account})
        device = conn.execute(text(
            "INSERT INTO device (tenant_id, asset_tag, model, serial_no, status, purchase_cost) "
            "VALUES (:t, :a, 'Laptop', :s, 'assigned', 80000) RETURNING id"),
            {"t": tenant, "a": f"AT-{uuid.uuid4().hex[:6]}", "s": uuid.uuid4().hex[:10]}).scalar_one()
        conn.execute(text(
            "INSERT INTO device_assignment (tenant_id, device_id, employee_id, assigned_at) "
            "VALUES (:t, :d, :e, now())"), {"t": tenant, "d": device, "e": employee_id})
        conn.execute(text(
            "INSERT INTO gratuity_accrual_balance (tenant_id, employee_id, as_of_period, accrued_amount, "
            "gratuity_wage_base) VALUES (:t, :e, '2026-06-30', 50000, 50000)"),
            {"t": tenant, "e": employee_id})
    return employee_id


def _tenant_and_geo(client, people, country_code):
    tenant_id = client.get("/api/auth/me", headers=people["hr"]).json()["tenant_id"]
    loc = next(l for l in client.get("/api/tables/location", headers=people["hr"]).json()["rows"] if l["country_code"] == country_code)
    dept = client.get("/api/tables/department", headers=people["hr"]).json()["rows"][0]
    return tenant_id, loc["legal_entity_id"], dept["id"], loc["id"]


def test_termination_through_closeout_us_employee_with_cobra(client, people, engine):
    tenant_id, legal_entity, department, location = _tenant_and_geo(client, people, "US")
    employee_id = str(_hire_test_employee(engine, tenant_id, legal_entity, department, location, "Jamie Fox"))

    started = client.post("/api/exit/start", headers=_hdr(people["hr"]), json={
        "employee_id": employee_id, "termination_type": "voluntary", "reason_code": "resignation",
        "notice_date": "2026-11-01", "last_working_day": "2026-11-15"})
    assert started.status_code == 201, started.text
    rid = started.json()["termination_id"]

    # Employees and managers cannot start a termination.
    denied = client.post("/api/exit/start", headers=_hdr(people["employee"]), json={
        "employee_id": employee_id, "termination_type": "voluntary", "reason_code": "resignation",
        "notice_date": "2026-11-01", "last_working_day": "2026-11-15"})
    assert denied.status_code == 403

    replay = client.post("/api/exit/start", headers=_hdr(people["hr"]), json={
        "employee_id": employee_id, "termination_type": "voluntary", "reason_code": "resignation",
        "notice_date": "2026-11-01", "last_working_day": "2026-11-15"})
    assert replay.status_code == 409 or replay.json().get("termination_id") == rid

    run_workers(6)  # legal_hold_checker (no hold) -> checklist -> deprovisioning_agent raises g_it_deprov

    identity_account_id = client.get("/api/tables/identity_account", headers=people["it"],
                                     params={"employee_id": employee_id}).json()["rows"][0]["id"]
    pending = client.get("/api/approvals", headers=people["it"], params={"status": "pending", "subject_id": identity_account_id}).json()["approvals"]
    deprov_gate = next(a for a in pending if a["gate_type"] == "g_it_deprov")
    assert deprov_gate["can_resolve"] is True  # tenant_it is an allowed approver

    resolved = client.post(f"/api/approvals/{deprov_gate['id']}/resolve", headers=people["it"], json={"decision": "approved"})
    assert resolved.status_code == 200, resolved.text

    denied_deprov = client.post(f"/api/exit/identity-accounts/{identity_account_id}/deprovision", headers=_hdr(people["hr"]),
                                json={"approval_request_id": deprov_gate["id"]})
    assert denied_deprov.status_code == 403

    deprovisioned = client.post(f"/api/exit/identity-accounts/{identity_account_id}/deprovision", headers=_hdr(people["it"]),
                                json={"approval_request_id": deprov_gate["id"]})
    assert deprovisioned.status_code == 200, deprovisioned.text

    run_workers(6)  # equipment_return_tracker -> final_pay_calculator raises g_finalpay

    pending = client.get("/api/approvals", headers=people["founder"], params={"status": "pending", "subject_id": rid}).json()["approvals"]
    finalpay_gate = next(a for a in pending if a["gate_type"] == "g_finalpay")
    resolved = client.post(f"/api/approvals/{finalpay_gate['id']}/resolve", headers=people["founder"], json={"decision": "approved"})
    assert resolved.status_code == 200, resolved.text

    run_workers(6)  # final_settlement_opener -> direct_deposit_disburser raises g_pay_disburse

    final_settlement_id = client.get("/api/tables/final_settlement", headers=people["payroll"],
                                     params={"employee_id": employee_id}).json()["rows"][0]["id"]
    pending = client.get("/api/approvals", headers=people["founder"], params={"status": "pending", "subject_id": final_settlement_id}).json()["approvals"]
    disburse_gate = next(a for a in pending if a["gate_type"] == "g_pay_disburse")
    resolved = client.post(f"/api/approvals/{disburse_gate['id']}/resolve", headers=people["founder"], json={"decision": "approved"})
    assert resolved.status_code == 200, resolved.text

    too_early = client.post(f"/api/exit/final-settlements/{final_settlement_id}/disburse", headers=_hdr(people["payroll"]),
                            json={"approval_request_id": deprov_gate["id"]})  # wrong approval, same shape as payroll's 409 check
    assert too_early.status_code == 409

    disbursed = client.post(f"/api/exit/final-settlements/{final_settlement_id}/disburse", headers=_hdr(people["payroll"]),
                            json={"approval_request_id": disburse_gate["id"]})
    assert disbursed.status_code == 200, disbursed.text

    run_workers(6)  # cobra_trigger_detector (US employee) raises g_cobra

    cobra_event_id = client.get("/api/tables/cobra_event", headers=people["hr"],
                                params={"employee_id": employee_id}).json()["rows"][0]["id"]
    pending = client.get("/api/approvals", headers=people["hr"], params={"status": "pending", "subject_id": cobra_event_id}).json()["approvals"]
    cobra_gate = next(a for a in pending if a["gate_type"] == "g_cobra")
    resolved = client.post(f"/api/approvals/{cobra_gate['id']}/resolve", headers=people["hr"], json={"decision": "approved"})
    assert resolved.status_code == 200, resolved.text

    sent = client.post(f"/api/exit/cobra-events/{cobra_event_id}/send-notice", headers=_hdr(people["hr"]),
                       json={"approval_request_id": cobra_gate["id"]})
    assert sent.status_code == 200, sent.text

    run_workers(6)  # employee_closeout

    instance = client.get("/api/workflows/instances", headers=people["hr"], params={"subject_id": rid}).json()["instances"][0]
    assert instance["state"] == "done" and instance["status"] == "completed"

    employee = client.get("/api/tables/employee", headers=people["hr"], params={"id": employee_id}).json()["rows"][0]
    assert employee["is_active"] is False and employee["date_of_exit"] is not None

    settlement = client.get("/api/tables/final_settlement", headers=people["payroll"], params={"id": final_settlement_id}).json()["rows"][0]
    assert settlement["disbursed_at"] is not None
    assert float(settlement["total_settlement"]) == float(settlement["pending_wages"]) + float(settlement["gratuity_payout"]) + float(settlement["leave_encashment"]) - float(settlement["recoveries"])


def test_an_active_legal_hold_blocks_deprovisioning(client, people, engine):
    tenant_id, legal_entity, department, location = _tenant_and_geo(client, people, "IN")
    employee_id = str(_hire_test_employee(engine, tenant_id, legal_entity, department, location, "Riya Shah"))

    hr_user = client.get("/api/auth/me", headers=people["hr"]).json()["user_id"]
    hold = client.post("/api/tables/legal_hold", headers=_hdr(people["hr"]), json={
        "scope_type": "employee", "scope_id": employee_id, "reason": "Pending ER investigation",
        "placed_by_user_id": hr_user, "placed_at": "2026-10-01T00:00:00Z"})
    assert hold.status_code == 201, hold.text

    started = client.post("/api/exit/start", headers=_hdr(people["hr"]), json={
        "employee_id": employee_id, "termination_type": "involuntary", "reason_code": "performance",
        "notice_date": "2026-11-01", "last_working_day": "2026-11-15"})
    assert started.status_code == 201, started.text
    rid = started.json()["termination_id"]

    run_workers(6)  # legal_hold_checker finds the active hold -> parks on g_legalhold

    instance = client.get("/api/workflows/instances", headers=people["hr"], params={"subject_id": rid}).json()["instances"][0]
    assert instance["state"] == "s02_legal_hold_check" and instance["status"] == "waiting_gate"

    pending = client.get("/api/approvals", headers=people["founder"], params={"status": "pending"}).json()["approvals"]
    hold_gate = next(a for a in pending if a["gate_type"] == "g_legalhold")
    assert hold_gate["subject_id"] == rid  # engine-level gate: raised against termination, the instance's own subject

    resolved = client.post(f"/api/approvals/{hold_gate['id']}/resolve", headers=people["founder"], json={"decision": "approved"})
    assert resolved.status_code == 200, resolved.text
    run_workers(6)

    instance = client.get("/api/workflows/instances", headers=people["hr"], params={"subject_id": rid}).json()["instances"][0]
    assert instance["state"] not in ("s02_legal_hold_check",)  # moved past the hold check
