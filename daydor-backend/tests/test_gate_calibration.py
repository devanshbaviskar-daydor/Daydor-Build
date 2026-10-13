"""Sprint 13 (ADR-005, ADR-006): shadow report, labelled-example store, training policy, calibrations and the
database's refusal to enforce without an approved one."""
from __future__ import annotations

import json
import math
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from daydor.db.session import tenant_session
from daydor.gates import calibration as C
from daydor.gates import report as R
from daydor.gates.hard import resolve
from daydor.gates.soft import run_soft_gate
from tests.factories import insert
from tests.test_gates import PAYROLL_GATE, FakeDecider, as_payroll, evaluation  # noqa: F401
from tests.test_gates import run_id  # noqa: F401  (fixture)

GATE = "sg_payroll_anomaly_precheck"


# ------------------------------------------------------------------ pure: the report's arithmetic
def outcome(decision="pass", conf=0.97, human="pass", threshold=0.9, latency=40):
    return R.Outcome(decision, conf, threshold, human, latency)


def test_report_counts_agreement_and_auto_pass_disagreement():
    rows = ([outcome("pass", 0.97, "pass")] * 90 + [outcome("pass", 0.95, "escalate")] * 10      # 10% disagree
            + [outcome("escalate", 0.6, "escalate")] * 20 + [outcome("escalate", 0.6, "pass")] * 5
            + [outcome("pass", 0.5, "pass")] * 3                                                 # below threshold: not auto
            + [outcome("error", None, None)] * 2)
    rep = R.build_report(GATE, rows)
    assert (rep.total, rep.labelled, rep.errors) == (130, 128, 2)
    assert rep.auto_pass == 100 and rep.auto_pass_disagreements == 10 and rep.auto_pass_disagreement_rate == 0.1
    assert rep.by_pair[("pass", "pass")] == 93 and rep.by_pair[("escalate", "pass")] == 5
    assert rep.agreement == pytest.approx((93 + 20) / 128)
    assert rep.label_counts == {"pass": 98, "escalate": 30} and rep.rarer_label == 30


def test_ece_is_the_gap_between_confidence_and_how_often_a_person_agreed():
    # 100 auto-passes at confidence 0.95 that a person agreed with 70% of the time: ECE is the 0.25 gap.
    rows = [outcome("pass", 0.95, "pass")] * 70 + [outcome("pass", 0.95, "escalate")] * 30
    rep = R.build_report(GATE, rows)
    assert rep.ece == pytest.approx(0.25)
    perfect = R.build_report(GATE, [outcome("pass", 0.95, "pass")] * 95 + [outcome("pass", 0.95, "escalate")] * 5)
    assert perfect.ece == pytest.approx(0.0)


def test_promotion_checks_name_what_is_missing():
    rep = R.build_report(GATE, [outcome("pass", 0.97, "pass")] * 40)
    names = {c.name: c.ok for c in rep.promotion_checks()}
    assert names == {"labels": False, "rarer label": False, "calibration error": True, "auto-pass disagreement": True}
    assert not rep.ready
    ready = R.build_report(GATE, [outcome("pass", 0.97, "pass")] * 940 + [outcome("pass", 0.97, "escalate")] * 0
                           + [outcome("escalate", 0.6, "escalate")] * 60)
    assert ready.labelled == 1000 and ready.rarer_label == 60 and ready.auto_pass_disagreement_rate == 0.0
    assert ready.ece is not None and ready.ece <= R.MAX_ECE and ready.ready


def test_an_empty_report_has_no_numbers_rather_than_zeros():
    rep = R.build_report(GATE, [])
    assert rep.agreement is None and rep.ece is None and rep.auto_pass_disagreement_rate is None and not rep.ready
    assert "n/a" in R.render(rep)


# ------------------------------------------------------------------ pure: calibration
def samples(n, over, seed=7):
    """Probabilities of 0.95 on the model's top option which a person agrees with `over` of the time."""
    import random
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        top = "normal" if rnd.random() < 0.8 else "unusual"
        right = rnd.random() < over
        correct = top if right else ("unusual" if top == "normal" else "normal")
        other = "unusual" if top == "normal" else "normal"
        out.append(C.Sample({top: 0.95, other: 0.05}, correct))
    return out


