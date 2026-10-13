"""State machines: transitions, hard/soft/conditional gates, resumption through the queue,
idempotency, optimistic concurrency, and an end-to-end payroll run."""
import json
import threading
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from daydor.agents.session import worker_session
from daydor.db.session import tenant_session
from daydor.gates.hard import resolve
from daydor.queue import Worker
from daydor.workflow import WorkflowEngine, WorkflowError
from daydor.workflow.definitions import seed_sql
from daydor.workflow.engine import ConcurrentTransition, gate_resolved_handler
from tests.factories import insert
from tests.calibration_helpers import approve_calibration
from tests.test_gates import FakeDecider, PAYROLL_GATE

SQL = Path(__file__).resolve().parents[1] / "migrations" / "sql"

DEMO = {
    "initial": "drafted",
    "states": {
        "drafted": {"on": {"submit": {"to": "approved", "gate": "g_pay_disburse", "on_reject": "drafted_again"},
                           "submit_conditional": {"to": "approved", "gate": "g_offer_band",
                                                  "gate_if": "requires_g_offer_band"},
                           "precheck": {"to": "approved", "soft_gate": "sg_payroll_anomaly_precheck"},
                           "submit_no_fallback": {"to": "approved", "gate": "g_pay_disburse"}}},
        "drafted_again": {"terminal": True},
        "approved": {"enter_jobs": [{"queue": "pay", "kind": "direct-deposit-disburser"}],
                     "on": {"finish": {"to": "done"}}},
        "done": {"terminal": True},
    },
}


@pytest.fixture(scope="module", autouse=True)
def demo_definition(engine):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO app.workflow_definition (name, version, definition) "
                          "VALUES ('demo', 1, CAST(:d AS jsonb)) ON CONFLICT DO NOTHING"),
                     {"d": json.dumps(DEMO)})


@pytest.fixture
def run(engine, org):
    with engine.begin() as conn:
        return insert(conn, "payroll_run", tenant_id=org.tenant_a, legal_entity_id=org.legal_entity_a,
                      gross_total=1_000_000, net_total=800_000, anomaly_score=0.01,
                      retention_class=insert(conn, "retention_policy"))


def agent(engine, org):
    return worker_session(engine, "payroll-anomaly-detector", org.tenant_a)


def founder(engine, org):
    return tenant_session(engine, "tenant_founder", org.tenant_a, user_id=org.user["founder_user"])


def instance(engine, org, wid):
    with agent(engine, org) as conn:
        return conn.execute(text("SELECT * FROM app.workflow_instance WHERE id = :i"), {"i": wid}).one()


def drain_workflow_queue(engine, wf=None):
    w = Worker(engine, "workflow", "wf-1")
    w.register("workflow.gate_resolved", worker="workflow-engine", fn=gate_resolved_handler(wf or WorkflowEngine()))
    return w.tick()


def test_generated_definitions_match_model_flows():
    assert (SQL / "0010_workflow_seed.sql").read_text() == seed_sql()


def test_start_is_idempotent_per_subject(engine, org, run):
    wf = WorkflowEngine()
    with agent(engine, org) as conn:
        a = wf.start(conn, "demo", "payroll_run", run)
        b = wf.start(conn, "demo", "payroll_run", run)
    assert a == b and instance(engine, org, a).state == "drafted"


def test_unknown_event_is_rejected(engine, org, run):
    wf = WorkflowEngine()
    with pytest.raises(WorkflowError, match="no transition"):
        with agent(engine, org) as conn:
            wid = wf.start(conn, "demo", "payroll_run", run)
            wf.fire(conn, wid, "teleport")


