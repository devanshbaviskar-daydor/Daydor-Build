"""Phase A of the agentic infrastructure (0040): one run per worker job, and autonomy that holds or flags it."""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from daydor.agents import runs
from daydor.agents.session import worker_session
from daydor.db.session import tenant_session
from daydor.queue import Worker, enqueue

pytestmark = pytest.mark.usefixtures("org")


def queue_name() -> str:
    return f"q_{uuid.uuid4().hex[:8]}"


def enq(engine, org, queue, kind="work", payload=None, key=None):
    with worker_session(engine, "workflow-engine", org.tenant_a) as conn:
        return enqueue(conn, queue, kind, payload or {}, idempotency_key=key)


def run_rows(engine, org, worker=None):
    with engine.connect() as conn:
        return conn.execute(text("SELECT * FROM agent_task_run WHERE tenant_id = :t AND (CAST(:w AS text) IS NULL OR worker_name = :w) "
                                 "ORDER BY created_at"), {"t": org.tenant_a, "w": worker}).all()


def set_policy(engine, org, worker, autonomy):
    with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
        conn.execute(text("INSERT INTO app.worker_tenant_policy (worker, autonomy) VALUES (:w, :a) "
                          "ON CONFLICT (tenant_id, worker) DO UPDATE SET autonomy = EXCLUDED.autonomy"), {"w": worker, "a": autonomy})


def clear_policy(engine, org, worker):
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL ROLE daydor_schema_owner"))
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(org.tenant_a)})
        conn.execute(text("DELETE FROM app.worker_tenant_policy WHERE tenant_id = :t AND worker = :w"), {"t": org.tenant_a, "w": worker})


# ------------------------------------------------------------------ the trace spine
def test_every_worker_job_leaves_one_run_that_is_closed_in_its_own_transaction(engine, org):
    q, calls = queue_name(), []
    jid = enq(engine, org, q)
    w = Worker(engine, q, "w1")
    w.register("work", worker="job-posting-publisher", fn=lambda conn, job: calls.append(job.id) or {"ok": 1})
    assert w.tick()["succeeded"] == 1 and calls == [jid]
    (r,) = [r for r in run_rows(engine, org, "job-posting-publisher") if r.input_ref == f"job:{jid}"]
    assert (r.status, r.idempotency_key, r.domain) == ("succeeded", f"job:{jid}", "ta")
    assert r.started_at and r.finished_at and r.error_code is None


def test_a_failed_job_still_leaves_a_record_and_the_retry_reuses_it(engine, org):
    q, attempts = queue_name(), []
    jid = enq(engine, org, q)

    def flaky(conn, job):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("carrier down")
        return {"ok": True}

    w = Worker(engine, q, "w1")
    w.register("work", worker="job-posting-publisher", fn=flaky)
    assert w.tick().get("queued") == 1                                                  # failed, will retry
    (r,) = [r for r in run_rows(engine, org, "job-posting-publisher") if r.input_ref == f"job:{jid}"]
    assert (r.status, r.error_code) == ("failed", "RuntimeError")
    with engine.begin() as conn:
        conn.execute(text("UPDATE app.job SET run_at = now() WHERE id = :j"), {"j": jid})
    assert w.tick()["succeeded"] == 1
    rows = [r for r in run_rows(engine, org, "job-posting-publisher") if r.input_ref == f"job:{jid}"]
    assert len(rows) == 1 and rows[0].status == "succeeded" and rows[0].error_code is None and len(attempts) == 2


def test_a_duplicate_delivery_of_finished_work_does_not_run_the_handler_again(engine, org):
    q, calls = queue_name(), []
    jid = enq(engine, org, q)
    w = Worker(engine, q, "w1")
    w.register("work", worker="job-posting-publisher", fn=lambda conn, job: calls.append(1) or {})
    w.tick()
    with engine.begin() as conn:                                                         # the queue redelivers it
        conn.execute(text("UPDATE app.job SET status = 'queued', run_at = now() WHERE id = :j"), {"j": jid})
    assert w.tick().get("skipped") == 1 and calls == [1]