def test_temperature_scaling_softens_an_over_confident_model_and_improves_the_fit():
    data = samples(600, over=0.75)
    t = C.fit_temperature(data)
    assert t > 1.5
    assert C.negative_log_likelihood(data, t) < C.negative_log_likelihood(data, 1.0)
    scaled = C.scale({"a": 0.95, "b": 0.05}, t)
    assert 0.7 < scaled["a"] < 0.85 and sum(scaled.values()) == pytest.approx(1.0)


def test_a_well_calibrated_model_needs_no_softening():
    data = samples(600, over=0.95)
    assert 0.8 <= C.fit_temperature(data) <= 1.2


def test_fitting_needs_both_classes():
    with pytest.raises(ValueError, match="same"):
        C.fit_temperature([C.Sample({"a": 0.9, "b": 0.1}, "a")] * 10)
    with pytest.raises(ValueError):
        C.fit_temperature([])


def test_scale_is_identity_at_one_and_keeps_the_order():
    p = {"a": 0.7, "b": 0.2, "c": 0.1}
    assert C.scale(p, 1.0) == pytest.approx(p)
    s = C.scale(p, 3.0)
    assert s["a"] > s["b"] > s["c"] and s["a"] < p["a"]


def test_the_rule_baseline_must_be_beaten():
    assert C.compare_to_baseline([True, True, False], [True, False, False])
    assert not C.compare_to_baseline([True, False, False], [True, False, False])        # a tie does not earn the model
    with pytest.raises(ValueError):
        C.compare_to_baseline([True], [True, False])


def test_zscore_baseline_flags_the_outlier():
    history = [100.0, 102.0, 98.0, 101.0, 99.0, 100.5]
    assert C.zscore_flags([100.2, 160.0], history) == [False, True]


# ------------------------------------------------------------------ database: shadow outcome
def new_run(engine, org):
    with engine.begin() as conn:
        return insert(conn, "payroll_run", tenant_id=org.tenant_a, legal_entity_id=org.legal_entity_a, status="built",
                      gross_total=1_000_000, net_total=800_000, anomaly_score=0.02,
                      retention_class=insert(conn, "retention_policy"))


def shadow_eval(engine, org, run, value="normal", p=0.97):
    with tenant_session(engine, "payroll-anomaly-detector" and "worker_payroll_anomaly_detector", org.tenant_a) as conn:
        return run_soft_gate(conn, PAYROLL_GATE, "payroll_run", run, FakeDecider(value, p))


def decide(engine, org, outcome_, status):
    with as_payroll(engine, org) as conn:
        assert resolve(conn, outcome_.approval_request_id, status) == status


def outcome_row(engine, org, evaluation_id):
    with tenant_session(engine, "daydor_ops", org.tenant_a) as conn:
        return conn.execute(text("SELECT * FROM app.gate_shadow_outcome WHERE evaluation_id = :e"),
                            {"e": evaluation_id}).one()


def test_shadow_outcome_pairs_the_model_with_the_human_decision(engine, org):
    approved, rejected, pending = (shadow_eval(engine, org, new_run(engine, org)) for _ in range(3))
    decide(engine, org, approved, "approved")
    decide(engine, org, rejected, "rejected")
    rows = {k: outcome_row(engine, org, o.evaluation_id) for k, o in (("a", approved), ("r", rejected), ("p", pending))}
    assert (rows["a"].human_status, rows["a"].human_label) == ("approved", "pass")
    assert (rows["r"].human_status, rows["r"].human_label) == ("rejected", "escalate")
    assert (rows["p"].human_status, rows["p"].human_label) == ("pending", None)
    assert rows["a"].model_decision == "pass" and rows["a"].effective_decision == "escalate"     # shadow escalates


def test_shadow_outcome_respects_tenant_isolation(engine, org):
    out = shadow_eval(engine, org, new_run(engine, org))
    with tenant_session(engine, "daydor_ops", org.tenant_b) as conn:
        assert conn.execute(text("SELECT count(*) FROM app.gate_shadow_outcome WHERE evaluation_id = :e"),
                            {"e": out.evaluation_id}).scalar_one() == 0


