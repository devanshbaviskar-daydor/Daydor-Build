"""FE-2 and FE-3 on the real backend: requisitions, application entry, screening, interview, offer."""
import uuid
from datetime import datetime

import pytest

from conftest import hire_start_fields, run_workers

BAND_BASE_OK, BAND_BASE_HIGH = 2400000, 4500000   # the seeded band is 18 lakh to 30 lakh


def _hdr(h):
    return {**h, "Idempotency-Key": str(uuid.uuid4())}


def _fresh_seat(client, people):
    base = client.get("/api/tables/position", headers=people["hr"], params={"status": "open"}).json()["rows"][0]
    eng = next(d for d in client.get("/api/tables/department", headers=people["hr"]).json()["rows"] if d["name"] == "Engineering")
    made = client.post("/api/tables/position", headers=_hdr(people["hr"]), json={
        "department_id": eng["id"], "job_profile_id": base["job_profile_id"], "status": "open",
        "budgeted_fte": 1.0, "budgeted_cost": 2400000, "opened_at": "2026-10-01"})
    return made.json()["id"]


def _start(client, people, proposed_base=BAND_BASE_OK):
    manager = client.get("/api/auth/me", headers=people["manager"]).json()["employee_id"]
    band = client.get("/api/tables/comp_band", headers=people["hr"]).json()["rows"][0]["id"]
    r = client.post("/api/hire/start", headers=_hdr(people["hr"]), json={
        "position_id": _fresh_seat(client, people), "hiring_manager_id": manager, "target_start_date": "2026-12-01",
        "pay_range_min": 1800000, "pay_range_max": 2600000, "interviewer_employee_id": manager,
        "scheduled_at": datetime(2026, 11, 10, 10, 0).isoformat(), "comp_band_id": band, "proposed_base": proposed_base,
        **{k: v for k, v in hire_start_fields(client, people["hr"], manager, proposed_base).items()
           if k not in ("interviewer_employee_id", "scheduled_at", "comp_band_id", "proposed_base")}})
    assert r.status_code == 201, r.text
    return r.json()


def _approve(client, people, role, subject_id, gate):
    run_workers()
    pend = client.get("/api/approvals", headers=people[role], params={"status": "pending", "subject_id": subject_id}).json()["approvals"]
    target = next(a for a in pend if a["gate_type"] == gate)
    assert target["can_resolve"], (gate, role)
    r = client.post(f"/api/approvals/{target['id']}/resolve", headers=people[role], json={"decision": "approved"})
    assert r.status_code == 200, r.text
    run_workers(6)


def _posted(client, people, **kw):
    started = _start(client, people, **kw)
    _approve(client, people, "founder", started["requisition_id"], "g_requisition_budget")
    return started


def _apply(client, people, requisition_id, email=None):
    return client.post(f"/api/hire/requisitions/{requisition_id}/applications", headers=_hdr(people["hr"]), json={
        "full_name": "Neha Gupta", "email": email or f"neha.{uuid.uuid4().hex[:6]}@example.test", "phone": "+91 98450 00000"})


def test_requisition_list_shows_a_plain_stage_for_each_requisition(client, people):
    started = _start(client, people)
    run_workers()
    mine = next(r for r in client.get("/api/hire/requisitions", headers=people["hr"]).json()["requisitions"] if r["id"] == started["requisition_id"])
    assert mine["stage"] == "awaiting_budget_approval" and mine["job_title"] == "Backend Engineer"
    assert mine["department_name"] == "Engineering" and mine["approval"]["status"] == "pending"
    assert mine["hiring_manager_name"] == "Meera Iyer" and mine["posting"] is None and mine["candidate_count"] == 0

    _approve(client, people, "founder", started["requisition_id"], "g_requisition_budget")
    after = client.get(f"/api/hire/requisitions/{started['requisition_id']}", headers=people["hr"]).json()["requisition"]
    assert after["stage"] == "posted" and after["posting"]["posted_at"] and after["posting"]["channel"] == "company_site"


