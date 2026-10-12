"""FE-7: time punches, timecards (+ manager approval through a real g_timecard gate), leave
accrual, benefit elections (processed by an agent, not the employee directly) and expenses (an
API-layer gap-fill: the backend models the table and the gate but ships no domain service for
either -- see timekeeping.py's module docstring)."""
import uuid
from datetime import date, datetime, timedelta, timezone

from conftest import run_workers


def _hdr(h):
    return {**h, "Idempotency-Key": str(uuid.uuid4())}


def test_employee_punches_time_and_builds_an_approved_timecard(client, people):
    me = client.get("/api/auth/me", headers=people["employee"]).json()["employee_id"]
    today = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0)
    punch_in = client.post("/api/tables/time_punch", headers=_hdr(people["employee"]), json={
        "employee_id": me, "punched_at": today.isoformat(), "kind": "in", "source": "web"})
    assert punch_in.status_code == 201, punch_in.text
    punch_out = client.post("/api/tables/time_punch", headers=_hdr(people["employee"]), json={
        "employee_id": me, "punched_at": (today + timedelta(hours=8)).isoformat(), "kind": "out", "source": "web"})
    assert punch_out.status_code == 201, punch_out.text

    # A manager's own column access on time_punch's fields doesn't extend to writing them --
    # table-level access looks like write (M: 4), but per-column access is the real picture
    # (same shape as finding 16's benefit_election).
    other = client.post("/api/tables/time_punch", headers=_hdr(people["manager"]), json={
        "employee_id": me, "punched_at": today.isoformat(), "kind": "in", "source": "web"})
    assert other.status_code == 422 and other.json()["error"]["code"] == "invalid_fields"

    period_start = today.date().isoformat()
    period_end = today.date().isoformat()
    denied = client.post("/api/timekeeping/timecards", headers=_hdr(people["it"]), json={
        "employee_id": me, "period_start": period_start, "period_end": period_end})
    assert denied.status_code == 403

    built = client.post("/api/timekeeping/timecards", headers=_hdr(people["employee"]), json={
        "employee_id": me, "period_start": period_start, "period_end": period_end})
    assert built.status_code == 201, built.text
    timecard_id, approval_id = built.json()["timecard_id"], built.json()["approval_request_id"]

    replay = client.post("/api/timekeeping/timecards", headers={**people["employee"], "Idempotency-Key": "x"}, json={
        "employee_id": me, "period_start": period_start, "period_end": period_end})
    # same period: validate_timecard is idempotent, returns the same row either way
    assert replay.json()["timecard_id"] == timecard_id

    rows = client.get("/api/tables/timecard", headers=people["employee"], params={"id": timecard_id}).json()["rows"]
    assert rows[0]["status"] == "pending_approval" and float(rows[0]["regular_hours"]) == 8.0

    pending = client.get("/api/approvals", headers=people["manager"], params={"status": "pending"}).json()["approvals"]
    gate = next(a for a in pending if a["id"] == approval_id)
    assert gate["gate_type"] == "g_timecard" and gate["can_resolve"] is True
    resolved = client.post(f"/api/approvals/{approval_id}/resolve", headers=people["manager"], json={"decision": "approved"})
    assert resolved.status_code == 200

    run_workers()
    after = client.get("/api/tables/timecard", headers=people["employee"], params={"id": timecard_id}).json()["rows"]
    assert after[0]["status"] == "approved"


def test_leave_accrues_and_only_hr_can_run_it(client, people):
    me = client.get("/api/auth/me", headers=people["employee"]).json()["employee_id"]
    policy = client.get("/api/tables/leave_policy", headers=people["hr"]).json()["rows"][0]["id"]

    denied = client.post("/api/timekeeping/leave-balances/accrue", headers=people["employee"], json={
        "employee_id": me, "leave_policy_id": policy, "as_of": "2026-10-01"})
    assert denied.status_code == 403

    accrued = client.post("/api/timekeeping/leave-balances/accrue", headers=people["hr"], json={
        "employee_id": me, "leave_policy_id": policy, "as_of": "2026-10-01"})
    assert accrued.status_code == 200, accrued.text

    rows = client.get("/api/tables/leave_balance", headers=people["employee"], params={"employee_id": me}).json()["rows"]
    assert rows and float(rows[0]["balance_days"]) >= 0