def test_shadow_report_reads_the_database_end_to_end(engine, org):
    run_ok, run_bad = new_run(engine, org), new_run(engine, org)
    ok, bad = shadow_eval(engine, org, run_ok, "normal", 0.97), shadow_eval(engine, org, run_bad, "normal", 0.96)
    decide(engine, org, ok, "approved")
    decide(engine, org, bad, "rejected")          # the gate would have waved this through
    with tenant_session(engine, "daydor_ops", org.tenant_a) as conn:
        rep = R.shadow_report(conn, GATE, since=datetime.now(timezone.utc) - timedelta(minutes=5))
    assert rep.labelled >= 2 and rep.auto_pass_disagreements >= 1
    assert rep.auto_pass_disagreement_rate > 0 and "Shadow report" in R.render(rep)


# ------------------------------------------------------------------ database: the example store
@pytest.fixture
def store_examples(engine):
    with engine.begin() as conn:
        conn.execute(text("UPDATE app.gate_definition SET store_examples = true, example_retention_days = 30 "
                          "WHERE gate_id = :g"), {"g": GATE})
    yield
    with engine.begin() as conn:
        conn.execute(text("UPDATE app.gate_definition SET store_examples = false, example_retention_days = NULL "
                          "WHERE gate_id = :g"), {"g": GATE})


def examples(engine, org, evaluation_id=None):
    with tenant_session(engine, "daydor_ops", org.tenant_a) as conn:
        return conn.execute(text("SELECT * FROM app.gate_example" + (" WHERE evaluation_id = :e" if evaluation_id else "")),
                            {"e": evaluation_id}).all()


def test_no_input_is_stored_unless_a_gate_opts_in(engine, org):
    with engine.connect() as conn:
        assert conn.execute(text("SELECT bool_or(store_examples) FROM app.gate_definition")).scalar_one() is False
    out = shadow_eval(engine, org, new_run(engine, org))
    assert examples(engine, org, out.evaluation_id) == []


def test_an_opted_in_gate_stores_exactly_its_declared_inputs(engine, org, store_examples):
    out = shadow_eval(engine, org, new_run(engine, org))
    (ex,) = examples(engine, org, out.evaluation_id)
    assert set(ex.input) == {"gross_total", "net_total", "anomaly_score"} and ex.label is None
    assert ex.expires_at > datetime.now(timezone.utc) + timedelta(days=29)


def test_the_store_refuses_fields_beyond_the_declared_inputs(engine, org, store_examples):
    out = shadow_eval(engine, org, new_run(engine, org))
    with pytest.raises(DBAPIError, match="beyond the gate's declared inputs"):
        with tenant_session(engine, "worker_payroll_anomaly_detector", org.tenant_a) as conn:
            conn.execute(text("SELECT app.record_gate_example(:e, CAST(:i AS jsonb))"),
                         {"e": out.evaluation_id, "i": json.dumps({"gross_total": 1, "employee_name": "x"})})


