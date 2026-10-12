"""Start a hire through the API, let the real queue workers run, approve as the founder, and watch
the real workflow move. This is the FE-0 exit path: session, approvals list and one flow action."""
import uuid

from conftest import run_workers


def _open_position(client, headers):
    """A fresh, never-touched open seat, not one picked from the shared pool: nothing in the
    backend marks a position "filled" or closes its requisition when a hire completes (a position
    a completed hire used still looks exactly like an open, vacant seat), so blindly picking
    `/tables/position?status=open`'s first vacant row can return one another test already hired
    into -- `open_requisition()` would then return that same, already-used requisition, and
    `start_hire()`'s unconditional `"advance"` calls raise `WorkflowError` from its terminal state
    (a new shape of finding 9, discovered by test_hire_end_to_end.py actually driving hires to
    completion instead of stopping at the offer)."""
    rows = client.get("/api/tables/position", headers=headers, params={"status": "open"}).json()["rows"]
    base = next(r for r in rows if r["current_employee_id"] is None)
    made = client.post("/api/tables/position", headers={**headers, "Idempotency-Key": str(uuid.uuid4())}, json={
        "department_id": base["department_id"], "job_profile_id": base["job_profile_id"], "status": "open",
        "budgeted_fte": 1.0, "budgeted_cost": 1800000, "opened_at": "2026-10-01"}).json()
    return {"id": made["id"], "department_id": base["department_id"], "job_profile_id": base["job_profile_id"]}


def _start(client, headers, position_id, manager_employee_id, key=None):
    h = {**headers, "Idempotency-Key": key or str(uuid.uuid4())}
    return client.post("/api/hire/start", headers=h, json={
        "position_id": position_id, "hiring_manager_id": manager_employee_id, "target_start_date": "2026-12-01",
        "pay_range_min": 1800000, "pay_range_max": 2600000})


def test_full_path_from_start_to_posting(client, people):
    manager_emp = client.get("/api/auth/me", headers=people["manager"]).json()["employee_id"]
    position = _open_position(client, people["hr"])
    key = str(uuid.uuid4())
    started = _start(client, people["hr"], position["id"], manager_emp, key)
    assert started.status_code == 201, started.text
    ids = started.json()

    replay = _start(client, people["hr"], position["id"], manager_emp, key)
    assert replay.json()["instance_id"] == ids["instance_id"] and replay.json()["replayed"] is True

    run_workers()  # the approval router raises the budget gate and parks the instance

    pending = client.get("/api/approvals", headers=people["founder"], params={"status": "pending"}).json()["approvals"]
    mine = next(a for a in pending if a["subject_id"] == ids["requisition_id"])
    assert mine["gate_type"] == "g_requisition_budget"
    assert mine["gate_label"] == "Requisition budget sign-off"
    assert mine["allowed_roles"] == ["tenant_founder"] and mine["can_resolve"] is True

    # HR can see the request but is not the approver.
    hr_view = client.get(f"/api/approvals/{mine['id']}", headers=people["hr"]).json()
    assert hr_view["can_resolve"] is False
    wrong = client.post(f"/api/approvals/{mine['id']}/resolve", headers=people["hr"], json={"decision": "approved"})
    assert wrong.status_code == 403 and wrong.json()["error"]["code"] in ("wrong_approver_role", "forbidden")

    inst = client.get(f"/api/workflows/instances/{ids['instance_id']}", headers=people["founder"]).json()
    assert inst["instance"]["status"] == "waiting_gate" and inst["instance"]["state"] == "s03_approval_request"
    assert inst["definition"]["initial"] == "start"

    done = client.post(f"/api/approvals/{mine['id']}/resolve", headers=people["founder"],
                       json={"decision": "approved", "note": "Within plan"})
    assert done.status_code == 200 and done.json()["status"] == "approved"
    run_workers()

    after = client.get(f"/api/workflows/instances/{ids['instance_id']}", headers=people["founder"]).json()
    assert after["instance"]["state"] == "s04_job_posting" and after["instance"]["status"] == "running"
    outcomes = [(t["from_state"], t["to_state"], t["outcome"]) for t in after["transitions"]]
    assert ("s03_approval_request", "s04_job_posting", "moved") in outcomes
    assert any(o[2] == "waiting_gate" for o in outcomes)
    assert [o[1] for o in outcomes][:3] == ["s01_position", "s02_job_requisition", "s03_approval_request"]

    again = client.post(f"/api/approvals/{mine['id']}/resolve", headers=people["founder"],
                        json={"decision": "approved"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_resolved"


def test_a_seat_that_is_not_open_is_refused(client, people):
    manager_emp = client.get("/api/auth/me", headers=people["manager"]).json()["employee_id"]
    rows = client.get("/api/tables/position", headers=people["hr"], params={"status": "filled"}).json()["rows"]
    r = _start(client, people["hr"], rows[0]["id"], manager_emp)
    assert r.status_code == 409 and r.json()["error"]["code"] == "no_open_seat"


def test_roles_that_cannot_open_requisitions_are_refused(client, people):
    r = _start(client, people["employee"], str(uuid.uuid4()), str(uuid.uuid4()))
    assert r.status_code == 403


def test_bad_pay_range_is_a_clear_error(client, people):
    h = {**people["hr"]}
    r = client.post("/api/hire/start", headers=h, json={
        "position_id": str(uuid.uuid4()), "hiring_manager_id": str(uuid.uuid4()),
        "target_start_date": "2026-12-01", "pay_range_min": 5, "pay_range_max": 1})
    assert r.status_code == 422


def test_workflow_timelines_are_limited_to_the_roles_the_database_allows(client, people):
    for role in ("manager", "employee", "it"):
        r = client.get("/api/workflows/instances", headers=people[role])
        assert r.status_code == 403 and r.json()["error"]["code"] == "workflow_not_visible", role
    for role in ("founder", "hr", "payroll", "ops", "auditor"):
        assert client.get("/api/workflows/instances", headers=people[role]).status_code == 200, role


def test_workflow_context_hides_personal_values(client, people):
    from daydor_api.access import safe_context
    kept, hidden = safe_context({"channel": "company_site", "position_id": "x", "requires_g_aedt": True,
                                 "email": "a@b.c", "phone": "555", "full_name": "A", "proposed_base": "1"})
    assert set(kept) == {"channel", "position_id", "requires_g_aedt"}
    assert hidden == ["email", "full_name", "phone", "proposed_base"]


def test_approvals_list_is_available_to_roles_with_table_access(client, people):
    for role in ("founder", "hr", "payroll", "it", "manager", "employee", "ops"):
        assert client.get("/api/approvals", headers=people[role]).status_code == 200, role
    assert client.get("/api/approvals", headers=people["admin"]).status_code == 403


def test_a_second_start_for_the_same_position_returns_the_hire_already_in_progress(client, people):
    manager_emp = client.get("/api/auth/me", headers=people["manager"]).json()["employee_id"]
    base = _open_position(client, people["hr"])
    made = client.post("/api/tables/position", headers={**people["hr"], "Idempotency-Key": str(uuid.uuid4())}, json={
        "department_id": base["department_id"], "job_profile_id": base["job_profile_id"], "status": "open",
        "budgeted_fte": 1.0, "budgeted_cost": 1800000, "opened_at": "2026-10-01"}).json()
    first = _start(client, people["hr"], made["id"], manager_emp)
    second = _start(client, people["founder"], made["id"], manager_emp)   # different person, different key
    assert first.status_code == 201 and second.status_code == 201
    assert second.json()["instance_id"] == first.json()["instance_id"] and second.json()["existing"] is True
