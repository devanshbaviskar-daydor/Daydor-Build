"""Phase 3: a hire from a new requisition through offer, background check, consent (resolved by
the new hire themselves, through a real sign-in), documents, work authorization (US) or identity
documents (India -- no work_authorization row at all, by design), onboarding, access, payroll
profile, and a real first payslip from an actual payroll run -- the right role doing each human
step, the queue worker doing the rest, end to end through the real API and a real Postgres.

Runs both the US and the India-first path; the backend's own README calls out running the
India-first path explicitly."""
import uuid
from datetime import date, datetime

import pytest

from conftest import run_workers, sign_in

PROPOSED_BASE = 2000000  # inside the seeded INR comp_band (18L-30L) for both paths, so no g_offer_band detour


def _hdr(h):
    return {**h, "Idempotency-Key": str(uuid.uuid4())}


def _approve(client, who, requisition_id, gate):
    run_workers()
    pend = client.get("/api/approvals", headers=who, params={"status": "pending", "subject_id": requisition_id}).json()["approvals"]
    target = next(a for a in pend if a["gate_type"] == gate)
    assert target["can_resolve"], gate
    r = client.post(f"/api/approvals/{target['id']}/resolve", headers=who, json={"decision": "approved"})
    assert r.status_code == 200, r.text
    run_workers(6)


def _fresh_seat(client, people, department_name="People Operations"):
    # Not "Engineering": test_hire_flow.py's _open_position() picks /tables/position?status=open's
    # first row with no department scoping and no ordering. This test's hires run to real
    # completion (unlike most others, which stop at the offer), and nothing in the backend marks
    # a position "filled" or closes its job_requisition on hire completion (a real gap worth its
    # own look) -- so a completed hire's position still looks exactly like an open, vacant seat
    # forever after. A collision there resurfaces finding 9's shape under a new state ('done'
    # instead of 'running'): open_requisition() returns the same already-used requisition,
    # engine.start() no-ops on the existing (completed) instance, and start_hire() then fires
    # three more "advance"s from a terminal state, raising WorkflowError. Using an isolated
    # department sidesteps the collision rather than changing shared test infrastructure.
    base = client.get("/api/tables/position", headers=people["hr"], params={"status": "open"}).json()["rows"][0]
    dept = next(d for d in client.get("/api/tables/department", headers=people["hr"]).json()["rows"] if d["name"] == department_name)
    made = client.post("/api/tables/position", headers=_hdr(people["hr"]), json={
        "department_id": dept["id"], "job_profile_id": base["job_profile_id"], "status": "open",
        "budgeted_fte": 1.0, "budgeted_cost": 2400000, "opened_at": "2026-10-01"})
    return made.json()["id"]


def _location(client, people, country_code):
    rows = client.get("/api/tables/location", headers=people["hr"]).json()["rows"]
    return next(r for r in rows if r["country_code"] == country_code)


def _new_hire_fields(client, people, location):
    retention = client.get("/api/tables/retention_policy", headers=people["hr"]).json()["rows"][0]
    state = location["state_code"] or "KA"
    return {
        "legal_entity_id": location["legal_entity_id"], "location_id": location["id"], "state_code": state,
        "employment_type": "full_time", "date_of_birth": "1995-04-12", "personal_address": "1 Main Street",
        "aadhaar_last4": "1234", "basic_da_monthly": PROPOSED_BASE / 24, "tax_regime_election": "new",
        "retention_class_id": retention["id"],
        "pay_frequency": "monthly", "payment_method": "bank_transfer", "work_state": state, "tax_state": state,
        "uan_number": "123456789012",
    }


def _run_the_hire(client, people, location, candidate_name):
    """Through offer, background check, employee creation, the real sign-in and consent gate,
    documents, work authorization/identity docs, onboarding, access, and payroll profile. Returns
    (requisition_id, employee_id, legal_entity_id)."""
    manager = client.get("/api/auth/me", headers=people["manager"]).json()["employee_id"]
    band = client.get("/api/tables/comp_band", headers=people["hr"]).json()["rows"][0]["id"]
    body = {
        "position_id": _fresh_seat(client, people), "hiring_manager_id": manager, "target_start_date": "2026-12-01",
        "pay_range_min": 1800000, "pay_range_max": 2600000, "interviewer_employee_id": manager,
        "scheduled_at": datetime(2026, 11, 10, 10, 0).isoformat(), "comp_band_id": band, "proposed_base": PROPOSED_BASE,
        **_new_hire_fields(client, people, location),
    }
    started = client.post("/api/hire/start", headers=_hdr(people["hr"]), json=body)
    assert started.status_code == 201, started.text
    rid = started.json()["requisition_id"]
    _approve(client, people["founder"], rid, "g_requisition_budget")

    candidate_email = f"{candidate_name.split()[0].lower()}.{uuid.uuid4().hex[:6]}@example.test"
    client.post(f"/api/hire/requisitions/{rid}/applications", headers=_hdr(people["hr"]), json={
        "full_name": candidate_name, "email": candidate_email, "phone": "+1 512 555 0100"})
    run_workers(6)
    _approve(client, people["hr"], rid, "g_aedt")
    # in-band offer, clear background check: runs straight through to the consent step

    detail = client.get(f"/api/hire/requisitions/{rid}", headers=people["hr"]).json()
    onboarding = detail["onboarding"]
    assert onboarding is not None and onboarding["awaiting_consent_request"] is True
    employee_id = onboarding["employee_id"]

    req = client.post(f"/api/hire/requisitions/{rid}/request-consent", headers=_hdr(people["hr"]))
    assert req.status_code == 202 and req.json()["status"] == "requested"

    pending = client.get("/api/approvals", headers=people["hr"], params={"status": "pending", "subject_id": rid}).json()["approvals"]
    consent_gate = next(a for a in pending if a["gate_type"] == "dpdp_consent")

    new_hire = sign_in(client, candidate_email)
    me = client.get("/api/auth/me", headers=new_hire).json()
    assert me["employee_id"] == employee_id
    granted = client.post("/api/tables/consent_record", headers=_hdr(new_hire), json={
        "employee_id": employee_id, "data_category": "aadhaar", "purpose": "identity_verification",
        "status": "granted", "granted_at": "2026-10-11T10:00:00Z", "consent_artifact_ref": "test-doc"})
    assert granted.status_code == 201, granted.text
    resolved = client.post(f"/api/approvals/{consent_gate['id']}/resolve", headers=new_hire, json={"decision": "approved"})
    assert resolved.status_code == 200 and resolved.json()["status"] == "approved"

    run_workers(8)

    return rid, employee_id