def test_the_handler_writes_under_its_run_so_audit_rows_link_to_it(engine, org):
    q = queue_name()
    jid = enq(engine, org, q)

    def handler(conn, job):
        conn.execute(text("INSERT INTO audit_log (actor_kind, agent_task_run_id, event_type, subject_table, subject_id, occurred_at) "
                          "VALUES ('agent', app.agent_task_run_id(), 'test.traced', 'employee', :e, now())"), {"e": org.emp["report"]})
        return {}

    w = Worker(engine, q, "w1")
    w.register("work", worker="job-posting-publisher", fn=handler)
    w.tick()
    (r,) = [r for r in run_rows(engine, org, "job-posting-publisher") if r.input_ref == f"job:{jid}"]
    with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
        trace = conn.execute(text("SELECT kind, ref, detail FROM app.agent_run_trace(:r)"), {"r": r.id}).all()
    kinds = [t.kind for t in trace]
    assert kinds.count("run") == 1 and kinds.count("job") == 1 and kinds.count("audit") == 1
    assert next(t for t in trace if t.kind == "job").detail["status"] == "succeeded"
    assert next(t for t in trace if t.kind == "audit").detail["event"] == "test.traced"


def test_a_trace_includes_the_workflow_instance_a_job_belongs_to(engine, org):
    q = queue_name()
    with worker_session(engine, "payroll-anomaly-detector", org.tenant_a) as conn:
        run_row = conn.execute(text("SELECT id FROM app.workflow_instance LIMIT 1")).first()
    wid = None
    if run_row is None:                                                                  # make one to point at
        from daydor.workflow.engine import WorkflowEngine
        with engine.begin() as conn:
            from tests.factories import insert
            retention = insert(conn, "retention_policy")
            run_id = insert(conn, "payroll_run", tenant_id=org.tenant_a, legal_entity_id=org.legal_entity_a, status="built",
                            gross_total=1, net_total=1, anomaly_score=0.0, retention_class=retention)
        with worker_session(engine, "payroll-anomaly-detector", org.tenant_a) as conn:
            wid = WorkflowEngine().start(conn, "payroll", "payroll_run", run_id)
    else:
        wid = run_row.id
    jid = enq(engine, org, q, payload={"workflow_instance_id": str(wid)})
    w = Worker(engine, q, "w1")
    w.register("work", worker="job-posting-publisher", fn=lambda conn, job: {})
    w.tick()
    (r,) = [r for r in run_rows(engine, org, "job-posting-publisher") if r.input_ref == f"job:{jid}"]
    with tenant_session(engine, "daydor_ops", org.tenant_a, user_id=org.user["ops"]) as conn:
        trace = {t.kind: t for t in conn.execute(text("SELECT kind, ref, detail FROM app.agent_run_trace(:r)"), {"r": r.id})}
    assert trace["workflow_instance"].ref == str(wid)


def test_a_worker_cannot_open_or_close_another_workers_run(engine, org):
    with worker_session(engine, "job-posting-publisher", org.tenant_a) as conn:
        mine = conn.execute(text("SELECT run_id FROM app.begin_agent_run('job-posting-publisher', :k, 'x')"),
                            {"k": f"k-{uuid.uuid4().hex}"}).scalar_one()
    with pytest.raises(DBAPIError, match="may not open a run for gl-poster"):
        with worker_session(engine, "job-posting-publisher", org.tenant_a) as conn:
            conn.execute(text("SELECT * FROM app.begin_agent_run('gl-poster', :k, 'x')"), {"k": f"k-{uuid.uuid4().hex}"})
    with pytest.raises(DBAPIError, match="may not close a run of job-posting-publisher"):
        with worker_session(engine, "gl-poster", org.tenant_a) as conn:
            conn.execute(text("SELECT app.finish_agent_run(:r, 'succeeded')"), {"r": mine})
    with pytest.raises(DBAPIError, match="cannot set a run to rejected"):
        with worker_session(engine, "job-posting-publisher", org.tenant_a) as conn:
            conn.execute(text("SELECT app.finish_agent_run(:r, 'rejected')"), {"r": mine})


