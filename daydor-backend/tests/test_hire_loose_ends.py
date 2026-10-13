"""Three loose ends of the hire flow: a finished hire fills its position and requisition, off-template
access grants go through sg_access_request_precheck, and the I-9 section 2 deadline timer has a consumer."""
from datetime import date

import pytest
from sqlalchemy import text

from daydor.agents.session import worker_session
from tests.calibration_helpers import approve_calibration
from daydor.db.session import tenant_session
from daydor.gates.decider import Answer, DeciderResult
from daydor.hire.access_grant import grant_app_access
from daydor.hire.requisition import NoVacantPosition, open_requisition
from daydor.hire.work_authorization import check_i9_section2, handle_i9_section2_due
from daydor.queue import Worker
from daydor.workflow.engine import WorkflowEngine
from tests.factories import insert
from tests.hire_helpers import (access_role_template, comp_band, drive_hire_to_completion,  # noqa: F401
                                drive_to_identity, retention_policy)


class FakeAccessJev:
    engine = "laya"

    def __init__(self, value="consistent", p=0.99):
        self.value, self.p, self.calls = value, p, []

    def decide(self, schema, state, timeout_s):
        self.calls.append(state)
        other = "inconsistent" if self.value == "consistent" else "consistent"
        probs = {self.value: self.p, other: 1 - self.p}
        return DeciderResult({"request_looks": Answer(self.value, probs, self.p)}, "laya", "fake-1")


@pytest.fixture
def enforce_access_gate(engine):
    sql = ("UPDATE app.gate_definition SET mode = :m, calibration_version = :c "
           "WHERE gate_id = 'sg_access_request_precheck'")
    with engine.begin() as conn:
        version = approve_calibration(conn, "sg_access_request_precheck")
        conn.execute(text(sql), {"m": "enforce", "c": version})
    yield
    with engine.begin() as conn:
        conn.execute(text(sql), {"m": "shadow", "c": None})


# 1. position / requisition close

def test_completed_hire_fills_the_position_and_requisition(engine, hire_org, comp_band, retention_policy,
                                                           access_role_template):
    tenant = hire_org["tenant"]
    wf = WorkflowEngine()
    instance_id, requisition_id, employee_id, instance = drive_hire_to_completion(
        engine, hire_org, wf, comp_band_id=comp_band, retention_class_id=retention_policy,
        worker_name="w-fill")
    assert instance.status == "completed"
    with tenant_session(engine, "tenant_hr", tenant) as conn:
        position = conn.execute(text("SELECT status, current_employee_id FROM position WHERE id = :p"),
                                {"p": hire_org["position"]}).one()
        requisition = conn.execute(text("SELECT status FROM job_requisition WHERE id = :r"),
                                   {"r": requisition_id}).scalar_one()
    assert (position.status, position.current_employee_id) == ("filled", employee_id)
    assert requisition == "filled"
    # The seat is taken: a second hire for it is refused up front.
    with worker_session(engine, "hire-intake", tenant) as conn:
        with pytest.raises(NoVacantPosition):
            open_requisition(conn, position_id=hire_org["position"],
                             hiring_manager_id=hire_org["hiring_manager"], target_start_date=date(2026, 6, 1))


def test_an_unfinished_hire_leaves_the_position_open(engine, hire_org, comp_band, retention_policy):
    wf = WorkflowEngine()
    _, requisition_id, _, instance = drive_to_identity(
        engine, hire_org, wf, comp_band_id=comp_band, retention_class_id=retention_policy,
        worker_name="w-unfilled")
    assert instance.status == "running"
    with tenant_session(engine, "tenant_hr", hire_org["tenant"]) as conn:
        status = conn.execute(text("SELECT status FROM position WHERE id = :p"),
                              {"p": hire_org["position"]}).scalar_one()
    assert status == "open"


# 2. sg_access_request_precheck