def test_benefit_election_is_processed_by_an_agent_not_the_employee_session(client, people):
    me = client.get("/api/auth/me", headers=people["employee"]).json()["employee_id"]
    plan = client.get("/api/tables/benefit_plan", headers=people["employee"]).json()["rows"][0]["id"]

    denied = client.post("/api/benefits/elections", headers=_hdr(people["it"]), json={
        "employee_id": me, "benefit_plan_id": plan, "coverage_tier": "self", "employee_cost": 500,
        "effective_from": "2026-11-01"})
    assert denied.status_code == 403

    elected = client.post("/api/benefits/elections", headers=_hdr(people["employee"]), json={
        "employee_id": me, "benefit_plan_id": plan, "coverage_tier": "self", "employee_cost": 500,
        "effective_from": "2026-11-01"})
    assert elected.status_code == 201, elected.text

    rows = client.get("/api/tables/benefit_election", headers=people["hr"], params={"employee_id": me}).json()["rows"]
    assert any(r["coverage_tier"] == "self" for r in rows)
    # The employee's own column access on coverage_tier/employee_cost is READ, not WRITE --
    # confirmed by the fact the only way to get here was the agent_ben-run endpoint, not a direct
    # table write (benefit_election is deliberately not in access.DIRECT_WRITE_TABLES).
    direct = client.post("/api/tables/benefit_election", headers=_hdr(people["employee"]), json={
        "employee_id": me, "benefit_plan_id": plan, "coverage_tier": "family", "employee_cost": 900,
        "effective_from": "2026-12-01"})
    assert direct.status_code == 403 and direct.json()["error"]["code"] == "not_directly_writable"


def test_expense_submission_and_manager_approval_through_g_expense(client, people):
    submitted = client.post("/api/expenses", headers=_hdr(people["employee"]), json={
        "amount": 1500, "category": "travel"})
    assert submitted.status_code == 201, submitted.text
    approval_id = submitted.json()["approval_request_id"]

    pending = client.get("/api/approvals", headers=people["manager"], params={"status": "pending"}).json()["approvals"]
    gate = next(a for a in pending if a["id"] == approval_id)
    assert gate["gate_type"] == "g_expense" and gate["can_resolve"] is True

    resolved = client.post(f"/api/approvals/{approval_id}/resolve", headers=people["manager"], json={"decision": "approved"})
    assert resolved.status_code == 200, resolved.text

    rows = client.get("/api/tables/expense", headers=people["employee"]).json()["rows"]
    assert any(r["id"] == submitted.json()["expense_id"] for r in rows)


