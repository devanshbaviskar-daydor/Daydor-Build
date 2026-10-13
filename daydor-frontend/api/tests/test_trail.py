"""FE-1 endpoints: session capabilities, workflow link on approvals, audit trail, pre-check results."""
import uuid

from sqlalchemy import text

from conftest import hire_start_fields, run_workers


def _start_and_raise(client, people):
    manager_emp = client.get("/api/auth/me", headers=people["manager"]).json()["employee_id"]
    rows = client.get("/api/tables/position", headers=people["hr"], params={"status": "open"}).json()["rows"]
    base = next(r for r in rows if r["current_employee_id"] is None)
    # A fresh seat each time: a position can only have one hire in progress.
    made = client.post("/api/tables/position", headers={**people["hr"], "Idempotency-Key": str(uuid.uuid4())}, json={
        "department_id": base["department_id"], "job_profile_id": base["job_profile_id"], "status": "open",
        "budgeted_fte": 1.0, "budgeted_cost": 1800000, "opened_at": "2026-10-01"}).json()
    seat = {"id": made["id"]}
    started = client.post("/api/hire/start", headers={**people["hr"], "Idempotency-Key": str(uuid.uuid4())}, json={
        "position_id": seat["id"], "hiring_manager_id": manager_emp, "target_start_date": "2026-12-01",
        "pay_range_min": 1800000, "pay_range_max": 2600000,
        **hire_start_fields(client, people["hr"], manager_emp)}).json()
    run_workers()
    pending = client.get("/api/approvals", headers=people["founder"],
                         params={"status": "pending", "subject_id": started["requisition_id"]}).json()["approvals"]
    assert len(pending) == 1
    return started, pending[0]


def test_session_capabilities_follow_the_workflow_reader_roles(client, people):
    for role, expected in (("founder", True), ("hr", True), ("payroll", True), ("ops", True), ("auditor", True),
                           ("manager", False), ("employee", False), ("it", False)):
        me = client.get("/api/auth/me", headers=people[role]).json()
        assert me["capabilities"]["workflow_timeline"] is expected, role


def test_approval_detail_names_the_workflow_only_for_roles_that_can_read_it(client, people):
    started, approval = _start_and_raise(client, people)
    founder = client.get(f"/api/approvals/{approval['id']}", headers=people["founder"]).json()
    assert founder["workflow_instance_id"] == started["instance_id"]
    for role in ("manager", "employee", "it"):
        detail = client.get(f"/api/approvals/{approval['id']}", headers=people[role])
        assert detail.status_code == 200 and detail.json()["workflow_instance_id"] is None, role


def test_approval_filters_by_subject(client, people):
    started, approval = _start_and_raise(client, people)
    hit = client.get("/api/approvals", headers=people["hr"], params={"subject_id": started["requisition_id"]}).json()
    assert [a["id"] for a in hit["approvals"]] == [approval["id"]]
    miss = client.get("/api/approvals", headers=people["hr"], params={"subject_id": str(uuid.uuid4())}).json()
    assert miss["approvals"] == []


def test_audit_trail_combines_approvals_and_transitions_in_time_order(client, people):
    started, approval = _start_and_raise(client, people)
    client.post(f"/api/approvals/{approval['id']}/resolve", headers=people["founder"],
                json={"decision": "approved", "note": "Within plan"})
    run_workers()
    params = {"table": "job_requisition", "id": started["requisition_id"]}

    founder = client.get("/api/audit/subject", headers=people["founder"], params=params).json()
    actions = [e["action"] for e in founder["entries"]]
    assert any(a.startswith("Asked for approval: Requisition budget sign-off") for a in actions)
    assert any(a.startswith("Approved: Requisition budget sign-off. Note: Within plan") for a in actions)
    assert any(a == "Paused at approval request, waiting for approval" for a in actions)
    assert any(a == "Moved from approval request to job posting" for a in actions)
    assert [e["at"] for e in founder["entries"]] == sorted(e["at"] for e in founder["entries"])
    mine = next(e for e in founder["entries"] if e["kind"] == "approval_resolved")
    assert mine["actor"] == "You"

    # HR may see names; the same entry names the founder.
    hr = client.get("/api/audit/subject", headers=people["hr"], params=params).json()
    assert next(e for e in hr["entries"] if e["kind"] == "approval_resolved")["actor"] == "Rohan Mehta"


def test_roles_that_cannot_read_workflows_get_the_approval_part_only_and_no_names(client, people):
    started, approval = _start_and_raise(client, people)
    client.post(f"/api/approvals/{approval['id']}/resolve", headers=people["founder"], json={"decision": "approved"})
    trail = client.get("/api/audit/subject", headers=people["manager"],
                       params={"table": "job_requisition", "id": started["requisition_id"]}).json()
    assert trail["sources"]["workflow"] is False
    assert {e["kind"] for e in trail["entries"]} == {"approval_requested", "approval_resolved"}
    assert next(e for e in trail["entries"] if e["kind"] == "approval_resolved")["actor"] == "A person"


def test_trail_for_a_role_without_approval_access_is_empty_not_an_error(client, people):
    trail = client.get("/api/audit/subject", headers=people["admin"],
                       params={"table": "job_requisition", "id": str(uuid.uuid4())}).json()
    assert trail["entries"] == []


def test_precheck_results_are_recorded_by_agents_and_shown_to_the_five_roles(client, people, engine, seeded):
    from daydor.db.session import tenant_session
    subject = uuid.uuid4()
    with engine.begin() as conn:
        tenant = conn.execute(text("SELECT id FROM tenant WHERE legal_name = 'Acme Technologies'")).scalar_one()
    with tenant_session(engine, "agent_pay", tenant) as conn:
        conn.execute(text("SELECT app.record_gate_evaluation('sg_payroll_anomaly_precheck', 'payroll_run', :s, 'laya', "
                          "'0.1', '1', 'hash', ARRAY['gross_total'], CAST('{}' AS jsonb), 0.42, 'escalate', 12, NULL, NULL)"),
                     {"s": subject})
    got = client.get("/api/evaluations", headers=people["payroll"], params={"subject_id": str(subject)}).json()["evaluations"]
    assert len(got) == 1
    ev = got[0]
    assert ev["gate_label"].startswith("Pre-check") or "payroll" in ev["gate_label"].lower()
    assert ev["mode"] == "shadow" and ev["effective_decision"] == "escalate" and ev["model_decision"] == "escalate"
    assert "input_hash" not in ev and "output" not in ev        # inputs and raw output stay in the database
    for role in ("manager", "employee", "it"):
        r = client.get("/api/evaluations", headers=people[role])
        assert r.status_code == 403 and r.json()["error"]["code"] == "evaluation_not_visible", role
