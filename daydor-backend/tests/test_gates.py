"""Hard gates (maker-checker, approver roles, guarded writes) and Laya soft gates."""
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from daydor.db.session import tenant_session
from daydor.gates.hard import request_approval, resolve, status
from daydor.gates.decider import Answer, Choice, DecisionSchema, DeciderResult
from daydor.gates.registry import seed_sql
from daydor.gates.soft import ForbiddenInput, SoftGate, run_soft_gate
from daydor.model import load_model
from tests.factories import insert

SQL = Path(__file__).resolve().parents[1] / "migrations" / "sql"


@pytest.fixture
def run_id(engine, org):
    with engine.begin() as conn:
        retention = insert(conn, "retention_policy")
        return insert(conn, "payroll_run", tenant_id=org.tenant_a, legal_entity_id=org.legal_entity_a,
                      status="built", gross_total=1_200_000, net_total=980_000, anomaly_score=0.02,
                      retention_class=retention)


def as_payroll(engine, org):
    return tenant_session(engine, "tenant_payroll", org.tenant_a, user_id=org.user["payroll_lead"])


def as_founder(engine, org, user="founder_user"):
    return tenant_session(engine, "tenant_founder", org.tenant_a, user_id=org.user[user])


def disburse(engine, org, run, approval):
    with tenant_session(engine, "agent_pay", org.tenant_a) as conn:
        conn.execute(text("UPDATE payroll_run SET approval_request_id = :a, disbursed_at = now() "
                          "WHERE id = :r"), {"a": approval, "r": run})


# ---------------------------------------------------------------- registry
def test_all_model_gates_registered_with_mapped_roles(engine):
    with engine.connect() as conn:
        rows = {r.gate_id: r for r in conn.execute(text("SELECT * FROM app.gate_definition"))}
    for g in load_model().gates:
        assert rows[g["id"]].kind == "hard"
    assert set(rows["g_pay_anomaly"].approver_roles) == {"tenant_payroll", "daydor_ops"}
    assert rows["sg_payroll_anomaly_precheck"].escalate_to == "g_pay_anomaly"
    assert all(r.mode == "shadow" for r in rows.values() if r.kind == "soft")


def test_committed_gate_seed_matches_registry():
    assert (SQL / "0007_gate_seed.sql").read_text() == seed_sql()


# ---------------------------------------------------------------- hard gates
def test_disbursal_blocked_without_approval(engine, org, run_id):
    with pytest.raises(DBAPIError, match="needs an approved g_pay_disburse gate"):
        disburse(engine, org, run_id, None)


def test_full_maker_checker_flow_unlocks_disbursal(engine, org, run_id):
    with as_payroll(engine, org) as conn:
        req = request_approval(conn, "g_pay_disburse", "payroll_run", run_id)
        maker = conn.execute(text("SELECT requested_by_user_id FROM approval_request WHERE id = :r"),
                             {"r": req}).scalar_one()
    assert maker == org.user["payroll_lead"]
    with as_founder(engine, org) as conn:
        assert resolve(conn, req, "approved", "Matches budget") == "approved"
    disburse(engine, org, run_id, req)
    with as_founder(engine, org) as conn:
        row = conn.execute(text("SELECT resolved_by_user_id, disbursed_at FROM approval_request ar "
                                "JOIN payroll_run pr ON pr.approval_request_id = ar.id WHERE pr.id = :r"),
                           {"r": run_id}).one()
    assert row.resolved_by_user_id == org.user["founder_user"] and row.disbursed_at is not None


def test_request_is_idempotent_per_gate_and_row(engine, org, run_id):
    with as_payroll(engine, org) as conn:
        a = request_approval(conn, "g_pay_disburse", "payroll_run", run_id)
        b = request_approval(conn, "g_pay_disburse", "payroll_run", run_id)
    assert a == b


def test_maker_cannot_approve_own_request(engine, org, run_id):
    with as_founder(engine, org) as conn:
        req = request_approval(conn, "g_pay_disburse", "payroll_run", run_id)
    with pytest.raises(DBAPIError, match="maker-checker"):
        with as_founder(engine, org) as conn:
            resolve(conn, req, "approved")


def test_wrong_role_cannot_resolve(engine, org, run_id):
    with tenant_session(engine, "tenant_hr", org.tenant_a, user_id=org.user["hr_admin"]) as conn:
        req = request_approval(conn, "g_pay_disburse", "payroll_run", run_id)
    with pytest.raises(DBAPIError, match="cannot resolve gate g_pay_disburse"):
        with as_payroll(engine, org) as conn:
            resolve(conn, req, "approved")