@pytest.mark.parametrize("country_code,candidate_name", [("IN", "Priya Nair"), ("US", "Jordan Lee")])
def test_hire_through_first_payslip(client, people, country_code, candidate_name):
    location = _location(client, people, country_code)
    rid, employee_id = _run_the_hire(client, people, location, candidate_name)

    wf = client.get("/api/workflows/instances", headers=people["hr"], params={"subject_id": rid}).json()
    instance = wf["instances"][0]
    assert instance["state"] == "done" and instance["status"] == "completed"

    work_auth = client.get("/api/tables/work_authorization", headers=people["hr"], params={"employee_id": employee_id}).json()["rows"]
    if country_code == "US":
        assert work_auth and work_auth[0]["status"] == "pending", "I-9/E-Verify should have started for a US hire"
    else:
        assert work_auth == [], "work authorization is US-only; an India hire should get no row at all"

    identity = client.get("/api/tables/identity_account", headers=people["hr"], params={"employee_id": employee_id}).json()["rows"]
    assert identity and identity[0]["status"] == "active"
    payroll_profile = client.get("/api/tables/payroll_profile", headers=people["payroll"], params={"employee_id": employee_id}).json()["rows"]
    assert payroll_profile, "payroll_profile should exist -- the hire flow's real terminal step"

    # Build the payroll run covering this hire's own legal entity and period, as Payroll would.
    created = client.post("/api/payroll/runs", headers=_hdr(people["payroll"]), json={
        "legal_entity_id": location["legal_entity_id"], "period_start": "2026-12-01", "period_end": "2026-12-31",
        "retention_class_id": client.get("/api/tables/retention_policy", headers=people["hr"]).json()["rows"][0]["id"],
    })
    assert created.status_code == 201, created.text
    run_id = created.json()["payroll_run_id"]
    anomaly_approval_id = created.json()["anomaly_check"]["approval_request_id"]
    assert anomaly_approval_id, "shadow-mode sg_payroll_anomaly_precheck should always escalate to g_pay_anomaly"

    # Maker-checker: the payroll person who built the run cannot also clear its own anomaly
    # check (g_pay_anomaly's other approver role, daydor_ops, can).
    anomaly_resolved = client.post(f"/api/approvals/{anomaly_approval_id}/resolve", headers=people["ops"], json={"decision": "approved"})
    assert anomaly_resolved.status_code == 200, anomaly_resolved.text

    requested = client.post(f"/api/payroll/runs/{run_id}/request-disbursal", headers=_hdr(people["payroll"]))
    assert requested.status_code == 202, requested.text
    disbursal_approval_id = requested.json()["approval_request_id"]

    disburse_too_early = client.post(f"/api/payroll/runs/{run_id}/disburse", headers=_hdr(people["payroll"]),
                                     json={"approval_request_id": disbursal_approval_id})
    assert disburse_too_early.status_code == 409, "disbursal must be impossible before the founder approves it"

    disburse_resolved = client.post(f"/api/approvals/{disbursal_approval_id}/resolve", headers=people["founder"], json={"decision": "approved"})
    assert disburse_resolved.status_code == 200, disburse_resolved.text

    disbursed = client.post(f"/api/payroll/runs/{run_id}/disburse", headers=_hdr(people["payroll"]),
                            json={"approval_request_id": disbursal_approval_id})
    assert disbursed.status_code == 200 and disbursed.json()["status"] == "disbursed"

    issued = client.post(f"/api/payroll/runs/{run_id}/issue-payslips", headers=_hdr(people["payroll"]))
    assert issued.status_code == 200 and issued.json()["payslip_ids"]

    payslips = client.get("/api/tables/payslip", headers=people["payroll"], params={"payroll_run_id": run_id}).json()["rows"]
    mine = next((p for p in payslips if p["employee_id"] == employee_id), None)
    assert mine is not None, "the new hire's first payslip should exist on this run"
    assert float(mine["gross_pay"]) == pytest.approx(PROPOSED_BASE / 12, abs=0.01)
    assert float(mine["net_pay"]) < float(mine["gross_pay"]), "statutory withholding should reduce net below gross"
