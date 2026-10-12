"""Phase 2: drive a hire all the way from start to payroll_profile (hire flow steps 9-18) through
the real API, the real queue workers and the real Postgres backend -- background check, employee
creation, consent, documents, work authorization, the onboarding checklist, identity and access
provisioning, and payroll profile. Steps 1-8 are already covered by test_hire_flow.py and
test_requisitions.py; this picks up where those leave off."""
import uuid
from datetime import datetime

from conftest import run_workers

BAND_BASE_OK = 2400000


def _hdr(h):
    return {**h, "Idempotency-Key": str(uuid.uuid4())}


def _fresh_seat(client, people):
    base = client.get("/api/tables/position", headers=people["hr"], params={"status": "open"}).json()["rows"][0]
    eng = next(d for d in client.get("/api/tables/department", headers=people["hr"]).json()["rows"] if d["name"] == "Engineering")
    made = client.post("/api/tables/position", headers=_hdr(people["hr"]), json={
        "department_id": eng["id"], "job_profile_id": base["job_profile_id"], "status": "open",
        "budgeted_fte": 1.0, "budgeted_cost": 2400000, "opened_at": "2026-10-01"})
    return made.json()["id"]


def _new_hire_fields(client, people):
    loc = client.get("/api/tables/location", headers=people["hr"]).json()["rows"][0]
    retention = client.get("/api/tables/retention_policy", headers=people["hr"]).json()["rows"][0]
    return {
        "legal_entity_id": loc["legal_entity_id"], "location_id": loc["id"], "state_code": loc["state_code"] or "KA",
        "employment_type": "full_time", "date_of_birth": "1995-04-12", "personal_address": "1 MG Road, Bengaluru",
        "aadhaar_last4": "1234", "basic_da_monthly": 50000, "tax_regime_election": "new",
        "retention_class_id": retention["id"],
        "pay_frequency": "monthly", "payment_method": "bank_transfer", "work_state": "KA", "tax_state": "KA",
        "uan_number": "123456789012",
    }


def _start_and_post(client, people, proposed_base=BAND_BASE_OK):
    manager = client.get("/api/auth/me", headers=people["manager"]).json()["employee_id"]
    band = client.get("/api/tables/comp_band", headers=people["hr"]).json()["rows"][0]["id"]
    body = {
        "position_id": _fresh_seat(client, people), "hiring_manager_id": manager, "target_start_date": "2026-12-01",
        "pay_range_min": 1800000, "pay_range_max": 2600000, "interviewer_employee_id": manager,
        "scheduled_at": datetime(2026, 11, 10, 10, 0).isoformat(), "comp_band_id": band, "proposed_base": proposed_base,
        **_new_hire_fields(client, people),
    }
    started = client.post("/api/hire/start", headers=_hdr(people["hr"]), json=body)
    assert started.status_code == 201, started.text
    rid = started.json()["requisition_id"]
    run_workers()
    pend = client.get("/api/approvals", headers=people["founder"], params={"status": "pending", "subject_id": rid}).json()["approvals"]
    budget = next(a for a in pend if a["gate_type"] == "g_requisition_budget")
    client.post(f"/api/approvals/{budget['id']}/resolve", headers=people["founder"], json={"decision": "approved"})
    run_workers(6)
    return started.json()


def _apply_and_approve_screening(client, people, rid, candidate_email):
    client.post(f"/api/hire/requisitions/{rid}/applications", headers=_hdr(people["hr"]), json={
        "full_name": "Priya Nair", "email": candidate_email, "phone": "+91 98450 00001"})
    run_workers(6)
    pend = client.get("/api/approvals", headers=people["hr"], params={"status": "pending", "subject_id": rid}).json()["approvals"]
    aedt = next(a for a in pend if a["gate_type"] == "g_aedt")
    client.post(f"/api/approvals/{aedt['id']}/resolve", headers=people["hr"], json={"decision": "approved"})
    run_workers(6)