def test_only_ops_and_admin_can_read_examples_and_nobody_can_write_them_directly(engine, org, store_examples):
    out = shadow_eval(engine, org, new_run(engine, org))
    for role in ("tenant_hr", "tenant_founder", "tenant_payroll", "worker_payroll_anomaly_detector"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            with tenant_session(engine, role, org.tenant_a) as conn:
                conn.execute(text("SELECT * FROM app.gate_example"))
    for role in ("daydor_ops", "daydor_admin"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            with tenant_session(engine, role, org.tenant_a) as conn:
                conn.execute(text("INSERT INTO app.gate_example (gate_id, evaluation_id, subject_table, subject_id, input, "
                                  "expires_at) VALUES (:g, :e, 'payroll_run', :s, '{}', now())"),
                             {"g": GATE, "e": out.evaluation_id, "s": uuid.uuid4()})
    assert examples(engine, org, out.evaluation_id)


def test_examples_are_labelled_from_the_human_decision_and_only_once(engine, org, store_examples):
    approved, rejected, pending = (shadow_eval(engine, org, new_run(engine, org)) for _ in range(3))
    decide(engine, org, approved, "approved")
    decide(engine, org, rejected, "rejected")
    with tenant_session(engine, "daydor_ops", org.tenant_a) as conn:
        assert conn.execute(text("SELECT app.label_gate_examples(:g)"), {"g": GATE}).scalar_one() >= 2
        assert conn.execute(text("SELECT app.label_gate_examples(:g)"), {"g": GATE}).scalar_one() == 0
    labels = {o.evaluation_id: (examples(engine, org, o.evaluation_id)[0].label) for o in (approved, rejected, pending)}
    assert labels == {approved.evaluation_id: "pass", rejected.evaluation_id: "escalate", pending.evaluation_id: None}
    with tenant_session(engine, "daydor_ops", org.tenant_a) as conn:
        rows = C.export_examples(conn, GATE)
    assert {r["label"] for r in rows} <= {"pass", "escalate"} and all(r["label"] for r in rows)


def test_expired_examples_are_purged(engine, org, store_examples):
    out = shadow_eval(engine, org, new_run(engine, org))
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL ROLE daydor_schema_owner"))
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(org.tenant_a)})
        conn.execute(text("UPDATE app.gate_example SET expires_at = now() - interval '1 day' WHERE evaluation_id = :e"),
                     {"e": out.evaluation_id})
    with tenant_session(engine, "daydor_ops", org.tenant_a) as conn:
        assert conn.execute(text("SELECT app.purge_expired_gate_examples()")).scalar_one() >= 1
    assert examples(engine, org, out.evaluation_id) == []


def test_examples_need_a_retention_period(engine):
    with pytest.raises(DBAPIError, match="gate_definition_examples_need_retention"):
        with engine.begin() as conn:
            conn.execute(text("UPDATE app.gate_definition SET store_examples = true WHERE gate_id = :g"), {"g": GATE})


# ------------------------------------------------------------------ database: pooling stays opt-in
def test_pooled_export_includes_only_tenants_that_opted_in(engine, org, store_examples):
    mine = shadow_eval(engine, org, new_run(engine, org))
    decide(engine, org, mine, "approved")
    with tenant_session(engine, "daydor_ops", org.tenant_a) as conn:
        conn.execute(text("SELECT app.label_gate_examples(:g)"), {"g": GATE})
    pooled = C.export_pooled(engine, GATE, [org.tenant_a, org.tenant_b])
    assert pooled.included == [] and set(pooled.excluded) == {org.tenant_a, org.tenant_b} and pooled.examples == []

    with pytest.raises(DBAPIError, match="tenant_training_policy_check"):             # an opt-in must name its basis
        with tenant_session(engine, "daydor_ops", org.tenant_a) as conn:
            conn.execute(text("INSERT INTO app.tenant_training_policy (tenant_id, allow_pooling) VALUES (:t, true)"),
                         {"t": org.tenant_a})
    with tenant_session(engine, "daydor_ops", org.tenant_a) as conn:
        conn.execute(text("INSERT INTO app.tenant_training_policy (tenant_id, allow_pooling, basis) "
                          "VALUES (:t, true, 'order form 12, clause 4') ON CONFLICT (tenant_id) DO UPDATE "
                          "SET allow_pooling = true, basis = 'order form 12, clause 4'"), {"t": org.tenant_a})
    try:
        pooled = C.export_pooled(engine, GATE, [org.tenant_a, org.tenant_b])
        assert pooled.included == [org.tenant_a] and pooled.excluded == [org.tenant_b]
        assert pooled.examples and all(e["tenant_id"] == org.tenant_a for e in pooled.examples)
    finally:
        with tenant_session(engine, "daydor_ops", org.tenant_a) as conn:
            conn.execute(text("UPDATE app.tenant_training_policy SET allow_pooling = false WHERE tenant_id = :t"),
                         {"t": org.tenant_a})


# ------------------------------------------------------------------ database: calibrations
def candidate(conn, version, gate=GATE, **over):
    vals = dict(v=version, g=gate, n=400, r=80, ece=0.05, rb=True, dis=0.005, thr=0.5, since=date(2026, 1, 1))
    vals.update(over)
    conn.execute(text("INSERT INTO app.gate_calibration (version, gate_id, checkpoint, n_labels, n_rarer_label, ece, "
                      "rule_baseline_beaten, disagreement_rate, auto_pass_threshold, shadow_clean_since) "
                      "VALUES (:v, :g, 'english', :n, :r, :ece, :rb, :dis, :thr, :since)"), vals)


