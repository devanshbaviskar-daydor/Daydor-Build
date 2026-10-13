"""Phase C: rollout (shadow, canary, ga), evals, tenant AI budgets and the circuit breaker. The model is scripted throughout."""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from daydor import circuit
from daydor.agents import evals, rollout
from daydor.agents.harness.client import ModelError, ScriptedClient, call, turn
from daydor.agents.session import worker_session
from daydor.db.session import tenant_session
from daydor.queue import Worker
from tests.factories import insert
from tests.rollout_helpers import place
from tests.test_agent_harness import (GOOD, RD, calls_of, drafter, enq, next_jobs, proposal_of, run_of)

W = "requisition-drafter"


@pytest.fixture
def req(engine, hire_org):
    """A requisition with no rollout row: the worker is in shadow, the default."""
    with engine.begin() as conn:
        requisition = insert(conn, "job_requisition", tenant_id=hire_org["tenant"], position_id=hire_org["position"],
                             hiring_manager_id=hire_org["hiring_manager"], status="draft", target_start_date="2026-09-01")
        ops = insert(conn, "app_user", role="ops")
        conn.execute(text("INSERT INTO app.ops_tenant_assignment (user_id, tenant_id) VALUES (:u, :t)"),
                     {"u": ops, "t": hire_org["tenant"]})
    return {**hire_org, "requisition": requisition, "ops": ops}


@pytest.fixture(autouse=True)
def closed_circuit(engine):
    def reset():
        with engine.begin() as conn:
            conn.execute(text("UPDATE app.integration_circuit SET state = 'closed', failures = 0, opened_at = NULL, "
                              "threshold = 5, cooldown_s = 60"))
    reset()
    yield
    reset()


def ops(engine, req):
    return tenant_session(engine, "daydor_ops", req["tenant"], user_id=req["ops"])


def ok_client():
    return ScriptedClient([turn(call("submit_proposal", GOOD))])


def run_one(engine, req, client=None, **kw):
    jid = enq(engine, req, **kw)
    outcome = drafter(engine, client or ok_client()).tick()
    return jid, outcome


def job_of(engine, jid):
    with engine.connect() as conn:
        return conn.execute(text("SELECT status, attempts, run_at > now() AS later, last_error FROM app.job WHERE id = :j"),
                            {"j": jid}).one()


def record_eval(engine, mode="replay", sha=None, passed=True, models=None):
    with engine.begin() as conn:
        return conn.execute(text("SELECT app.record_worker_eval(:w, :m, :p, 'g', CAST(:mo AS jsonb), 3, :n)"),
                            {"w": W, "m": mode, "p": sha or rollout.prompt_sha(W), "mo": json.dumps(models or {}),
                             "n": 3 if passed else 2}).scalar_one()


# ------------------------------------------------------------------ rollout: what a stage does
def test_a_new_llm_worker_starts_in_shadow_its_proposal_is_recorded_and_never_applied(engine, req):
    jid, outcome = run_one(engine, req)
    assert outcome["succeeded"] == 1
    run = run_of(engine, req, jid)
    assert run.status == "succeeded"                                   # nothing to acknowledge: nothing was applied
    prop = proposal_of(engine, run.id)
    assert (prop.status, prop.valid, prop.committed_at) == ("shadow", True, None) and prop.proposal["title"] == GOOD["title"]
    assert next_jobs(engine, req) == []                                # the next step never started
    assert len(calls_of(engine, run.id)) == 1                          # but the model call was recorded and counted
    with tenant_session(engine, "tenant_hr", req["tenant"]) as conn:
        stats = conn.execute(text("SELECT status, valid, proposals FROM app.agent_proposal_stats WHERE worker = :w"), {"w": W}).all()
    assert [(s.status, s.valid, s.proposals) for s in stats] == [("shadow", True, 1)]


def test_shadow_wins_over_a_tenant_that_asked_for_approval(engine, req):
    with tenant_session(engine, "tenant_hr", req["tenant"]) as conn:
        conn.execute(text("INSERT INTO app.worker_tenant_policy (worker, autonomy) VALUES (:w, 'approve')"), {"w": W})
    jid, outcome = run_one(engine, req)
    assert outcome["succeeded"] == 1 and run_of(engine, req, jid).status == "succeeded"
    assert proposal_of(engine, run_of(engine, req, jid).id).status == "shadow"