def test_people_and_other_roles_cannot_open_runs_and_workers_cannot_write_the_table(engine, org):
    for role in ("tenant_hr", "tenant_founder", "daydor_ops"):
        with pytest.raises(ProgrammingError, match="permission denied for function begin_agent_run"):
            with tenant_session(engine, role, org.tenant_a, user_id=org.user["ops"]) as conn:
                conn.execute(text("SELECT * FROM app.begin_agent_run('gl-poster', 'k', 'x')"))
    with pytest.raises(ProgrammingError, match="permission denied"):
        with worker_session(engine, "gl-poster", org.tenant_a) as conn:
            conn.execute(text("UPDATE agent_task_run SET status = 'succeeded'"))


def test_runs_are_tenant_isolated(engine, org):
    q = queue_name()
    enq(engine, org, q)
    Worker(engine, q, "w1")
    w = Worker(engine, q, "w1")
    w.register("work", worker="job-posting-publisher", fn=lambda conn, job: {})
    w.tick()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM agent_task_run WHERE tenant_id = :t"), {"t": org.tenant_b}).scalar_one() == 0
    assert run_rows(engine, org, "job-posting-publisher")


def test_platform_actors_get_no_runs(engine, org):
    q = queue_name()
    enq(engine, org, q)
    before = len(run_rows(engine, org))
    w = Worker(engine, q, "w1")
    w.register("work", worker="workflow-engine", fn=lambda conn, job: {})
    assert w.tick()["succeeded"] == 1 and len(run_rows(engine, org)) == before


def test_a_disabled_worker_fails_closed_and_leaves_no_run(engine, org):
    q = queue_name()
    jid = enq(engine, org, q)
    with tenant_session(engine, "daydor_ops") as conn:
        conn.execute(text("UPDATE app.worker_definition SET enabled = false WHERE worker = 'job-posting-publisher'"))
    try:
        w = Worker(engine, q, "w1")
        w.register("work", worker="job-posting-publisher", fn=lambda conn, job: {})
        assert w.tick().get("queued") == 1
    finally:
        with tenant_session(engine, "daydor_ops") as conn:
            conn.execute(text("UPDATE app.worker_definition SET enabled = true WHERE worker = 'job-posting-publisher'"))
    assert [r for r in run_rows(engine, org, "job-posting-publisher") if r.input_ref == f"job:{jid}"] == []


# ------------------------------------------------------------------ autonomy
class Settler:
    """Drains the agent-runs queue: every gate resolution in the whole suite lands there, so one batch is not enough."""
    def __init__(self, engine):
        self.w = Worker(engine, runs.SETTLE_QUEUE, "settler", batch=200)
        self.w.register(runs.SETTLE_KIND, worker="workflow-engine", fn=runs.handle_agent_gate_resolved)

    def tick(self):
        for _ in range(200):                                    # the outbox relays 100 events per tick
            out = self.w.tick()
            if not out["relayed"] and not set(out) - {"relayed", "timers_fired"}:
                break


def settler(engine):
    return Settler(engine)