def test_applications_need_an_approved_budget_and_a_live_posting(client, people):
    started = _start(client, people)
    run_workers()
    early = _apply(client, people, started["requisition_id"])
    assert early.status_code == 409 and early.json()["error"]["code"] == "not_accepting_applications"
    ghost = _apply(client, people, str(uuid.uuid4()))
    assert ghost.status_code == 404


def test_only_roles_with_write_access_enter_applications_and_input_is_checked(client, people):
    started = _posted(client, people)
    assert _apply(client, {"hr": people["manager"]}, started["requisition_id"]).status_code == 403
    bad = client.post(f"/api/hire/requisitions/{started['requisition_id']}/applications", headers=people["hr"],
                      json={"full_name": "X", "email": "not-an-email", "phone": "1"})
    assert bad.status_code == 422 and "email" in bad.json()["error"]["message"]


def test_a_candidate_goes_from_application_to_an_in_band_offer(client, people):
    started = _posted(client, people)
    rid = started["requisition_id"]
    key = str(uuid.uuid4())
    payload = {"full_name": "Neha Gupta", "email": "neha.g@example.test", "phone": "+91 98450 00000"}
    first = client.post(f"/api/hire/requisitions/{rid}/applications", headers={**people["hr"], "Idempotency-Key": key}, json=payload)
    assert first.status_code == 202 and first.json()["status"] == "queued"
    replay = client.post(f"/api/hire/requisitions/{rid}/applications", headers={**people["hr"], "Idempotency-Key": key}, json=payload)
    assert replay.json().get("replayed") is True
    run_workers(6)

    # screening parks on the AEDT sign-off, which only HR can give
    detail = client.get(f"/api/hire/requisitions/{rid}", headers=people["hr"]).json()
    item = detail["pipeline"][0]
    assert item["candidate"]["full_name"] == "Neha Gupta" and item["application"]["stage"] == "applied"
    assert item["screening"]["recommendation"] and item["screening"]["approval"]["gate_type"] == "g_aedt"
    assert item["screening"]["approval"]["status"] == "pending" and item["interview"] is None

    _approve(client, people, "hr", rid, "g_aedt")
    item = client.get(f"/api/hire/requisitions/{rid}", headers=people["hr"]).json()["pipeline"][0]
    assert item["screening"]["approval"]["status"] == "approved"
    assert item["interview"]["interviewer_name"] == "Meera Iyer"
    assert item["offer"]["within_band"] is True and item["offer"]["approval"] is None
    assert item["offer"]["band"]["currency"] == "INR" and float(item["offer"]["proposed_base"]) == BAND_BASE_OK


def test_an_out_of_band_offer_waits_for_the_founder(client, people):
    started = _posted(client, people, proposed_base=BAND_BASE_HIGH)
    rid = started["requisition_id"]
    assert _apply(client, people, rid).status_code == 202
    run_workers(6)
    item = client.get(f"/api/hire/requisitions/{rid}", headers=people["hr"]).json()["pipeline"][0]
    _approve(client, people, "hr", rid, "g_aedt")
    item = client.get(f"/api/hire/requisitions/{rid}", headers=people["hr"]).json()["pipeline"][0]
    assert item["offer"]["within_band"] is False
    assert item["offer"]["approval"] == {"id": item["offer"]["approval"]["id"], "status": "pending", "gate_type": "g_offer_band"}
    _approve(client, people, "founder", rid, "g_offer_band")
    item = client.get(f"/api/hire/requisitions/{rid}", headers=people["hr"]).json()["pipeline"][0]
    assert item["offer"]["approval"]["status"] == "approved"