def test_canary_applies_the_proposal_but_a_person_acknowledges_every_run(engine, req):
    place(engine, req["tenant"], W, "canary")
    jid, _ = run_one(engine, req)
    run = run_of(engine, req, jid)
    assert run.status == "review_pending" and proposal_of(engine, run.id).status == "committed"
    (nxt,) = next_jobs(engine, req)
    assert nxt.status == "held" and nxt.hold_run == run.id


def test_a_promotion_earned_on_another_prompt_does_not_carry_over(engine, req):
    place(engine, req["tenant"], W, "ga")
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(text("UPDATE app.worker_rollout SET prompt_sha256 = 'an-older-prompt' WHERE tenant_id = :t"), {"t": req["tenant"]})
    jid, _ = run_one(engine, req)
    assert proposal_of(engine, run_of(engine, req, jid).id).status == "shadow"
    with tenant_session(engine, "worker_requisition_drafter", req["tenant"]) as conn:
        assert rollout.stage_for(conn, W) == "shadow"


def test_workers_without_an_llm_have_no_rollout(engine, req):
    with tenant_session(engine, "worker_job_posting_publisher", req["tenant"]) as conn:
        assert rollout.stage_for(conn, "job-posting-publisher") == "ga"
    with pytest.raises(DBAPIError, match="not an LLM worker"):
        with ops(engine, req) as conn:
            conn.execute(text("SELECT app.set_worker_rollout('job-posting-publisher', 'shadow')"))


# ------------------------------------------------------------------ rollout: promotion needs evidence
def canary_runs(engine, req, n, client=ok_client):
    for _ in range(n):
        run_one(engine, req, client())


def test_canary_needs_a_passing_eval_on_the_prompt_in_force(engine, req):
    with pytest.raises(DBAPIError, match="no passing eval on file"):
        with ops(engine, req) as conn:
            rollout.promote(conn, W, "canary")
    record_eval(engine, sha="a-different-prompt")
    record_eval(engine, passed=False)
    with pytest.raises(DBAPIError, match="no passing"):
        with ops(engine, req) as conn:
            rollout.promote(conn, W, "canary")
    record_eval(engine)                                                  # a passing replay eval on the prompt in force is enough
    with ops(engine, req) as conn:
        assert rollout.promote(conn, W, "canary") == "canary"
    with tenant_session(engine, "tenant_hr", req["tenant"]) as conn:
        assert rollout.stage_for(conn, W) == "canary"


def test_general_availability_needs_canary_a_live_eval_and_a_clean_canary_period(engine, req):
    record_eval(engine, mode="live", models=rollout.models_in_force(W))
    with pytest.raises(DBAPIError, match="must run as canary"):          # no jumping from shadow, evidence or not
        with ops(engine, req) as conn:
            conn.execute(text("SELECT app.set_worker_rollout(:w, 'ga', :s, '{}')"), {"w": W, "s": rollout.prompt_sha(W)})
    with ops(engine, req) as conn:
        rollout.promote(conn, W, "canary")
    with pytest.raises(DBAPIError, match="needs 5 committed canary runs"):
        with ops(engine, req) as conn:
            rollout.promote(conn, W, "ga")
    canary_runs(engine, req, 5)
    with ops(engine, req) as conn:
        assert rollout.promote(conn, W, "ga") == "ga"
    jid, _ = run_one(engine, req)                                        # at ga the worker acts at its own autonomy (review, by default)
    assert proposal_of(engine, run_of(engine, req, jid).id).status == "committed"


def test_a_rejected_canary_run_blocks_general_availability(engine, req):
    record_eval(engine, mode="live", models=rollout.models_in_force(W))
    with ops(engine, req) as conn:
        rollout.promote(conn, W, "canary")
    canary_runs(engine, req, 5)
    jid, _ = run_one(engine, req)
    with tenant_session(engine, "tenant_hr", req["tenant"]) as conn:
        conn.execute(text("SELECT app.reject_agent_run(:r)"), {"r": run_of(engine, req, jid).id})
    with pytest.raises(DBAPIError, match="none rejected"):
        with ops(engine, req) as conn:
            rollout.promote(conn, W, "ga")


def test_a_live_eval_on_another_model_does_not_count_for_general_availability(engine, req, monkeypatch):
    record_eval(engine, mode="live", models=rollout.models_in_force(W))
    with ops(engine, req) as conn:
        rollout.promote(conn, W, "canary")
    canary_runs(engine, req, 5)
    monkeypatch.setenv("DAYDOR_MODEL_MEDIUM", "a-newer-model")
    with pytest.raises(PermissionError, match="no passing live eval"):
        with ops(engine, req) as conn:
            rollout.promote(conn, W, "ga")