def test_a_tenant_that_raises_a_workers_autonomy_to_approve_holds_its_jobs_until_a_person_says_yes(engine, org):
    q, calls = queue_name(), []
    jid = enq(engine, org, q)
    w = Worker(engine, q, "w1")
    w.register("work", worker="job-posting-publisher", fn=lambda conn, job: calls.append(1) or {"did": "it"})   # default: review
    set_policy(engine, org, "job-posting-publisher", "approve")
    try:
        assert w.tick().get("held") == 1 and calls == []
        (r,) = [r for r in run_rows(engine, org, "job-posting-publisher") if r.input_ref == f"job:{jid}"]
        assert r.status == "awaiting_approval" and r.approval_request_id is not None
        with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
            ar = conn.execute(text("SELECT gate_type, subject_table, subject_id, status, required_approver_role "
                                   "FROM approval_request WHERE id = :a"), {"a": r.approval_request_id}).one()
        assert (ar.gate_type, ar.subject_table, ar.subject_id, ar.status) == ("g_agent_action", "agent_task_run", r.id, "pending")
        assert ar.required_approver_role == "tenant_hr"                      # job-posting-publisher's owner is hr

        # still waiting: the same job delivered again is held again, not run
        with engine.begin() as conn:
            conn.execute(text("UPDATE app.job SET status = 'queued', run_at = now() WHERE id = :j"), {"j": jid})
        assert w.tick().get("held") == 1 and calls == []

        # a person approves; the settler puts the job back; the handler runs once, under the same run
        from daydor.gates.hard import resolve
        with tenant_session(engine, "tenant_hr", org.tenant_a, user_id=org.user["hr_admin"]) as conn:
            assert resolve(conn, r.approval_request_id, "approved") == "approved"
        settler(engine).tick()
        assert w.tick()["succeeded"] == 1 and calls == [1]
        (r2,) = [x for x in run_rows(engine, org, "job-posting-publisher") if x.input_ref == f"job:{jid}"]
        assert r2.id == r.id and r2.status == "succeeded"
        assert w.tick().get("succeeded") is None and calls == [1]            # and never again
    finally:
        clear_policy(engine, org, "job-posting-publisher")


def test_a_rejected_hold_stops_the_run_and_the_handler_never_runs(engine, org):
    q, calls = queue_name(), []
    jid = enq(engine, org, q)
    w = Worker(engine, q, "w1")
    w.register("work", worker="job-posting-publisher", fn=lambda conn, job: calls.append(1) or {})
    set_policy(engine, org, "job-posting-publisher", "approve")
    try:
        w.tick()
        (r,) = [r for r in run_rows(engine, org, "job-posting-publisher") if r.input_ref == f"job:{jid}"]
        from daydor.gates.hard import resolve
        with tenant_session(engine, "tenant_hr", org.tenant_a, user_id=org.user["hr_admin"]) as conn:
            assert resolve(conn, r.approval_request_id, "rejected") == "rejected"
        settler(engine).tick()
        (r2,) = [x for x in run_rows(engine, org, "job-posting-publisher") if x.input_ref == f"job:{jid}"]
        assert r2.status == "rejected" and r2.finished_at is not None
        assert w.tick().get("succeeded") is None and calls == []
    finally:
        clear_policy(engine, org, "job-posting-publisher")


def test_review_autonomy_runs_the_job_and_leaves_the_run_for_a_person_to_acknowledge(engine, org):
    q, calls = queue_name(), []
    jid = enq(engine, org, q)
    w = Worker(engine, q, "w1")
    w.register("work", worker="onboarding-checklist-builder", fn=lambda conn, job: calls.append(1) or {})     # default: auto
    set_policy(engine, org, "onboarding-checklist-builder", "review")
    try:
        assert w.tick()["succeeded"] == 1 and calls == [1]
    finally:
        clear_policy(engine, org, "onboarding-checklist-builder")
    (r,) = [r for r in run_rows(engine, org, "onboarding-checklist-builder") if r.input_ref == f"job:{jid}"]
    assert r.status == "review_pending"
    with pytest.raises(ProgrammingError, match="permission denied for function acknowledge_agent_run"):
        with tenant_session(engine, "tenant_employee", org.tenant_a, employee_id=org.emp["report"]) as conn:
            conn.execute(text("SELECT app.acknowledge_agent_run(:r)"), {"r": r.id})
    with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
        conn.execute(text("SELECT app.acknowledge_agent_run(:r)"), {"r": r.id})
    with pytest.raises(DBAPIError, match="not waiting for review"):
        with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
            conn.execute(text("SELECT app.acknowledge_agent_run(:r)"), {"r": r.id})
    assert [x for x in run_rows(engine, org, "onboarding-checklist-builder") if x.id == r.id][0].status == "succeeded"