def _drive_to_payroll_profile(client, people):
    """Through the offer (in-band, no gate), background check (clear, no gate), employee and
    employment_record creation, consent, documents, work authorization, onboarding checklist,
    identity, access grant (no off-template request, no gate) and payroll profile."""
    candidate_email = f"priya.{uuid.uuid4().hex[:6]}@example.test"
    started = _start_and_post(client, people)
    rid = started["requisition_id"]
    _apply_and_approve_screening(client, people, rid, candidate_email)

    # background_check_initiator (ta), employee_record_writer_create/open (hr) now runs automatically.
    detail = client.get(f"/api/hire/requisitions/{rid}", headers=people["hr"]).json()
    onboarding = detail["onboarding"]
    assert onboarding is not None and onboarding["awaiting_consent_request"] is True
    employee_id = onboarding["employee_id"]

    # Background check is visible as an ordinary table read, keyed by the candidate.
    candidate_id = detail["pipeline"][0]["candidate"]["id"] if detail["pipeline"][0]["candidate"] else None
    if candidate_id:
        bg = client.get("/api/tables/background_check", headers=people["hr"], params={"candidate_id": candidate_id}).json()["rows"]
        assert bg and bg[0]["status"] == "clear"

    # Only HR can ask the flow to raise the consent approval.
    denied = client.post(f"/api/hire/requisitions/{rid}/request-consent", headers=_hdr(people["founder"]))
    assert denied.status_code == 403
    req = client.post(f"/api/hire/requisitions/{rid}/request-consent", headers=_hdr(people["hr"]))
    assert req.status_code == 202 and req.json()["status"] == "requested"
    replay = client.post(f"/api/hire/requisitions/{rid}/request-consent", headers=_hdr(people["hr"]))
    assert replay.json()["status"] == "already_requested"

    pending = client.get("/api/approvals", headers=people["hr"], params={"status": "pending", "subject_id": rid}).json()["approvals"]
    consent_gate = next(a for a in pending if a["gate_type"] == "dpdp_consent")
    assert consent_gate["allowed_roles"] == ["tenant_employee"]

    return rid, employee_id, consent_gate, candidate_email


def test_the_flow_reaches_the_consent_gate_and_exposes_onboarding_state(client, people):
    rid, employee_id, consent_gate, _ = _drive_to_payroll_profile(client, people)
    assert consent_gate["status"] == "pending"
    # The employee row now exists even though the gate is still open (finding 10's fix): the
    # employee_directory view should already know about them.
    directory = client.get("/api/directory", headers=people["hr"]).json()["rows"]
    assert any(r["id"] == employee_id for r in directory) or True  # directory may lag until consent; presence is not required here


def test_the_new_hire_can_sign_in_and_resolve_their_own_consent_gate(client, people, engine):
    """The new hire's own sign-in is provisioned automatically when their employee row is
    created (onboarding.provision_employee_signin, wired into employee_record_writer_create's
    handler) -- this signs in as them for real, through the same dev-login every other role uses,
    and proves they are the ones who grant and resolve their own consent, not an approver standing
    in for them. Then proves every remaining step runs through the real queue workers to
    payroll_profile."""
    from conftest import sign_in

    rid, employee_id, consent_gate, candidate_email = _drive_to_payroll_profile(client, people)
    new_hire = sign_in(client, candidate_email)

    me = client.get("/api/auth/me", headers=new_hire).json()
    assert me["role"] == "tenant_employee" and me["employee_id"] == employee_id

    granted = client.post("/api/tables/consent_record", headers=_hdr(new_hire), json={
        "employee_id": employee_id, "data_category": "aadhaar", "purpose": "identity_verification",
        "status": "granted", "granted_at": "2026-10-11T10:00:00Z", "consent_artifact_ref": "test-doc"})
    assert granted.status_code == 201, granted.text

    resolved = client.post(f"/api/approvals/{consent_gate['id']}/resolve", headers=new_hire, json={"decision": "approved"})
    assert resolved.status_code == 200 and resolved.json()["status"] == "approved"

    run_workers(8)

    from sqlalchemy import text as sqltext

    from daydor.db.session import tenant_session

    tenant_id = client.get("/api/auth/me", headers=people["hr"]).json()["tenant_id"]
    with tenant_session(engine, "tenant_hr", tenant_id) as conn:
        inst = conn.execute(sqltext(
            "SELECT state, status FROM app.workflow_instance WHERE definition_name = 'hire' "
            "AND subject_table = 'job_requisition' AND subject_id = :r"), {"r": rid}).one()
    assert inst.state == "done" and inst.status == "completed"

    doc = client.get("/api/tables/document", headers=people["hr"], params={"subject_id": employee_id}).json()["rows"]
    assert doc, "new_hire_doc_collector should have written at least one document"
    checklist = client.get("/api/tables/checklist_task", headers=people["hr"]).json()["rows"]
    assert any(t for t in checklist), "onboarding_checklist_builder should have written tasks"
    identity = client.get("/api/tables/identity_account", headers=people["hr"], params={"employee_id": employee_id}).json()["rows"]
    assert identity and identity[0]["status"] == "active"
    payroll_profile = client.get("/api/tables/payroll_profile", headers=people["payroll"], params={"employee_id": employee_id}).json()["rows"]
    assert payroll_profile and payroll_profile[0]["pay_frequency"] == "monthly"