def approve(conn, version, by="Owner One"):
    conn.execute(text("UPDATE app.gate_calibration SET status = 'approved', signed_off_by = :b, "
                      "signed_off_at = now() WHERE version = :v"), {"b": by, "v": version})


@pytest.mark.parametrize("over, why", [
    ({"n": 299}, "too few labels"), ({"r": 49}, "too few of the rarer label"), ({"ece": 0.11}, "calibration error too high"),
    ({"rb": False}, "rule baseline not beaten"), ({"dis": 0.01}, "disagreement at the limit"),
    ({"since": None}, "no shadow window"), ({"since": date.today()}, "under two clean weeks"),
])
def test_a_calibration_cannot_be_approved_unless_every_criterion_holds(engine, over, why):
    v = f"cal-{uuid.uuid4().hex[:8]}"
    with tenant_session(engine, "daydor_ops") as conn:
        candidate(conn, v, **over)
    with pytest.raises(DBAPIError, match="gate_calibration_approved_meets_criteria"):
        with tenant_session(engine, "daydor_ops") as conn:
            approve(conn, v)


def test_a_calibration_needs_a_named_sign_off(engine):
    v = f"cal-{uuid.uuid4().hex[:8]}"
    with tenant_session(engine, "daydor_ops") as conn:
        candidate(conn, v)
    with pytest.raises(DBAPIError, match="gate_calibration_approved_meets_criteria"):
        with tenant_session(engine, "daydor_ops") as conn:
            conn.execute(text("UPDATE app.gate_calibration SET status = 'approved' WHERE version = :v"), {"v": v})
    with tenant_session(engine, "daydor_ops") as conn:
        approve(conn, v)
        assert conn.execute(text("SELECT status FROM app.gate_calibration WHERE version = :v"), {"v": v}).scalar_one() == "approved"


def test_calibration_evidence_is_immutable_and_never_deleted(engine):
    v = f"cal-{uuid.uuid4().hex[:8]}"
    with tenant_session(engine, "daydor_ops") as conn:
        candidate(conn, v)
    with pytest.raises(ProgrammingError, match="permission denied"):          # no grant on the evidence columns
        with tenant_session(engine, "daydor_ops") as conn:
            conn.execute(text("UPDATE app.gate_calibration SET ece = 0.01 WHERE version = :v"), {"v": v})
    with pytest.raises(DBAPIError, match="evidence is immutable"):             # nor can the owner quietly rewrite it
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL ROLE daydor_schema_owner"))
            conn.execute(text("UPDATE app.gate_calibration SET ece = 0.01 WHERE version = :v"), {"v": v})
    with pytest.raises(DBAPIError, match="never deleted"):
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL ROLE daydor_schema_owner"))
            conn.execute(text("DELETE FROM app.gate_calibration WHERE version = :v"), {"v": v})
    with pytest.raises(DBAPIError, match="starts as a candidate"):
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL ROLE daydor_schema_owner"))
            conn.execute(text("INSERT INTO app.gate_calibration (version, gate_id, checkpoint, status, n_labels, "
                              "n_rarer_label, ece, rule_baseline_beaten, disagreement_rate) "
                              "VALUES (:v, :g, 'english', 'approved', 1, 1, 0, true, 0)"), {"v": v + "x", "g": GATE})