def test_a_worker_already_at_approve_gets_no_extra_hold(engine, org):
    """direct-deposit-disburser defaults to approve and has its own gates in its flows: the policy adds nothing."""
    q, calls = queue_name(), []
    enq(engine, org, q)
    w = Worker(engine, q, "w1")
    w.register("work", worker="direct-deposit-disburser", fn=lambda conn, job: calls.append(1) or {})
    set_policy(engine, org, "direct-deposit-disburser", "approve")
    try:
        assert w.tick()["succeeded"] == 1 and calls == [1]
    finally:
        clear_policy(engine, org, "direct-deposit-disburser")


def test_without_a_policy_nothing_is_held_or_flagged(engine, org):
    q = queue_name()
    jid = enq(engine, org, q)
    w = Worker(engine, q, "w1")
    w.register("work", worker="job-posting-publisher", fn=lambda conn, job: {})
    assert w.tick()["succeeded"] == 1
    (r,) = [r for r in run_rows(engine, org, "job-posting-publisher") if r.input_ref == f"job:{jid}"]
    assert r.status == "succeeded"


def test_the_settler_ignores_other_gates_and_only_the_workflow_engine_may_settle(engine, org):
    with pytest.raises(DBAPIError, match="only the workflow engine settles held runs"):
        with worker_session(engine, "job-posting-publisher", org.tenant_a) as conn:
            conn.execute(text("SELECT app.settle_agent_run(:a)"), {"a": uuid.uuid4()})
    with worker_session(engine, "workflow-engine", org.tenant_a) as conn:
        assert conn.execute(text("SELECT app.settle_agent_run(:a)"), {"a": uuid.uuid4()}).scalar_one() is None


def test_the_gate_and_subscription_are_registered(engine):
    with engine.connect() as conn:
        gate = conn.execute(text("SELECT kind, approver_roles, tables FROM app.gate_definition WHERE gate_id = 'g_agent_action'")).one()
        sub = conn.execute(text("SELECT queue, kind FROM app.subscription WHERE topic = 'gate.resolved' AND queue = 'agent-runs'")).one()
    assert gate.kind == "hard" and set(gate.approver_roles) >= {"tenant_hr", "tenant_founder", "daydor_ops"} and gate.tables == ["agent_task_run"]
    assert tuple(sub) == ("agent-runs", "agent.gate_resolved")


def test_pure_autonomy_rules():
    run = lambda **k: runs.AgentRun(uuid.uuid4(), k.get("status", "running"), True, k.get("released", False),
                                    k["eff"], k["default"])
    W = "job-posting-publisher"
    assert run(eff="approve", default="auto").must_hold_before(W) and run(eff="approve", default="review").must_hold_before(W)
    assert not run(eff="approve", default="approve").must_hold_before(W) and not run(eff="auto", default="auto").must_hold_before(W)
    assert not run(eff="approve", default="auto", released=True).must_hold_before(W)          # an approved hold runs
    assert run(eff="review", default="auto").needs_review_after(W) and not run(eff="review", default="review").needs_review_after(W)
    assert not run(eff="approve", default="auto").needs_review_after(W)
    # An LLM worker on the harness acts at review by default, and is not held up front: it proposes first.
    L = "requisition-drafter"
    assert run(eff="review", default="review").needs_review_after(L) and not run(eff="auto", default="review").needs_review_after(L)
    assert not run(eff="approve", default="review").must_hold_before(L) and runs.is_llm(L)
    assert not runs.is_llm("interview-scheduler")            # llm kind, but still a deterministic placeholder
    assert runs.is_tracked("gl-poster") and not runs.is_tracked("workflow-engine") and not runs.is_tracked("no-such")
    assert runs.owner_role("job-posting-publisher") == "tenant_hr" and runs.owner_role("gl-poster") == "tenant_founder"