def test_agents_cannot_resolve_gates(engine, org, run_id):
    with as_payroll(engine, org) as conn:
        req = request_approval(conn, "g_pay_disburse", "payroll_run", run_id)
    with pytest.raises(ProgrammingError, match="permission denied for function resolve_approval"):
        with tenant_session(engine, "agent_pay", org.tenant_a) as conn:
            resolve(conn, req, "approved")


def test_direct_status_update_is_refused(engine, org, run_id):
    with as_payroll(engine, org) as conn:
        req = request_approval(conn, "g_pay_disburse", "payroll_run", run_id)
    with pytest.raises(DBAPIError, match="app.resolve_approval"):
        with as_founder(engine, org) as conn:
            conn.execute(text("UPDATE approval_request SET status = 'approved' WHERE id = :r"), {"r": req})


def test_requester_cannot_be_spoofed(engine, org, run_id):
    with as_payroll(engine, org) as conn:
        rid = conn.execute(text(
            "INSERT INTO approval_request (gate_type, subject_table, subject_id, status, idempotency_key, "
            "requested_by_user_id) VALUES ('g_pay_disburse', 'payroll_run', :s, 'pending', :k, :fake) "
            "RETURNING requested_by_user_id"),
            {"s": run_id, "k": str(uuid.uuid4()), "fake": org.user["founder_user"]}).scalar_one()
    assert rid == org.user["payroll_lead"]


def test_resolved_request_is_immutable(engine, org, run_id):
    with as_payroll(engine, org) as conn:
        req = request_approval(conn, "g_pay_disburse", "payroll_run", run_id)
    with as_founder(engine, org) as conn:
        resolve(conn, req, "rejected", "Wrong period")
    with pytest.raises(DBAPIError, match="already rejected"):
        with as_founder(engine, org) as conn:
            resolve(conn, req, "approved")


def test_approval_for_another_row_does_not_unlock(engine, org, run_id):
    with engine.begin() as conn:
        other = insert(conn, "payroll_run", tenant_id=org.tenant_a, legal_entity_id=org.legal_entity_a,
                       retention_class=insert(conn, "retention_policy"))
    with as_payroll(engine, org) as conn:
        req = request_approval(conn, "g_pay_disburse", "payroll_run", other)
    with as_founder(engine, org) as conn:
        resolve(conn, req, "approved")
    with pytest.raises(DBAPIError, match="needs an approved"):
        disburse(engine, org, run_id, req)


def test_disbursed_at_is_final(engine, org, run_id):
    with as_payroll(engine, org) as conn:
        req = request_approval(conn, "g_pay_disburse", "payroll_run", run_id)
    with as_founder(engine, org) as conn:
        resolve(conn, req, "approved")
    disburse(engine, org, run_id, req)
    with pytest.raises(DBAPIError, match="final once set"):
        disburse(engine, org, run_id, req)


def test_multi_role_gate_accepts_either_role(engine, org, run_id):
    with tenant_session(engine, "tenant_hr", org.tenant_a, user_id=org.user["hr_admin"]) as conn:
        req = request_approval(conn, "g_pay_anomaly", "payroll_run", run_id)
    with tenant_session(engine, "daydor_ops", org.tenant_a, user_id=org.user["payroll_lead"]) as conn:
        assert resolve(conn, req, "approved") == "approved"


# ---------------------------------------------------------------- soft gates (Laya)
SCHEMA = DecisionSchema("payroll_run_normality", "1", (Choice(
    "run_looks", "Does this payroll run look normal compared with past runs?",
    {"normal": "totals and anomaly score are in line with past runs",
     "unusual": "totals or anomaly score differ markedly from past runs"}),))


class FakeDecider:
    """Stands in for the decider. Reports engine 'laya' so it matches the gate registry."""
    engine = "laya"

    def __init__(self, value="normal", p=0.97, error=None):
        self.value, self.p, self.error, self.calls = value, p, error, []

    def decide(self, schema, state, timeout_s):
        self.calls.append(state)
        if self.error:
            raise self.error
        other = "unusual" if self.value == "normal" else "normal"
        probs = {self.value: self.p, other: 1 - self.p}
        return DeciderResult({"run_looks": Answer(self.value, probs, self.p)}, "laya", "fake-1")


