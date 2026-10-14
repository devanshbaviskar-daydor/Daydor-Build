"""Phase D: approval deadlines and escalation, notifications, the inbox, tenant worker controls, recurring platform timers."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from daydor import approval_sla, notifications, schedules
from daydor.agents.session import worker_session
from daydor.db.session import tenant_session
from daydor.gates.hard import request_approval, resolve
from daydor.queue import Worker, emit_event
from tests.factories import insert


@pytest.fixture
def own(engine):
    """A tenant of its own with one person per approving role, so counts are exact."""
    with engine.begin() as conn:
        tenant = insert(conn, "tenant", legal_name="Inbox Co", status="active")
        users = {r: insert(conn, "app_user", tenant_id=tenant, role=r) for r in ("founder", "hr", "payroll", "it")}
        users["ops"] = insert(conn, "app_user", role="ops")
        conn.execute(text("INSERT INTO app.ops_tenant_assignment (user_id, tenant_id) VALUES (:u, :t)"), {"u": users["ops"], "t": tenant})
    return {"tenant": tenant, "user": users}


def as_(engine, own, role):
    return tenant_session(engine, f"tenant_{role}" if role != "ops" else "daydor_ops", own["tenant"], user_id=own["user"][role])


def ask(engine, own, gate="g_close", **kw):
    with worker_session(engine, "gl-poster", own["tenant"]) as conn:
        return request_approval(conn, gate, "gl_journal_entry", uuid.uuid4(), **kw)


def sweep(engine, own, now=None):
    with worker_session(engine, "root-orchestrator", own["tenant"]) as conn:
        return conn.execute(text("SELECT app.sweep_approvals(COALESCE(CAST(:n AS timestamptz), now()))"), {"n": now}).scalar_one()


def approval(engine, rid):
    with engine.connect() as conn:
        return conn.execute(text("SELECT status, created_at, deadline_at, escalated_at FROM approval_request WHERE id = :i"), {"i": rid}).one()


# ------------------------------------------------------------------ deadlines and escalation
def test_every_pending_approval_gets_the_gates_response_window_and_urgent_gates_get_less(engine, own):
    a, b = ask(engine, own), ask(engine, own, "g_agent_action")
    assert sweep(engine, own) == 0
    assert approval(engine, a).deadline_at - approval(engine, a).created_at == timedelta(hours=48)
    assert approval(engine, b).deadline_at - approval(engine, b).created_at == timedelta(hours=48)
    with worker_session(engine, "direct-deposit-disburser", own["tenant"]) as conn:
        c = request_approval(conn, "g_pay_disburse", "payroll_run", uuid.uuid4())
    sweep(engine, own)
    assert approval(engine, c).deadline_at - approval(engine, c).created_at == timedelta(hours=24)


def test_a_deadline_the_requester_set_is_kept(engine, own):
    when = datetime.now(timezone.utc) + timedelta(hours=5)
    rid = ask(engine, own, deadline_at=when)
    sweep(engine, own)
    assert abs((approval(engine, rid).deadline_at - when).total_seconds()) < 1


def test_a_late_approval_is_escalated_once_and_only_notifies(engine, own):
    rid = ask(engine, own)
    sweep(engine, own)
    assert sweep(engine, own, datetime.now(timezone.utc) + timedelta(hours=47)) == 0
    late = datetime.now(timezone.utc) + timedelta(hours=49)
    assert sweep(engine, own, late) == 1 and sweep(engine, own, late) == 0           # once
    row = approval(engine, rid)
    assert row.status == "pending" and row.escalated_at is not None                  # nothing was decided or expired
    with engine.connect() as conn:
        ev = conn.execute(text("SELECT payload FROM app.outbox WHERE topic = 'approval.escalated' AND subject_id = :s"), {"s": rid}).one()
    assert ev.payload["escalate_to"] == "tenant_founder" and ev.payload["gate_label"] == "Period close and GL posting"
    # who may decide is unchanged: g_close is payroll or the founder, never IT, however late it is
    with pytest.raises(DBAPIError, match="cannot resolve"):
        with as_(engine, own, "it") as conn:
            resolve(conn, rid, "approved")
    with as_(engine, own, "payroll") as conn:
        assert resolve(conn, rid, "approved") == "approved"


def test_a_resolved_request_is_never_escalated_and_tenants_do_not_touch_each_other(engine, own, org):
    rid = ask(engine, own)
    with as_(engine, own, "founder") as conn:
        resolve(conn, rid, "approved")
    assert sweep(engine, own, datetime.now(timezone.utc) + timedelta(days=30)) == 0
    assert approval(engine, rid).escalated_at is None
    with worker_session(engine, "root-orchestrator", org.tenant_b) as conn:
        assert conn.execute(text("SELECT app.sweep_approvals(now() + interval '90 days')")).scalar_one() >= 0
    other = ask(engine, own)
    with worker_session(engine, "root-orchestrator", org.tenant_b) as conn:
        conn.execute(text("SELECT app.sweep_approvals(now() + interval '90 days')"))
    assert approval(engine, other).deadline_at is None                                 # tenant B's sweep did not reach it


def test_only_the_platform_and_ops_run_the_sweep(engine, own):
    for role in ("tenant_founder", "tenant_hr"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            with tenant_session(engine, role, own["tenant"]) as conn:
                conn.execute(text("SELECT app.sweep_approvals()"))
    with pytest.raises(ProgrammingError, match="permission denied"):
        with worker_session(engine, "gl-poster", own["tenant"]) as conn:
            conn.execute(text("SELECT app.sweep_approvals()"))


def test_the_hourly_sweep_chain_runs_from_the_queue_and_schedules_the_next_hour(engine, own):
    with worker_session(engine, "root-orchestrator", own["tenant"]) as conn:
        approval_sla.start_sweep(conn, at=datetime.now(timezone.utc) - timedelta(hours=2))
        approval_sla.start_sweep(conn, at=datetime.now(timezone.utc) - timedelta(hours=2))      # idempotent
    w = Worker(engine, "platform", f"sweep-{uuid.uuid4().hex[:6]}")
    w.register(approval_sla.KIND, worker="root-orchestrator", fn=approval_sla.handle_approval_sweep)
    assert w.tick()["succeeded"] >= 1
    nxt = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("approval-sweep-%Y%m%d%H")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM app.timer WHERE tenant_id = :t AND timer_key = :k"),
                            {"t": own["tenant"], "k": nxt}).scalar_one() == 1


# ------------------------------------------------------------------ notifications from events
def drain_notify(engine):
    w = Worker(engine, notifications.QUEUE, f"n-{uuid.uuid4().hex[:6]}")
    w.register(notifications.KIND, worker="root-orchestrator", fn=notifications.handle_notify_event)
    total: dict[str, int] = {}
    for _ in range(10):                      # other tests leave events too; a tick takes ten jobs
        out = w.tick()
        for k, v in out.items():
            total[k] = total.get(k, 0) + v
        if not out.get("succeeded"):
            break
    return total


def notes(engine, own, role):
    with as_(engine, own, role) as conn:
        return conn.execute(text("SELECT kind, severity, title, subject_id FROM app.notification WHERE dismissed_at IS NULL ORDER BY created_at")).all()


def test_a_clock_event_becomes_a_notification_for_the_role_that_owns_it_and_a_redelivery_adds_nothing(engine, own):
    subject = uuid.uuid4()
    data = {"clock": "cobra_notice", "label": "COBRA notice due", "due_on": "2026-11-01", "owner": "hr"}
    with worker_session(engine, "root-orchestrator", own["tenant"]) as conn:
        emit_event(conn, "clock.due_soon", "cobra_event", subject, data)
        emit_event(conn, "clock.due_soon", "cobra_event", subject, {**data, "again": True})     # same clock, same subject
        emit_event(conn, "clock.overdue", "cobra_event", subject, data)
    assert drain_notify(engine)["succeeded"] >= 3
    hr = notes(engine, own, "hr")
    assert [(n.severity, n.title) for n in hr] == [("due_soon", "COBRA notice due: due 2026-11-01"),
                                                   ("overdue", "COBRA notice due: overdue since 2026-11-01")]
    assert notes(engine, own, "payroll") == [] and notes(engine, own, "it") == []          # not addressed to them, and row security hides it
    assert len(notes(engine, own, "founder")) == 2


def test_an_escalation_reaches_the_founder_through_the_queue(engine, own):
    rid = ask(engine, own)
    sweep(engine, own)
    sweep(engine, own, datetime.now(timezone.utc) + timedelta(hours=49))
    with engine.begin() as conn:
        conn.execute(text("UPDATE app.outbox SET published_at = NULL WHERE subject_id = :s"), {"s": rid})
    drain_notify(engine)
    drain_notify(engine)
    (n,) = notes(engine, own, "founder")
    assert (n.severity, n.title, n.subject_id) == ("escalated", "Waiting too long: Period close and GL posting", rid)


def test_an_unknown_topic_is_ignored(engine, own):
    from daydor.queue.worker import Job
    out = notifications.handle_notify_event(None, Job(uuid.uuid4(), own["tenant"], "notify", "notify.event", {"topic": "nope"}, 1, 5))
    assert out == {"ignored": "nope"}


def test_notifications_are_written_only_by_the_platform_and_dismissed_only_by_the_audience(engine, own):
    with worker_session(engine, "root-orchestrator", own["tenant"]) as conn:
        nid = conn.execute(text("SELECT app.notify('tenant_hr', 'clock', 'overdue', 'x', NULL, NULL, '{}', :k)"), {"k": uuid.uuid4().hex}).scalar_one()
    for role in ("founder", "hr"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            with as_(engine, own, role) as conn:
                conn.execute(text("SELECT app.notify('tenant_hr', 'clock', 'overdue', 'x', NULL, NULL, '{}', 'k')"))
        with pytest.raises(ProgrammingError, match="permission denied"):
            with as_(engine, own, role) as conn:
                conn.execute(text("UPDATE app.notification SET dismissed_at = now()"))
    with pytest.raises(DBAPIError, match="not found"):
        with as_(engine, own, "payroll") as conn:
            conn.execute(text("SELECT app.dismiss_notification(:n)"), {"n": nid})
    with pytest.raises(DBAPIError, match="signed-in user"):
        with tenant_session(engine, "tenant_hr", own["tenant"]) as conn:
            conn.execute(text("SELECT app.dismiss_notification(:n)"), {"n": nid})
    with as_(engine, own, "hr") as conn:
        conn.execute(text("SELECT app.dismiss_notification(:n)"), {"n": nid})
    assert notes(engine, own, "hr") == []


# ------------------------------------------------------------------ the inbox
def inbox(engine, own, role):
    with as_(engine, own, role) as conn:
        return conn.execute(text("SELECT * FROM app.inbox()")).all()


def test_the_inbox_lists_what_this_role_may_decide_most_urgent_first(engine, own):
    old = ask(engine, own)                                  # g_close: payroll or founder
    new = ask(engine, own, "g_agent_action")                # anyone
    sweep(engine, own)
    sweep(engine, own, datetime.now(timezone.utc) + timedelta(hours=49))      # both escalated; reset one to plain "waiting"
    with engine.begin() as conn:
        conn.execute(text("UPDATE approval_request SET escalated_at = NULL, deadline_at = now() + interval '1 day' WHERE id = :i"), {"i": new})
    pay = inbox(engine, own, "payroll")
    assert [(i.kind, i.state, i.id) for i in pay] == [("approval", "escalated", old), ("approval", "waiting", new)]
    assert pay[0].title == "Period close and GL posting"
    assert [i.id for i in inbox(engine, own, "it")] == [new]               # IT may not decide g_close, so it is not in its inbox
    assert {i.id for i in inbox(engine, own, "founder")} == {old, new}


def test_my_own_request_is_marked_so_i_know_i_cannot_decide_it(engine, own):
    with as_(engine, own, "payroll") as conn:
        mine = request_approval(conn, "g_close", "gl_journal_entry", uuid.uuid4())
    (item,) = [i for i in inbox(engine, own, "payroll") if i.id == mine]
    assert item.detail["requested_by_me"] is True
    (item,) = [i for i in inbox(engine, own, "founder") if i.id == mine]
    assert item.detail["requested_by_me"] is False


def test_agent_runs_waiting_for_review_go_to_the_workers_owner_and_the_founder(engine, own):
    with engine.begin() as conn:
        run = insert(conn, "agent_task_run", tenant_id=own["tenant"], worker_name="requisition-drafter", domain="ta",
                     status="review_pending", idempotency_key=f"k-{uuid.uuid4().hex}", input_ref="job:x")
    assert [i.id for i in inbox(engine, own, "hr") if i.kind == "review"] == [run]
    assert [i.id for i in inbox(engine, own, "founder") if i.kind == "review"] == [run]
    assert [i for i in inbox(engine, own, "payroll") if i.kind == "review"] == []
    (item,) = [i for i in inbox(engine, own, "hr") if i.kind == "review"]
    assert item.state == "review" and item.detail["worker"] == "requisition-drafter"


def test_the_inbox_is_per_tenant_and_not_open_to_everyone(engine, own, org):
    ask(engine, own)
    with tenant_session(engine, "tenant_founder", org.tenant_a) as conn:
        assert conn.execute(text("SELECT count(*) FROM app.inbox() WHERE subject_table = 'gl_journal_entry' AND since > now() - interval '1 minute'")).scalar_one() == 0
    for role in ("tenant_employee", "tenant_manager", "external_auditor"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            with tenant_session(engine, role, own["tenant"]) as conn:
                conn.execute(text("SELECT * FROM app.inbox()"))


# ------------------------------------------------------------------ tenant worker controls
def controls(engine, own, role="hr"):
    with as_(engine, own, role) as conn:
        return {r.worker: r for r in conn.execute(text("SELECT * FROM app.tenant_worker_controls()")).all()}


def test_a_tenant_sees_every_real_worker_and_no_platform_actor(engine, own):
    c = controls(engine, own)
    assert "requisition-drafter" in c and "gl-poster" in c
    assert not {"workflow-engine", "root-orchestrator", "hire-intake", "exit-intake"} & set(c)
    assert c["requisition-drafter"].effective_autonomy == c["requisition-drafter"].default_autonomy


def test_a_tenant_can_be_more_careful_never_less_and_switch_a_worker_off(engine, own):
    default = controls(engine, own)["requisition-drafter"].default_autonomy
    with as_(engine, own, "hr") as conn:
        assert conn.execute(text("SELECT app.set_worker_control('requisition-drafter', 'approve', true)")).scalar_one() == "approve"
    assert controls(engine, own)["requisition-drafter"].tenant_autonomy == "approve"
    with pytest.raises(DBAPIError, match="cannot raise autonomy"):
        with as_(engine, own, "founder") as conn:
            conn.execute(text("SELECT app.set_worker_control('requisition-drafter', 'auto', true)"))
    with as_(engine, own, "founder") as conn:
        conn.execute(text("SELECT app.set_worker_control('requisition-drafter', NULL, false)"))
    c = controls(engine, own)["requisition-drafter"]
    assert (c.tenant_autonomy, c.tenant_enabled, c.effective_autonomy) == (None, False, default)


def test_platform_actors_other_roles_and_other_tenants_are_out(engine, own, org):
    with pytest.raises(DBAPIError, match="platform actor"):
        with as_(engine, own, "hr") as conn:
            conn.execute(text("SELECT app.set_worker_control('workflow-engine', 'approve', true)"))
    for role in ("payroll", "it"):
        with pytest.raises(ProgrammingError, match="permission denied"):       # not even granted; the function checks the role again
            with as_(engine, own, role) as conn:
                conn.execute(text("SELECT app.set_worker_control('requisition-drafter', 'approve', true)"))
    with as_(engine, own, "hr") as conn:
        conn.execute(text("SELECT app.set_worker_control('requisition-drafter', 'approve', true)"))
    with tenant_session(engine, "tenant_hr", org.tenant_b) as conn:
        assert {r.worker: r.tenant_autonomy for r in conn.execute(text("SELECT * FROM app.tenant_worker_controls()"))}["requisition-drafter"] is None
    with engine.connect() as conn:
        ev = conn.execute(text("SELECT payload FROM app.outbox WHERE topic = 'worker.policy_changed' AND tenant_id = :t ORDER BY id DESC LIMIT 1"),
                          {"t": own["tenant"]}).one()
    assert ev.payload["worker"] == "requisition-drafter" and ev.payload["by"] == str(own["user"]["hr"])


# ------------------------------------------------------------------ recurring timers for every tenant
def test_the_platform_starts_its_recurring_timers_for_every_active_tenant_and_only_them(engine, own):
    with engine.begin() as conn:
        dead = insert(conn, "tenant", legal_name="Gone Co", status="suspended")
    n = schedules.ensure_platform_schedules(engine)
    assert n >= 1
    assert schedules.ensure_platform_schedules(engine) == n                                        # idempotent
    with engine.connect() as conn:
        kinds = {r.kind for r in conn.execute(text("SELECT kind FROM app.timer WHERE tenant_id = :t"), {"t": own["tenant"]})}
        assert {"statutory_clock_scan", "approval_sweep"} <= kinds
        assert conn.execute(text("SELECT count(*) FROM app.timer WHERE tenant_id = :t"), {"t": dead}).scalar_one() == 0
