"""Phase D over HTTP: the inbox and a tenant's controls over its workers (backend 0044), against the real database."""
import pytest


@pytest.fixture
def restore_controls(client, people):
    yield
    for w in ("requisition-drafter",):
        client.put(f"/api/worker-controls/{w}", headers=people["hr"], json={"autonomy": None, "enabled": True})


def test_the_inbox_is_for_roles_that_decide_things(client, people):
    for who in ("founder", "hr", "payroll", "it", "ops"):
        r = client.get("/api/inbox", headers=people[who])
        assert r.status_code == 200, who
        body = r.json()
        assert set(body["counts"]) == {"approval", "review", "notification"} and isinstance(body["items"], list)
    for who in ("employee", "manager", "auditor"):
        assert client.get("/api/inbox", headers=people[who]).status_code == 403


def test_a_pending_approval_shows_in_the_inbox_of_a_role_that_may_decide_it(client, people):
    founder = client.get("/api/inbox", headers=people["founder"]).json()
    approvals = [i for i in founder["items"] if i["kind"] == "approval"]
    for item in approvals:
        assert item["state"] in {"waiting", "overdue", "escalated"} and item["title"]
    assert founder["counts"]["approval"] == len(approvals)


def test_acknowledging_or_dismissing_something_that_is_not_there_is_a_clean_error(client, people):
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.post(f"/api/inbox/reviews/{missing}/acknowledge", headers=people["hr"]).status_code >= 400
    assert client.post(f"/api/inbox/notifications/{missing}/dismiss", headers=people["hr"]).status_code >= 400
    assert client.post(f"/api/inbox/reviews/{missing}/acknowledge", headers=people["employee"]).status_code == 403


def test_hr_sees_every_worker_and_what_it_may_do(client, people):
    r = client.get("/api/worker-controls", headers=people["hr"])
    assert r.status_code == 200
    workers = {w["worker"]: w for w in r.json()["workers"]}
    assert "requisition-drafter" in workers and "workflow-engine" not in workers
    drafter = workers["requisition-drafter"]
    assert drafter["rollout_stage"] == "shadow"                                         # an LLM worker starts in shadow
    assert drafter["allowed_autonomy"][-1] == "approve" and drafter["default_autonomy"] in drafter["allowed_autonomy"]
    assert workers["gl-poster"]["rollout_stage"] is None                                # not an LLM worker
    assert client.get("/api/worker-controls", headers=people["payroll"]).status_code == 403


def test_a_tenant_can_be_more_careful_never_less_and_can_switch_a_worker_off(client, people, restore_controls):
    got = client.put("/api/worker-controls/requisition-drafter", headers=people["hr"], json={"autonomy": "approve"})
    assert got.status_code == 200 and got.json()["effective_autonomy"] == "approve"
    row = next(w for w in client.get("/api/worker-controls", headers=people["founder"]).json()["workers"] if w["worker"] == "requisition-drafter")
    assert row["tenant_autonomy"] == "approve" and row["effective_autonomy"] == "approve"
    off = client.put("/api/worker-controls/requisition-drafter", headers=people["founder"], json={"autonomy": None, "enabled": False})
    assert off.status_code == 200
    row = next(w for w in client.get("/api/worker-controls", headers=people["hr"]).json()["workers"] if w["worker"] == "requisition-drafter")
    assert row["tenant_enabled"] is False
    default = row["default_autonomy"]
    if default != "auto":
        low = client.put("/api/worker-controls/requisition-drafter", headers=people["hr"], json={"autonomy": "auto"})
        assert low.status_code == 422 and low.json()["error"]["code"] == "autonomy_too_low"


def test_unknown_and_platform_workers_and_the_wrong_roles_are_refused(client, people):
    for name in ("no-such-worker", "workflow-engine"):
        assert client.put(f"/api/worker-controls/{name}", headers=people["hr"], json={"autonomy": "approve"}).status_code == 404
    for who in ("payroll", "it", "employee", "ops"):
        assert client.put("/api/worker-controls/requisition-drafter", headers=people[who], json={"autonomy": "approve"}).status_code == 403
    assert client.put("/api/worker-controls/requisition-drafter", headers=people["hr"], json={"autonomy": "bogus"}).status_code == 422