def test_only_ops_and_admin_record_calibrations(engine):
    for role in ("tenant_founder", "tenant_hr", "worker_payroll_anomaly_detector"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            with tenant_session(engine, role) as conn:
                candidate(conn, f"cal-{uuid.uuid4().hex[:8]}")


def test_a_gate_cannot_enforce_without_an_approved_calibration_of_its_own(engine):
    other = "sg_access_request_precheck"
    mine, theirs, unapproved = (f"cal-{uuid.uuid4().hex[:8]}" for _ in range(3))
    with tenant_session(engine, "daydor_ops") as conn:
        candidate(conn, mine)
        approve(conn, mine)
        candidate(conn, theirs, gate=other)
        approve(conn, theirs)
        candidate(conn, unapproved)
    enforce = "UPDATE app.gate_definition SET mode = 'enforce', calibration_version = :v WHERE gate_id = :g"
    for version, why in ((None, "none"), (unapproved, "only a candidate"), (theirs, "another gate's"), ("no-such-version", "unknown")):
        with pytest.raises(DBAPIError, match="cannot enforce"):
            with engine.begin() as conn:
                conn.execute(text(enforce), {"v": version, "g": GATE})
    try:
        with engine.begin() as conn:
            conn.execute(text(enforce), {"v": mine, "g": GATE})
            assert conn.execute(text("SELECT mode FROM app.gate_definition WHERE gate_id = :g"), {"g": GATE}).scalar_one() == "enforce"
        # ... and it cannot be retired from under the gate
        with pytest.raises(DBAPIError, match="in use by a gate in enforce mode"):
            with tenant_session(engine, "daydor_ops") as conn:
                conn.execute(text("UPDATE app.gate_calibration SET status = 'retired' WHERE version = :v"), {"v": mine})
    finally:
        with engine.begin() as conn:
            conn.execute(text("UPDATE app.gate_definition SET mode = 'shadow', calibration_version = NULL WHERE gate_id = :g"),
                         {"g": GATE})


def synthetic_rows(n, informative, seed=3):
    """Shadow rows. `informative`: the higher the model's confidence, the more a person agrees (and very high
    confidence is nearly always right). Otherwise it is confident (0.95) and right only 80% of the time."""
    import random
    rnd = random.Random(seed)
    rows = []
    for i in range(n):
        top = "normal" if rnd.random() < 0.8 else "unusual"
        other = "unusual" if top == "normal" else "normal"
        p = rnd.uniform(0.55, 0.995) if informative else 0.95
        right = rnd.random() < (min(1.0, p + 0.03) if informative else 0.8)
        label = ("pass" if top == "normal" else "escalate") if right else ("escalate" if top == "normal" else "pass")
        rows.append({"model_decision": "pass" if top == "normal" else "escalate", "confidence": p, "threshold": 0.9,
                     "human_label": label, "created_at": i,
                     "output": {"run_looks": {"value": top, "probabilities": {top: p, other: 1 - p}}}})
    return rows


def propose(engine, rows, version, **over):
    kw = dict(gate_id=GATE, version=version, question="run_looks", pass_option="normal", review_option="unusual",
              rows=rows, checkpoint="english", engine_version="x@1", rule_baseline_beaten=False,
              shadow_clean_since=date(2026, 1, 1))
    kw.update(over)
    with tenant_session(engine, "daydor_ops") as conn:
        return C.propose_calibration(conn, **kw)


def test_a_model_whose_confidence_means_nothing_earns_no_threshold(engine):
    v = f"cal-{uuid.uuid4().hex[:8]}"
    cand = propose(engine, synthetic_rows(400, informative=False), v)
    assert cand.temperature > 1.5 and cand.n_fit == 280 and cand.n_holdout == 120 and cand.n_labels == 400
    assert cand.threshold is None                              # nothing it would auto-pass is right often enough
    with engine.connect() as conn:
        row = conn.execute(text("SELECT status, ece, disagreement_rate, auto_pass_threshold, note FROM app.gate_calibration "
                                "WHERE version = :v"), {"v": v}).one()
    assert row.status == "candidate" and row.ece == 1 and row.disagreement_rate == 1 and row.auto_pass_threshold == 1
    assert "no threshold" in row.note
    with pytest.raises(DBAPIError, match="gate_calibration_approved_meets_criteria"):      # and it cannot be approved
        with tenant_session(engine, "daydor_ops") as conn:
            approve(conn, v)


def test_an_informative_model_earns_a_threshold_and_a_candidate_with_small_error(engine):
    v = f"cal-{uuid.uuid4().hex[:8]}"
    cand = propose(engine, synthetic_rows(1500, informative=True), v, rule_baseline_beaten=True)
    assert cand.threshold is not None and 0.5 <= cand.threshold < 1.0
    assert cand.ece_after is not None and cand.ece_after < 0.10
    with engine.connect() as conn:
        row = conn.execute(text("SELECT status, n_labels, temperatures, auto_pass_threshold FROM app.gate_calibration "
                                "WHERE version = :v"), {"v": v}).one()
    assert row.status == "candidate" and row.n_labels == 1500
    assert float(row.auto_pass_threshold) == cand.threshold and row.temperatures["run_looks"] == cand.temperature


def test_proposing_needs_enough_rows_to_split(engine):
    with pytest.raises(ValueError, match="too few"):
        propose(engine, synthetic_rows(400, True)[:2], f"cal-{uuid.uuid4().hex[:8]}")


def test_choose_threshold_is_none_without_support_or_with_too_much_disagreement():
    few = [outcome("pass", 0.99, "pass")] * 5
    assert C.choose_threshold(few) is None
    noisy = [outcome("pass", 0.99, "pass")] * 90 + [outcome("pass", 0.99, "escalate")] * 10
    assert C.choose_threshold(noisy) is None
    clean = [outcome("pass", 0.8, "escalate")] * 30 + [outcome("pass", 0.97, "pass")] * 200
    assert C.choose_threshold(clean) == pytest.approx(0.81)          # the lowest step above the bad cluster


# ------------------------------------------------------------------ the runner applies the calibration
def test_applying_temperatures_changes_what_the_gate_thresholds_on():
    from daydor.gates.decider import Answer, DeciderResult
    raw = DeciderResult({"run_looks": Answer("normal", {"normal": 0.95, "unusual": 0.05}, 0.95)}, "laya", "x")
    out = C.apply_temperatures(raw, {"run_looks": 3.0})
    assert out.answers["run_looks"].value == "normal" and out.answers["run_looks"].confidence < 0.8
    assert out.answers["run_looks"].probabilities["normal"] == pytest.approx(out.answers["run_looks"].confidence)
    assert C.apply_temperatures(raw, {}).answers == raw.answers
    assert C.apply_temperatures(raw, {"other_question": 3.0}).answers == raw.answers


def test_an_enforcing_gate_decides_on_the_calibrated_confidence(engine, org):
    """Raw confidence 0.97 would pass at threshold 0.9; after the fitted temperature it is below it, so it escalates."""
    # temperatures live on the evidence, so record the candidate with them in the first place
    v2 = f"cal-{uuid.uuid4().hex[:8]}"
    with tenant_session(engine, "daydor_ops") as conn:
        conn.execute(text("INSERT INTO app.gate_calibration (version, gate_id, checkpoint, n_labels, n_rarer_label, ece, "
                          "rule_baseline_beaten, disagreement_rate, auto_pass_threshold, shadow_clean_since, temperatures) "
                          "VALUES (:v, :g, 'english', 400, 80, 0.05, true, 0.005, 0.5, DATE '2026-01-01', "
                          "CAST('{\"run_looks\": 3.0}' AS jsonb))"), {"v": v2, "g": GATE})
        approve(conn, v2)
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE app.gate_definition SET mode = 'enforce', calibration_version = :v WHERE gate_id = :g"),
                         {"v": v2, "g": GATE})
        out = shadow_eval(engine, org, new_run(engine, org), "normal", 0.97)
        assert out.model_decision == "pass" and out.confidence < 0.9           # still the pass option, but not confident enough
        assert out.effective_decision == "escalate" and out.approval_request_id is not None
        row = evaluation(engine, org, out.evaluation_id)
        assert row.output["run_looks"]["probabilities"]["normal"] == pytest.approx(0.97)      # the log keeps the raw numbers
        assert float(row.confidence) < 0.9 and row.calibration_version == v2
    finally:
        with engine.begin() as conn:
            conn.execute(text("UPDATE app.gate_definition SET mode = 'shadow', calibration_version = NULL WHERE gate_id = :g"),
                         {"g": GATE})


def test_a_gate_cannot_run_looser_than_its_calibration_was_measured(engine):
    v = f"cal-{uuid.uuid4().hex[:8]}"
    with tenant_session(engine, "daydor_ops") as conn:
        candidate(conn, v, thr=0.97)
        approve(conn, v)
    with pytest.raises(DBAPIError, match="is below the"):
        with engine.begin() as conn:
            conn.execute(text("UPDATE app.gate_definition SET mode = 'enforce', calibration_version = :v WHERE gate_id = :g"),
                         {"v": v, "g": GATE})                       # the gate's own threshold is 0.90