def test_hard_gate_parks_then_resumes_through_queue(engine, org, run):
    wf = WorkflowEngine()
    with agent(engine, org) as conn:
        wid = wf.start(conn, "demo", "payroll_run", run)
        r = wf.fire(conn, wid, "submit")
    assert r.outcome == "waiting_gate" and instance(engine, org, wid).status == "waiting_gate"
    with pytest.raises(WorkflowError, match="waiting_gate"):
        with agent(engine, org) as conn:
            wf.fire(conn, wid, "finish")

    with founder(engine, org) as conn:
        resolve(conn, r.approval_request_id, "approved")      # emits gate.resolved
    # Other tests' gate.resolved events may be queued too, so assert on this instance, not counts.
    assert drain_workflow_queue(engine)["succeeded"] >= 1

    inst = instance(engine, org, wid)
    assert (inst.state, inst.status) == ("approved", "running")
    with engine.connect() as conn:   # entering "approved" queued the disburser exactly once
        n = conn.execute(text("SELECT count(*) FROM app.job WHERE idempotency_key = :k"),
                         {"k": f"wf:{wid}:approved:direct-deposit-disburser"}).scalar_one()
    assert n == 1


def test_rejection_follows_on_reject(engine, org, run):
    wf = WorkflowEngine()
    with agent(engine, org) as conn:
        wid = wf.start(conn, "demo", "payroll_run", run)
        r = wf.fire(conn, wid, "submit")
    with founder(engine, org) as conn:
        resolve(conn, r.approval_request_id, "rejected", "Wrong bank file")
    drain_workflow_queue(engine)
    inst = instance(engine, org, wid)
    assert (inst.state, inst.status) == ("drafted_again", "completed")


def test_rejection_without_fallback_cancels(engine, org, run):
    wf = WorkflowEngine()
    with agent(engine, org) as conn:
        wid = wf.start(conn, "demo", "payroll_run", run)
        r = wf.fire(conn, wid, "submit_no_fallback")
    with founder(engine, org) as conn:
        resolve(conn, r.approval_request_id, "rejected")
    drain_workflow_queue(engine)
    assert instance(engine, org, wid).status == "cancelled"


def test_conditional_gate_only_when_flagged(engine, org, run):
    wf = WorkflowEngine()
    with agent(engine, org) as conn:
        wid = wf.start(conn, "demo", "payroll_run", run)
        r = wf.fire(conn, wid, "submit_conditional")
    assert r.outcome == "moved" and r.state == "approved"

    with engine.begin() as conn:
        other = insert(conn, "payroll_run", tenant_id=org.tenant_a, legal_entity_id=org.legal_entity_a,
                       retention_class=insert(conn, "retention_policy"))
    with agent(engine, org) as conn:
        wid2 = wf.start(conn, "demo", "payroll_run", other, {"requires_g_offer_band": True})
        r2 = wf.fire(conn, wid2, "submit_conditional")
    assert r2.outcome == "waiting_gate"


def test_duplicate_event_delivery_is_a_noop(engine, org, run):
    wf = WorkflowEngine()
    with agent(engine, org) as conn:
        wid = wf.start(conn, "demo", "payroll_run", run)
        wf.fire(conn, wid, "submit_conditional", event_id="evt-1")
        again = wf.fire(conn, wid, "submit_conditional", event_id="evt-1")
    assert again.outcome == "duplicate" and instance(engine, org, wid).state == "approved"


def test_concurrent_transitions_one_wins(engine, org, run):
    wf = WorkflowEngine()
    with agent(engine, org) as conn:
        wid = wf.start(conn, "demo", "payroll_run", run)
    errors = []

    def second():
        try:
            with agent(engine, org) as c2:
                wf.fire(c2, wid, "submit_conditional")
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    with agent(engine, org) as c1:
        wf.fire(c1, wid, "submit_conditional")
        t = threading.Thread(target=second)
        t.start()
        t.join(0.5)            # blocked on c1's row lock
    t.join(5)
    assert len(errors) == 1 and isinstance(errors[0], (ConcurrentTransition, WorkflowError))
    assert instance(engine, org, wid).version == 2