def test_a_tenant_can_step_back_never_forward_and_the_table_is_not_writable_directly(engine, req):
    place(engine, req["tenant"], W, "ga")
    with tenant_session(engine, "tenant_founder", req["tenant"]) as conn:
        assert conn.execute(text("SELECT app.demote_worker_rollout(:w)"), {"w": W}).scalar_one() == "shadow"
    for role in ("tenant_founder", "tenant_hr"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            with tenant_session(engine, role, req["tenant"]) as conn:
                conn.execute(text("SELECT app.set_worker_rollout(:w, 'ga')"), {"w": W})
    with pytest.raises(ProgrammingError, match="permission denied"):
        with ops(engine, req) as conn:
            conn.execute(text("UPDATE app.worker_rollout SET stage = 'ga'"))
    with pytest.raises(ProgrammingError, match="permission denied"):
        with worker_session(engine, W, req["tenant"]) as conn:
            conn.execute(text("SELECT app.set_worker_rollout(:w, 'shadow')"), {"w": W})


def test_rollout_is_per_tenant(engine, req, org):
    place(engine, req["tenant"], W, "ga")
    with tenant_session(engine, "worker_requisition_drafter", org.tenant_a) as conn:
        assert rollout.stage_for(conn, W) == "shadow"


# ------------------------------------------------------------------ evals
def test_every_llm_worker_has_a_golden_set_for_the_prompt_in_force():
    assert evals.llm_workers() == [W]
    for w in evals.llm_workers():
        assert evals.check_current(w) == []


def test_changing_a_prompt_makes_its_golden_set_stale(monkeypatch):
    real = evals.load_golden
    monkeypatch.setattr(evals, "load_golden", lambda w: ({**real(w)[0], "prompt_sha256": "0" * 64}, "x"))
    assert any("prompt changed" in p for p in evals.check_current(W))
    monkeypatch.setattr(evals, "load_golden", lambda w: ({**real(w)[0], "output_schema": "other/1"}, "x"))
    assert any("output schema" in p for p in evals.check_current(W))


def test_the_replay_eval_passes_and_fails_when_a_guardrail_or_an_expectation_breaks(monkeypatch):
    r = evals.replay(W)
    assert r.passed and r.total >= 8 and r.mode == "replay"
    real = evals.load_golden
    golden, sha = real(W)
    wrong = [{**c, "expect": {"outcome": "accepted"}} if c["id"] == "age-preference" else c for c in golden["cases"]]
    monkeypatch.setattr(evals, "load_golden", lambda w: ({**golden, "cases": wrong}, sha))
    broken = evals.replay(W)
    assert not broken.passed and [c["id"] for c in broken.cases if not c["passed"]] == ["age-preference"]
    # a guardrail that stops guarding
    import dataclasses
    monkeypatch.setattr(evals, "spec_for", lambda w: dataclasses.replace(RD.SPEC, rules=lambda p, c: []))
    monkeypatch.setattr(evals, "load_golden", lambda w: (golden, sha))
    assert not evals.replay(W).passed


def test_a_live_eval_runs_the_real_loop_judges_the_proposal_and_is_recorded(engine, req):
    live_cases = len([c for c in evals.load_golden(W)[0]["cases"] if c["kind"] == "live"])
    with worker_session(engine, W, req["tenant"]) as conn:
        good = evals.live(W, conn, ScriptedClient([turn(call("submit_proposal", GOOD, f"t{i}")) for i in range(live_cases)]))
    assert good.passed and good.mode == "live" and good.models == rollout.models_in_force(W)
    leaky = {**GOOD, "summary": "You will build and run backend services; the salary is 20 LPA."}      # fails the rules: sent back, then gives up
    with worker_session(engine, W, req["tenant"]) as conn:
        bad = evals.live(W, conn, ScriptedClient([turn(call("submit_proposal", leaky, f"t{i}")) for i in range(60)]))
    assert not bad.passed and any("ProposalInvalid" in c["why"] for c in bad.cases if not c["passed"])
    with tenant_session(engine, "daydor_admin") as conn:
        evals.record(conn, good)
        evals.record(conn, bad)
    with ops(engine, req) as conn:
        rows = conn.execute(text("SELECT mode, passed, total FROM app.worker_eval_result WHERE worker = :w ORDER BY run_at"), {"w": W}).all()
    assert (rows[-2].passed, rows[-1].passed) == (True, False)
    with pytest.raises(DBAPIError, match="append-only|cannot be"):
        with engine.begin() as conn:
            conn.execute(text("UPDATE app.worker_eval_result SET passed_count = total"))


def test_only_daydor_staff_record_evals(engine, req):
    for role in ("tenant_founder", "tenant_hr"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            with tenant_session(engine, role, req["tenant"]) as conn:
                conn.execute(text("SELECT app.record_worker_eval(:w, 'replay', 'p', 'g', '{}', 1, 1)"), {"w": W})
    with pytest.raises(ProgrammingError, match="permission denied"):
        with worker_session(engine, W, req["tenant"]) as conn:
            conn.execute(text("SELECT app.record_worker_eval(:w, 'live', 'p', 'g', '{}', 1, 1)"), {"w": W})


# ------------------------------------------------------------------ tenant AI budgets
def set_cap(engine, req, usd=None, tokens=None):
    with ops(engine, req) as conn:
        conn.execute(text("INSERT INTO app.tenant_ai_budget (monthly_cap_usd, monthly_cap_tokens) VALUES (:u, :t) "
                          "ON CONFLICT (tenant_id) DO UPDATE SET monthly_cap_usd = :u, monthly_cap_tokens = :t"), {"u": usd, "t": tokens})


def test_a_tenant_token_cap_stops_a_run_in_flight_and_then_every_later_run_before_it_calls_a_model(engine, req):
    place(engine, req["tenant"], W, "ga")
    set_cap(engine, req, tokens=1500)
    client = ScriptedClient([turn(call("list_similar_titles", {"job_family": "Engineering"}), inp=900, out=700)] * 3)
    jid, _ = run_one(engine, req, client)
    run = run_of(engine, req, jid)
    assert run.status == "failed" and run.error_code == "BudgetExceeded" and len(client.seen) == 1
    with ops(engine, req) as conn:
        head = conn.execute(text("SELECT * FROM app.tenant_ai_headroom()")).one()
    assert (head.cap_tokens, head.used_tokens) == (1500, 1600)
    untouched = ScriptedClient([turn(call("submit_proposal", GOOD))])
    jid2, _ = run_one(engine, req, untouched)
    assert run_of(engine, req, jid2).error_code == "TenantBudgetExceeded" and untouched.seen == []


def test_a_tenant_dollar_cap_counts_priced_calls(engine, req, monkeypatch):
    place(engine, req["tenant"], W, "ga")
    monkeypatch.setenv("DAYDOR_MODEL_PRICES", json.dumps({"scripted-model": [1000.0, 1000.0]}))
    set_cap(engine, req, usd=1)
    jid, _ = run_one(engine, req, ScriptedClient([turn(call("list_similar_titles", {"job_family": "Engineering"}), inp=1000, out=1000)] * 3))
    assert run_of(engine, req, jid).error_code == "BudgetExceeded"                 # $2 spent in one turn, against $1 left
    jid2, _ = run_one(engine, req, ScriptedClient([turn(call("submit_proposal", GOOD))]))
    assert run_of(engine, req, jid2).error_code == "TenantBudgetExceeded"


def test_no_cap_means_no_cap_and_spend_is_visible(engine, req):
    place(engine, req["tenant"], W, "ga")
    jid, _ = run_one(engine, req, ScriptedClient([turn(call("submit_proposal", GOOD), inp=700, out=300)]))
    assert run_of(engine, req, jid).status == "review_pending"
    with tenant_session(engine, "tenant_founder", req["tenant"]) as conn:
        usage = conn.execute(text("SELECT worker, calls, input_tokens, output_tokens, unpriced_calls FROM app.ai_usage_daily")).all()
    assert [(u.worker, u.calls, u.input_tokens, u.output_tokens, u.unpriced_calls) for u in usage] == [(W, 1, 700, 300, 1)]


def test_only_daydor_ops_set_a_cap_and_tenants_see_only_their_own(engine, req, org):
    set_cap(engine, req, tokens=10)
    for role in ("tenant_founder", "tenant_hr", "tenant_payroll"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            with tenant_session(engine, role, req["tenant"]) as conn:
                conn.execute(text("UPDATE app.tenant_ai_budget SET monthly_cap_tokens = 999999"))
    with tenant_session(engine, "tenant_founder", req["tenant"]) as conn:
        assert conn.execute(text("SELECT monthly_cap_tokens FROM app.tenant_ai_budget")).scalar_one() == 10
    with tenant_session(engine, "tenant_founder", org.tenant_a) as conn:
        assert conn.execute(text("SELECT count(*) FROM app.tenant_ai_budget")).scalar_one() == 0


# ------------------------------------------------------------------ circuit breaker
def circuit_state(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT state, failures FROM app.integration_circuit WHERE integration = 'model_provider'")).one()


def test_the_circuit_opens_after_the_threshold_refuses_calls_then_probes_and_closes(engine, req):
    with worker_session(engine, W, req["tenant"]) as conn:
        for _ in range(4):
            assert circuit.record(conn, "model_provider", False, "boom") == "closed"
        assert circuit.allow(conn, "model_provider").allowed
        assert circuit.record(conn, "model_provider", False, "boom") == "open"
        gate = circuit.allow(conn, "model_provider")
        assert not gate.allowed and 0 < gate.retry_after_s <= 60
    with engine.begin() as conn:                                         # the cooldown passes
        conn.execute(text("UPDATE app.integration_circuit SET opened_at = now() - interval '2 minutes'"))
    with worker_session(engine, W, req["tenant"]) as conn:
        assert circuit.allow(conn, "model_provider").allowed             # a probe
        assert circuit.record(conn, "model_provider", False, "still down") == "open"      # the probe failed: reopened
        assert not circuit.allow(conn, "model_provider").allowed
    with engine.begin() as conn:
        conn.execute(text("UPDATE app.integration_circuit SET opened_at = now() - interval '2 minutes'"))
    with worker_session(engine, W, req["tenant"]) as conn:
        assert circuit.record(conn, "model_provider", True) == "closed"
    assert tuple(circuit_state(engine)) == ("closed", 0)


def test_a_success_in_between_resets_the_count(engine, req):
    with worker_session(engine, W, req["tenant"]) as conn:
        for ok in (False, False, False, False, True, False, False, False, False):
            circuit.record(conn, "model_provider", ok)
    assert tuple(circuit_state(engine)) == ("closed", 4)


def test_only_registered_integrations_and_only_through_the_functions(engine, req):
    with pytest.raises(DBAPIError, match="unknown integration"):
        with worker_session(engine, W, req["tenant"]) as conn:
            circuit.record(conn, "made-up", False)
    with pytest.raises(ProgrammingError, match="permission denied"):
        with worker_session(engine, W, req["tenant"]) as conn:
            conn.execute(text("UPDATE app.integration_circuit SET state = 'closed'"))
    with pytest.raises(ProgrammingError, match="permission denied"):
        with tenant_session(engine, "tenant_founder", req["tenant"]) as conn:
            circuit.allow(conn, "model_provider")
    with pytest.raises(ProgrammingError, match="permission denied"):
        with worker_session(engine, W, req["tenant"]) as conn:
            conn.execute(text("SELECT app.circuit_reset('model_provider')"))


def test_model_errors_open_the_circuit_and_an_open_circuit_defers_jobs_without_spending_attempts(engine, req):
    place(engine, req["tenant"], W, "ga")
    with engine.begin() as conn:
        conn.execute(text("UPDATE app.integration_circuit SET threshold = 2"))

    class Down(ScriptedClient):
        def complete(self, **kw):
            raise ModelError("overloaded_error")
    for _ in range(2):
        run_one(engine, req, Down([]))
    assert circuit_state(engine).state == "open"

    client = ScriptedClient([turn(call("submit_proposal", GOOD))])
    jid, outcome = run_one(engine, req, client)
    assert outcome.get("deferred") == 1 and client.seen == []              # the model was not called
    job = job_of(engine, jid)
    assert (job.status, job.attempts, job.later) == ("queued", 0, True) and "circuit is open" in job.last_error
    assert run_of(engine, req, jid).status == "running"                   # the run waits with the job

    with tenant_session(engine, "daydor_admin") as conn:                  # ops closes it again; the job then runs on the same run
        conn.execute(text("SELECT app.circuit_reset('model_provider')"))
    with engine.begin() as conn:
        conn.execute(text("UPDATE app.job SET run_at = now() WHERE id = :j"), {"j": jid})
    assert drafter(engine, client).tick()["succeeded"] == 1
    assert run_of(engine, req, jid).status == "review_pending" and job_of(engine, jid).status == "succeeded"


def test_a_provider_that_answers_badly_is_not_a_provider_that_is_down(engine, req):
    place(engine, req["tenant"], W, "ga")
    with engine.begin() as conn:
        conn.execute(text("UPDATE app.integration_circuit SET threshold = 2"))
    for _ in range(3):
        run_one(engine, req, ScriptedClient([turn(call("submit_proposal", {"title": "x"}, f"t{i}")) for i in range(6)]))
    assert tuple(circuit_state(engine)) == ("closed", 0)