def test_each_role_sees_the_pipeline_its_grants_allow(client, people):
    started = _posted(client, people)
    rid = started["requisition_id"]
    _apply(client, people, rid)
    run_workers(6)
    # Payroll can read requisitions but not applications or candidates.
    pay = client.get(f"/api/hire/requisitions/{rid}", headers=people["payroll"]).json()
    assert pay["pipeline"] == [] and pay["access"] == {"can_enter_applications": False, "sees_candidates": False}
    # A manager reads the pipeline but cannot enter applications.
    mgr = client.get(f"/api/hire/requisitions/{rid}", headers=people["manager"]).json()
    assert mgr["access"]["sees_candidates"] is True and mgr["access"]["can_enter_applications"] is False
    # The database hides candidate rows from managers until a candidate becomes an employee, so the
    # manager sees the application and its (masked) screening but not who the candidate is.
    assert mgr["pipeline"][0]["candidate"] is None and mgr["pipeline"][0]["application"]["stage"] == "applied"
    # Employees and IT have no access to requisitions at all.
    for role in ("employee", "it"):
        r = client.get("/api/hire/requisitions", headers=people[role])
        assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden", role
    assert client.get(f"/api/hire/requisitions/{uuid.uuid4()}", headers=people["hr"]).status_code == 404


def test_multi_value_filters_and_the_directory(client, people):
    positions = client.get("/api/tables/position", headers=people["hr"]).json()["rows"]
    ids = ",".join(p["id"] for p in positions[:2])
    got = client.get("/api/tables/position", headers=people["hr"], params={"id__in": ids}).json()
    assert got["total"] == 2
    assert client.get("/api/tables/position", headers=people["hr"], params={"nope__in": "a"}).status_code == 422

    d = client.get("/api/directory", headers=people["hr"]).json()
    assert {r["full_name"] for r in d["rows"]} >= {"Meera Iyer", "Arjun Rao"}
    assert [r["full_name"] for r in client.get("/api/directory", headers=people["employee"], params={"q": "meera"}).json()["rows"]] != []
    assert client.get("/api/directory", headers=people["auditor"]).status_code == 403


def test_employees_manage_their_own_contacts_and_consent_and_hr_rates_skills(client, people):
    me = client.get("/api/auth/me", headers=people["employee"]).json()["employee_id"]
    contact = client.post("/api/tables/emergency_contact", headers=_hdr(people["employee"]), json={
        "employee_id": me, "contact_name": "Lakshmi Rao", "relationship": "Mother", "phone": "+91 98450 11111", "priority": 1})
    assert contact.status_code == 201, contact.text
    got = client.get("/api/tables/emergency_contact", headers=people["employee"]).json()["rows"]
    assert [c["contact_name"] for c in got] == ["Lakshmi Rao"]
    # HR sees it too; a manager sees it masked (the view hides the values, it does not refuse).
    assert client.get("/api/tables/emergency_contact", headers=people["hr"]).status_code == 200

    skill = client.post("/api/tables/skill", headers=_hdr(people["hr"]), json={"name": "Kubernetes", "category": "Platform"}).json()["id"]
    # The model lets only HR rate a skill: employees and managers cannot set proficiency_level.
    own = client.post("/api/tables/employee_skill", headers=_hdr(people["employee"]), json={
        "employee_id": me, "skill_id": skill, "proficiency_level": 3, "source": "self_reported", "last_updated": "2026-10-08T10:00:00Z"})
    assert own.status_code == 422 and own.json()["error"]["code"] == "invalid_fields"
    rated = client.post("/api/tables/employee_skill", headers=_hdr(people["hr"]), json={
        "employee_id": me, "skill_id": skill, "proficiency_level": 3, "source": "manager_rated", "last_updated": "2026-10-08T10:00:00Z"})
    assert rated.status_code == 201, rated.text

    consent = client.post("/api/tables/consent_record", headers=_hdr(people["employee"]), json={
        "employee_id": me, "data_category": "pan", "purpose": "identity_verification", "status": "granted",
        "granted_at": "2026-10-08T10:00:00Z", "consent_artifact_ref": "web-form-1"})
    assert consent.status_code == 201, consent.text
    assert client.post("/api/tables/consent_record", headers=_hdr(people["manager"]), json={"status": "granted"}).status_code == 403