def _identity_and_profile(engine, tenant, employee_id):
    with tenant_session(engine, "tenant_hr", tenant) as conn:
        return conn.execute(
            text("SELECT ia.id AS account, jp.id AS profile FROM identity_account ia "
                 "JOIN employee e ON e.id = ia.employee_id JOIN position p ON p.id = e.position_id "
                 "JOIN job_profile jp ON jp.id = p.job_profile_id WHERE ia.employee_id = :e"),
            {"e": employee_id}).one()


def _grant(engine, tenant, ids, jev, extra):
    with worker_session(engine, "app-access-granter", tenant) as conn:
        return grant_app_access(conn, identity_account_id=ids.account, job_profile_id=ids.profile,
                                extra_access=extra, decider=jev)


def _evaluations(engine, grant_ids):
    with engine.connect() as conn:
        return conn.execute(text("SELECT gate_id, subject_id, effective_decision, model_decision "
                                 "FROM app.gate_evaluation WHERE subject_id = ANY(:g)"),
                            {"g": list(grant_ids)}).all()


def test_off_template_grant_is_prechecked_and_still_escalates_in_shadow_mode(engine, hire_org, comp_band,
                                                                             retention_policy):
    wf = WorkflowEngine()
    _, _, employee_id, _ = drive_to_identity(engine, hire_org, wf, comp_band_id=comp_band,
                                             retention_class_id=retention_policy, worker_name="w-sg-shadow")
    ids = _identity_and_profile(engine, hire_org["tenant"], employee_id)
    jev = FakeAccessJev("consistent", 0.99)
    result = _grant(engine, hire_org["tenant"], ids, jev, [{"app_name": "prod-db", "permission_level": "admin"}])
    assert result["requires_g_it_offtemplate"] is True        # shadow mode: a human still reviews it
    (ev,) = _evaluations(engine, result["grant_ids"])
    assert (ev.gate_id, ev.model_decision, ev.effective_decision) == (
        "sg_access_request_precheck", "pass", "escalate")
    assert jev.calls == [{"app_name": "prod-db", "permission_level": "admin", "title": jev.calls[0]["title"]}]
    # The gate was told not to open its own approval: the workflow opens the one IT sees.
    with engine.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM approval_request WHERE subject_id = ANY(:g)"),
                         {"g": list(result["grant_ids"])}).scalar_one()
    assert n == 0


def test_enforced_precheck_skips_review_only_when_confident(engine, hire_org, comp_band, retention_policy,
                                                            enforce_access_gate):
    wf = WorkflowEngine()
    _, _, employee_id, _ = drive_to_identity(engine, hire_org, wf, comp_band_id=comp_band,
                                             retention_class_id=retention_policy, worker_name="w-sg-enforce")
    ids = _identity_and_profile(engine, hire_org["tenant"], employee_id)
    extra = [{"app_name": "wiki", "permission_level": "read"}]
    ok = _grant(engine, hire_org["tenant"], ids, FakeAccessJev("consistent", 0.99), extra)
    assert ok["requires_g_it_offtemplate"] is False
    (ev,) = _evaluations(engine, ok["grant_ids"])
    assert (ev.model_decision, ev.effective_decision) == ("pass", "pass")


def test_unwired_decider_fails_closed_so_the_grant_escalates(engine, hire_org, comp_band, retention_policy,
                                                             enforce_access_gate):
    wf = WorkflowEngine()
    _, _, employee_id, _ = drive_to_identity(engine, hire_org, wf, comp_band_id=comp_band,
                                             retention_class_id=retention_policy, worker_name="w-sg-closed")
    ids = _identity_and_profile(engine, hire_org["tenant"], employee_id)
    result = _grant(engine, hire_org["tenant"], ids, None, [{"app_name": "wiki", "permission_level": "read"}])
    assert result["requires_g_it_offtemplate"] is True
    (ev,) = _evaluations(engine, result["grant_ids"])
    assert ev.model_decision == "error" and ev.effective_decision == "escalate"