def payroll_state(conn, run):
    r = conn.execute(text("SELECT gross_total, net_total, anomaly_score FROM payroll_run WHERE id = :r"),
                     {"r": run}).one()
    return {"gross_total": float(r.gross_total), "net_total": float(r.net_total),
            "anomaly_score": float(r.anomaly_score)}


def pass_if_normal(result):
    a = result.answers["run_looks"]
    return a.value == "normal", a.confidence


PAYROLL_GATE = SoftGate("sg_payroll_anomaly_precheck", SCHEMA,
                        ("payroll_run.gross_total", "payroll_run.net_total", "payroll_run.anomaly_score"),
                        payroll_state, pass_if_normal)


@pytest.fixture
def enforce_mode(engine):
    with engine.begin() as conn:
        conn.execute(text("UPDATE app.gate_definition SET mode = 'enforce', calibration_version = 'test-cal-1' "
                          "WHERE gate_id = 'sg_payroll_anomaly_precheck'"))
    yield
    with engine.begin() as conn:
        conn.execute(text("UPDATE app.gate_definition SET mode = 'shadow', calibration_version = NULL "
                          "WHERE gate_id = 'sg_payroll_anomaly_precheck'"))


def soft(engine, org, run, client):
    with tenant_session(engine, "agent_pay", org.tenant_a) as conn:
        return run_soft_gate(conn, PAYROLL_GATE, "payroll_run", run, client)


def evaluation(engine, org, eid):
    with tenant_session(engine, "tenant_payroll", org.tenant_a) as conn:
        return conn.execute(text("SELECT * FROM app.gate_evaluation WHERE id = :e"), {"e": eid}).one()


def test_shadow_mode_logs_but_always_escalates(engine, org, run_id):
    out = soft(engine, org, run_id, FakeDecider("normal", 0.99))
    assert out.model_decision == "pass" and out.effective_decision == "escalate"
    assert out.approval_request_id is not None
    row = evaluation(engine, org, out.evaluation_id)
    assert row.mode == "shadow" and len(row.input_hash) == 64
    assert "1200000" not in str(row.output)          # inputs are hashed, not stored


def test_enforce_mode_confident_pass_skips_extra_review(engine, org, run_id, enforce_mode):
    out = soft(engine, org, run_id, FakeDecider("normal", 0.97))
    assert out.effective_decision == "pass" and out.approval_request_id is None


def test_enforce_mode_low_confidence_escalates(engine, org, run_id, enforce_mode):
    out = soft(engine, org, run_id, FakeDecider("normal", 0.70))
    assert out.effective_decision == "escalate"
    with as_payroll(engine, org) as conn:
        assert status(conn, out.approval_request_id) == "pending"


def test_enforce_mode_unusual_escalates_to_named_hard_gate(engine, org, run_id, enforce_mode):
    out = soft(engine, org, run_id, FakeDecider("unusual", 0.99))
    with as_payroll(engine, org) as conn:
        gate = conn.execute(text("SELECT gate_type FROM approval_request WHERE id = :r"),
                            {"r": out.approval_request_id}).scalar_one()
    assert out.effective_decision == "escalate" and gate == "g_pay_anomaly"


def test_decider_error_fails_closed(engine, org, run_id, enforce_mode):
    out = soft(engine, org, run_id, FakeDecider(error=TimeoutError("no answer")))
    assert out.model_decision == "error" and out.effective_decision == "escalate"
    assert "TimeoutError" in evaluation(engine, org, out.evaluation_id).error


def test_unwired_http_client_fails_closed(engine, org, run_id, enforce_mode):
    from daydor.gates.decider import LayaClient
    out = soft(engine, org, run_id, LayaClient())
    assert out.effective_decision == "escalate" and out.model_decision == "error"


def test_restricted_columns_can_never_be_inputs(engine, org, run_id):
    bad = SoftGate("sg_payroll_anomaly_precheck", SCHEMA, ("employee.date_of_birth",),
                   lambda c, s: {}, pass_if_normal)
    decider = FakeDecider()
    with pytest.raises(ForbiddenInput, match="restricted data never goes to a model"):
        with tenant_session(engine, "agent_pay", org.tenant_a) as conn:
            run_soft_gate(conn, bad, "payroll_run", run_id, decider)
    assert decider.calls == []