def test_payroll_filing_and_gl_posting(client, people):
    """FE-10: statutory filings and a GL journal entry, after a run is built and disbursed."""
    loc = client.get("/api/tables/location", headers=people["hr"]).json()["rows"]
    location = next(l for l in loc if l["country_code"] == "IN")
    retention = client.get("/api/tables/retention_policy", headers=people["hr"]).json()["rows"][0]["id"]
    year = 2040 + (hash(location["id"]) % 9)
    period_start, period_end = f"{year}-06-01", f"{year}-06-30"

    created = client.post("/api/payroll/runs", headers=_hdr(people["payroll"]), json={
        "legal_entity_id": location["legal_entity_id"], "period_start": period_start, "period_end": period_end,
        "retention_class_id": retention})
    assert created.status_code == 201, created.text
    run_id = created.json()["payroll_run_id"]
    anomaly_id = created.json()["anomaly_check"]["approval_request_id"]
    client.post(f"/api/approvals/{anomaly_id}/resolve", headers=people["ops"], json={"decision": "approved"})

    disbursal = client.post(f"/api/payroll/runs/{run_id}/request-disbursal", headers=_hdr(people["payroll"])).json()
    client.post(f"/api/approvals/{disbursal['approval_request_id']}/resolve", headers=people["founder"], json={"decision": "approved"})
    disbursed = client.post(f"/api/payroll/runs/{run_id}/disburse", headers=_hdr(people["payroll"]),
                            json={"approval_request_id": disbursal["approval_request_id"]})
    assert disbursed.status_code == 200, disbursed.text
    client.post(f"/api/payroll/runs/{run_id}/issue-payslips", headers=_hdr(people["payroll"]))

    filed = client.post(f"/api/payroll/runs/{run_id}/file", headers=_hdr(people["payroll"]), json={
        "period": f"{year}-06", "retention_class_id": retention})
    assert filed.status_code == 201, filed.text
    assert len(filed.json()["filing_ids"]) == 2  # India: ecr, 24q

    gl_opened = client.post(f"/api/payroll/runs/{run_id}/gl", headers=_hdr(people["payroll"]))
    assert gl_opened.status_code == 201, gl_opened.text
    gl_id, close_approval_id = gl_opened.json()["gl_journal_entry_id"], gl_opened.json()["approval_request_id"]

    too_early = client.post(f"/api/payroll/gl/{gl_id}/post", headers=_hdr(people["payroll"]),
                            json={"approval_request_id": close_approval_id})
    assert too_early.status_code == 409

    client.post(f"/api/approvals/{close_approval_id}/resolve", headers=people["founder"], json={"decision": "approved"})
    posted = client.post(f"/api/payroll/gl/{gl_id}/post", headers=_hdr(people["payroll"]),
                         json={"approval_request_id": close_approval_id})
    assert posted.status_code == 200 and posted.json()["status"] == "posted"

    rows = client.get("/api/tables/gl_journal_entry", headers=people["payroll"], params={"id": gl_id}).json()["rows"]
    assert rows[0]["posted_at"] is not None


def test_generic_table_writes_handle_jsonb_columns(client, people):
    """Regression: POST /tables/{table} builds `INSERT ... VALUES (:col)` for every column with
    no cast; a jsonb column sent as a JS object (not a pre-serialized string -- exactly what
    ModelForm sends) made psycopg raise 'cannot adapt type dict', surfaced to callers as a bare
    500. leave_policy.accrual_rule is the first jsonb column any DIRECT_WRITE_TABLES entry
    actually writes through this path."""
    legal_entity = client.get("/api/tables/legal_entity", headers=people["hr"]).json()["rows"][0]["id"]
    created = client.post("/api/tables/leave_policy", headers=_hdr(people["hr"]), json={
        "legal_entity_id": legal_entity, "leave_type": "annual", "accrual_rule": {"days_per_month": 1.5},
        "carry_forward_cap": 15})
    assert created.status_code == 201, created.text
    rows = client.get("/api/tables/leave_policy", headers=people["hr"], params={"id": created.json()["id"]}).json()["rows"]
    assert rows[0]["accrual_rule"] == {"days_per_month": 1.5}

    updated = client.patch(f"/api/tables/leave_policy/{created.json()['id']}", headers=people["hr"], json={
        "accrual_rule": {"days_per_month": 2}})
    assert updated.status_code == 200, updated.text
    rows = client.get("/api/tables/leave_policy", headers=people["hr"], params={"id": created.json()["id"]}).json()["rows"]
    assert rows[0]["accrual_rule"] == {"days_per_month": 2}


def test_statutory_rate_rule_table_grant_is_misleading_for_ops(client, people):
    """New finding: statutory_rate_rule/pt_slab_rule's table_acl shows daydor_ops at write level
    (matching docs/sprint-plan.md's claim that ops maintains these jurisdiction packs), but the
    real per-column GRANT in 0003_model_security.sql gives INSERT/UPDATE to daydor_admin only --
    ops gets SELECT. The same "table grant is a summary" shape as finding 16, one table over."""
    denied = client.post("/api/tables/statutory_rate_rule", headers=_hdr(people["ops"]), json={
        "scheme": "pf", "jurisdiction_code": "IN", "effective_from": "2026-01-01",
        "employee_rate": 0.12, "employer_rate": 0.12})
    assert denied.status_code == 403
    # Readable, at least, confirming this is a write-only restriction.
    readable = client.get("/api/tables/statutory_rate_rule", headers=people["ops"])
    assert readable.status_code == 200