def test_on_template_only_grants_never_call_the_precheck(engine, hire_org, comp_band, retention_policy,
                                                         access_role_template):
    wf = WorkflowEngine()
    _, _, employee_id, _ = drive_to_identity(engine, hire_org, wf, comp_band_id=comp_band,
                                             retention_class_id=retention_policy, worker_name="w-sg-none")
    ids = _identity_and_profile(engine, hire_org["tenant"], employee_id)
    jev = FakeAccessJev()
    result = _grant(engine, hire_org["tenant"], ids, jev, None)
    assert result["requires_g_it_offtemplate"] is False and jev.calls == []


# 3. I-9 section 2 timer consumer

def _us_hire(engine, hire_org, comp_band, retention_policy, name):
    with engine.begin() as conn:
        le = insert(conn, "legal_entity", tenant_id=hire_org["tenant"], name=f"{name} Inc", country_code="US")
    wf = WorkflowEngine()
    _, _, employee_id, _ = drive_to_identity(engine, hire_org, wf, comp_band_id=comp_band,
                                             retention_class_id=retention_policy, worker_name=name,
                                             legal_entity_id=le)
    with tenant_session(engine, "tenant_hr", hire_org["tenant"]) as conn:
        wa = conn.execute(text("SELECT id FROM work_authorization WHERE employee_id = :e"),
                          {"e": employee_id}).scalar_one()
    return employee_id, wa


def _overdue_events(engine, wa):
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM app.outbox WHERE topic = 'i9.section2_overdue' "
                                 "AND subject_id = :w"), {"w": wa}).scalar_one()


def test_overdue_i9_raises_an_event_through_the_real_timer(engine, hire_org, comp_band, retention_policy):
    employee_id, wa = _us_hire(engine, hire_org, comp_band, retention_policy, "w-i9-late")
    # The fixture's start date is in the past, so the timer is already due and has fired into the
    # 'hr' queue (see test_hire_identity); a worker with the real handler now consumes it.
    w = Worker(engine, "hr", "w-i9-consumer")
    w.register("i9_section2_due", worker="root-orchestrator", fn=handle_i9_section2_due)
    w.tick()
    assert _overdue_events(engine, wa) == 1
    w.tick()
    assert _overdue_events(engine, wa) == 1                    # consumed once, not repeated


def test_i9_completed_in_time_or_employee_gone_is_silent(engine, hire_org, comp_band, retention_policy):
    tenant = hire_org["tenant"]
    employee_id, wa = _us_hire(engine, hire_org, comp_band, retention_policy, "w-i9-done")
    with engine.begin() as conn:
        conn.execute(text("UPDATE work_authorization SET i9_section2_completed_at = now() WHERE id = :w"),
                     {"w": wa})
    with worker_session(engine, "root-orchestrator", tenant) as conn:
        assert check_i9_section2(conn, employee_id=employee_id, work_authorization_id=wa) == {"overdue": False}
    with engine.begin() as conn:
        conn.execute(text("UPDATE work_authorization SET i9_section2_completed_at = NULL WHERE id = :w"),
                     {"w": wa})
        conn.execute(text("UPDATE employee SET is_active = false WHERE id = :e"), {"e": employee_id})
    with worker_session(engine, "root-orchestrator", tenant) as conn:
        assert check_i9_section2(conn, employee_id=employee_id, work_authorization_id=wa) == {"overdue": False}
    assert _overdue_events(engine, wa) == 0


def test_enforced_precheck_escalates_when_not_confident(engine, hire_org, comp_band, retention_policy,
                                                        enforce_access_gate):
    wf = WorkflowEngine()
    _, _, employee_id, _ = drive_to_identity(engine, hire_org, wf, comp_band_id=comp_band,
                                             retention_class_id=retention_policy, worker_name="w-sg-low")
    ids = _identity_and_profile(engine, hire_org["tenant"], employee_id)
    result = _grant(engine, hire_org["tenant"], ids, FakeAccessJev("consistent", 0.70),
                    [{"app_name": "wiki", "permission_level": "read"}])
    assert result["requires_g_it_offtemplate"] is True