def test_inputs_above_gate_class_limit_rejected(engine, org):
    gate = SoftGate("sg_access_request_precheck", SCHEMA, ("payroll_run.gross_total",),
                    lambda c, s: {}, pass_if_normal)
    with pytest.raises(ForbiddenInput, match="above this gate's limit C1"):
        with tenant_session(engine, "agent_it", org.tenant_a) as conn:
            run_soft_gate(conn, gate, "app_access_grant", uuid.uuid4(), FakeDecider())


def test_undeclared_state_fields_rejected(engine, org, run_id):
    leaky = SoftGate("sg_payroll_anomaly_precheck", SCHEMA, ("payroll_run.gross_total",),
                     lambda c, s: {"gross_total": 1, "employee_names": ["x"]}, pass_if_normal)
    with pytest.raises(ForbiddenInput, match="undeclared fields"):
        with tenant_session(engine, "agent_pay", org.tenant_a) as conn:
            run_soft_gate(conn, leaky, "payroll_run", run_id, FakeDecider())


def test_database_forces_shadow_mode_to_escalate(engine, org, run_id):
    with tenant_session(engine, "agent_pay", org.tenant_a) as conn:
        eid = conn.execute(text(
            "SELECT app.record_gate_evaluation('sg_payroll_anomaly_precheck', 'payroll_run', :s, 'laya', "
            "NULL, 'x@1', 'h', ARRAY['payroll_run.gross_total'], NULL, 0.999, 'pass', 5, NULL)"),
            {"s": run_id}).scalar_one()
    assert evaluation(engine, org, eid).effective_decision == "escalate"


def test_gate_evaluations_are_append_only(engine, org, run_id):
    out = soft(engine, org, run_id, FakeDecider())
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:     # even the superuser connection hits the trigger
            conn.execute(text("UPDATE app.gate_evaluation SET effective_decision = 'pass' WHERE id = :e"),
                         {"e": out.evaluation_id})


def test_choice_cardinality_limit():
    with pytest.raises(ValueError):
        Choice("too_many", "pick one", {str(i): f"option {i}" for i in range(21)})


# ---------------------------------------------------------------- Laya-specific database rules
def test_enforce_mode_is_refused_without_a_calibration(engine):
    with pytest.raises(DBAPIError, match="gate_definition_enforce_needs_calibration"):
        with engine.begin() as conn:
            conn.execute(text("UPDATE app.gate_definition SET mode = 'enforce' "
                              "WHERE gate_id = 'sg_payroll_anomaly_precheck'"))


def test_soft_gates_record_their_engine_and_checkpoint(engine):
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT engine, checkpoint, calibration_version FROM app.gate_definition "
                                 "WHERE kind = 'soft'")).all()
    assert rows and all(r.engine == "laya" and r.checkpoint == "english" and r.calibration_version is None
                        for r in rows)


def test_evaluation_from_the_wrong_engine_is_refused(engine, org, run_id):
    with pytest.raises(DBAPIError, match="is decided by laya, not other"):
        with tenant_session(engine, "agent_pay", org.tenant_a) as conn:
            conn.execute(text(
                "SELECT app.record_gate_evaluation('sg_payroll_anomaly_precheck', 'payroll_run', :s, 'other', "
                "NULL, 'x@1', 'h', ARRAY['payroll_run.gross_total'], NULL, 0.9, 'pass', 5, NULL)"),
                {"s": run_id})


def test_evaluation_records_which_calibration_decided(engine, org, run_id, enforce_mode):
    out = soft(engine, org, run_id, FakeDecider("normal", 0.97))
    assert evaluation(engine, org, out.evaluation_id).calibration_version == "test-cal-1"


def test_enforced_evaluations_record_the_calibration_that_decided_them(engine, org, run_id, enforce_mode):
    out = soft(engine, org, run_id, FakeDecider("normal", 0.97))
    assert evaluation(engine, org, out.evaluation_id).calibration_version == "test-cal-1"


def test_shadow_evaluations_carry_no_calibration(engine, org, run_id):
    out = soft(engine, org, run_id, FakeDecider("normal", 0.99))
    assert evaluation(engine, org, out.evaluation_id).calibration_version is None


def test_runner_rejects_a_client_for_a_different_engine(engine, org, run_id):
    class Other(FakeDecider):
        engine = "other"
    with pytest.raises(ValueError, match="is decided by laya, not other"):
        soft(engine, org, run_id, Other())