@pytest.fixture
def enforce_payroll_soft_gate(engine):
    with engine.begin() as conn:
        version = approve_calibration(conn, "sg_payroll_anomaly_precheck")
        conn.execute(text("UPDATE app.gate_definition SET mode = 'enforce', calibration_version = :v "
                          "WHERE gate_id = 'sg_payroll_anomaly_precheck'"), {"v": version})
    yield
    with engine.begin() as conn:
        conn.execute(text("UPDATE app.gate_definition SET mode = 'shadow', "
                          "calibration_version = NULL WHERE gate_id = 'sg_payroll_anomaly_precheck'"))


def test_soft_gate_pass_moves_without_human(engine, org, run, enforce_payroll_soft_gate):
    wf = WorkflowEngine({"sg_payroll_anomaly_precheck": PAYROLL_GATE}, FakeDecider("normal", 0.98))
    with agent(engine, org) as conn:
        wid = wf.start(conn, "demo", "payroll_run", run)
        r = wf.fire(conn, wid, "precheck")
    assert r.outcome == "moved" and r.approval_request_id is None


def test_soft_gate_shadow_mode_waits_for_human(engine, org, run):
    wf = WorkflowEngine({"sg_payroll_anomaly_precheck": PAYROLL_GATE}, FakeDecider("normal", 0.99))
    with agent(engine, org) as conn:
        wid = wf.start(conn, "demo", "payroll_run", run)
        r = wf.fire(conn, wid, "precheck")
    assert r.outcome == "waiting_gate"
    with tenant_session(engine, "tenant_payroll", org.tenant_a, user_id=org.user["payroll_lead"]) as conn:
        resolve(conn, r.approval_request_id, "approved")     # g_pay_anomaly: payroll or ops
    drain_workflow_queue(engine)
    assert instance(engine, org, wid).state == "approved"


def test_instances_are_tenant_isolated(engine, org, run):
    wf = WorkflowEngine()
    with agent(engine, org) as conn:
        wid = wf.start(conn, "demo", "payroll_run", run)
    with worker_session(engine, "payroll-anomaly-detector", org.tenant_b) as conn:
        assert conn.execute(text("SELECT count(*) FROM app.workflow_instance WHERE id = :i"),
                            {"i": wid}).scalar_one() == 0


def test_end_to_end_generated_payroll_flow(engine, org, run):
    """Drive the generated payroll skeleton: the anomaly gate is skipped (not flagged), disbursal
    parks for the founder, and the same approval then unlocks the guarded disbursal write."""
    wf = WorkflowEngine()
    with agent(engine, org) as conn:
        wid = wf.start(conn, "payroll", "payroll_run", run)
    for _ in range(10):         # start -> s09 moves (anomaly gate not flagged); 10th parks at disbursal
        with agent(engine, org) as conn:
            r = wf.fire(conn, wid, "advance")
    assert r.outcome == "waiting_gate" and r.state == "s09_payroll_run"

    # The disburser cannot jump ahead of the gate.
    with pytest.raises(Exception, match="needs an approved g_pay_disburse"):
        with worker_session(engine, "direct-deposit-disburser", org.tenant_a) as conn:
            conn.execute(text("UPDATE payroll_run SET approval_request_id = :a, disbursed_at = now() "
                              "WHERE id = :r"), {"a": r.approval_request_id, "r": run})

    with founder(engine, org) as conn:
        resolve(conn, r.approval_request_id, "approved")
    drain_workflow_queue(engine)
    assert instance(engine, org, wid).state == "s10_approval_request"

    with worker_session(engine, "direct-deposit-disburser", org.tenant_a) as conn:
        conn.execute(text("UPDATE payroll_run SET approval_request_id = :a, disbursed_at = now() "
                          "WHERE id = :r"), {"a": r.approval_request_id, "r": run})
    with engine.connect() as conn:
        assert conn.execute(text("SELECT disbursed_at IS NOT NULL FROM payroll_run WHERE id = :r"),
                            {"r": run}).scalar_one()
