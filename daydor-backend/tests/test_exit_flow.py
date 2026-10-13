"""Sprints 10-11: termination intake, legal-hold blocking, deprovisioning, final settlement,
disbursal and close-out end to end (docs/sprint-plan.md's two exit criteria)."""
import uuid
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from daydor.db.session import tenant_session
from daydor.exit.cobra import detect_cobra_event, request_cobra_notice_approval
from daydor.exit.deprovisioning import deprovision_identity
from daydor.exit.final_settlement import disburse_final_settlement
from daydor.exit.workflow import start_exit
from daydor.gates.hard import resolve
from daydor.workflow.engine import WorkflowEngine
from tests.exit_helpers import exit_org, hr_worker, instance_state, it_worker, pay_worker, resolve_and_relay  # noqa: F401
from tests.factories import insert


@pytest.fixture
def wf():
    return WorkflowEngine()


def _scalar(engine, tenant, sql, params):
    with tenant_session(engine, "tenant_hr", tenant) as conn:
        return conn.execute(text(sql), params).scalar_one()


def test_termination_under_active_legal_hold_is_blocked_from_it_deprovisioning(engine, exit_org, wf):
    tenant, employee = exit_org["tenant"], exit_org["employee"]
    with engine.begin() as conn:
        insert(conn, "legal_hold", tenant_id=tenant, scope_type="employee", scope_id=employee,
              reason="Pending litigation", placed_by_user_id=exit_org["founder_user"],
              placed_at="2026-05-01")

    with tenant_session(engine, "agent_hr", tenant) as conn:
        instance_id = start_exit(conn, wf, employee_id=employee, termination_type="involuntary",
                                 reason_code="performance", notice_date=date(2026, 6, 1),
                                 last_working_day=date(2026, 6, 15),
                                 initiated_by_user_id=exit_org["hr_user"])

    hr = hr_worker(engine, wf)
    hr.tick()  # legal_hold_checker: finds the active hold, parks on g_legalhold

    state = instance_state(engine, tenant, instance_id)
    assert state.state == "s02_legal_hold_check"
    assert state.status == "waiting_gate"

    it = it_worker(engine, wf)
    it.tick()  # nothing to do yet: the instance never reached s04_identity_account
    assert instance_state(engine, tenant, instance_id).state == "s02_legal_hold_check"

    with engine.begin() as conn:
        conn.execute(text("UPDATE legal_hold SET released_at = now() WHERE scope_id = :e"), {"e": employee})

    resolve_and_relay(engine, wf, tenant, "tenant_hr", exit_org["hr_user"], state.waiting_on_approval, "legalhold")
    assert instance_state(engine, tenant, instance_id).state == "s03_checklist"


def test_start_exit_replay_returns_existing_instance_without_advancing_it(engine, exit_org, wf):
    tenant, employee = exit_org["tenant"], exit_org["employee"]
    kwargs = dict(employee_id=employee, termination_type="voluntary", reason_code="resignation",
                  notice_date=date(2026, 6, 1), last_working_day=date(2026, 6, 15),
                  initiated_by_user_id=exit_org["hr_user"])
    with tenant_session(engine, "agent_hr", tenant) as conn:
        instance_id = start_exit(conn, wf, **kwargs)
    hr_worker(engine, wf).tick()   # moves the instance on from s02_legal_hold_check
    before = instance_state(engine, tenant, instance_id)

    with tenant_session(engine, "agent_hr", tenant) as conn:
        assert start_exit(conn, wf, **kwargs) == instance_id
    after = instance_state(engine, tenant, instance_id)
    assert (after.state, after.status) == (before.state, before.status)
    assert before.state != "s02_legal_hold_check"  # a replay used to skip ahead from here


def test_exit_flow_end_to_end_settlement_disbursal_and_closeout(engine, exit_org, wf):
    tenant = exit_org["tenant"]
    employee = exit_org["employee"]
    founder_user, hr_user = exit_org["founder_user"], exit_org["hr_user"]

    with tenant_session(engine, "agent_hr", tenant) as conn:
        instance_id = start_exit(conn, wf, employee_id=employee, termination_type="voluntary",
                                 reason_code="resignation", notice_date=date(2026, 6, 1),
                                 last_working_day=date(2026, 6, 30),
                                 initiated_by_user_id=hr_user)

    hr, it, pay = hr_worker(engine, wf), it_worker(engine, wf), pay_worker(engine, wf)

    hr.tick()  # legal_hold_checker: no hold -> auto-advances to s03_checklist
    assert instance_state(engine, tenant, instance_id).state == "s03_checklist"

    hr.tick()  # termination_checklist_builder -> s04_identity_account
    assert instance_state(engine, tenant, instance_id).state == "s04_identity_account"

    it.tick()  # deprovisioning_agent: only requests g_it_deprov, does not advance
    assert instance_state(engine, tenant, instance_id).state == "s04_identity_account"
    approval_id = _scalar(engine, tenant, "SELECT id FROM approval_request WHERE gate_type = "
                          "'g_it_deprov' AND subject_id = :i", {"i": exit_org["identity_account"]})

    with pytest.raises(DBAPIError):
        with tenant_session(engine, "agent_it", tenant) as conn:
            deprovision_identity(conn, wf, instance_id, identity_account_id=exit_org["identity_account"],
                                 approval_request_id=uuid.uuid4())

    with tenant_session(engine, "tenant_hr", tenant, user_id=hr_user) as conn:
        assert resolve(conn, approval_id, "approved") == "approved"
    with tenant_session(engine, "agent_it", tenant) as conn:
        deprovision_identity(conn, wf, instance_id, identity_account_id=exit_org["identity_account"],
                             approval_request_id=approval_id)
    assert instance_state(engine, tenant, instance_id).state == "s05_device_assignment"

    with engine.begin() as conn:
        access_revoked = conn.execute(
            text("SELECT revoked_at FROM app_access_grant WHERE identity_account_id = :i"),
            {"i": exit_org["identity_account"]}).scalar_one()
    assert access_revoked is not None

    it.tick()  # equipment_return_tracker -> s06_final_settlement_calc
    assert instance_state(engine, tenant, instance_id).state == "s06_final_settlement_calc"
    with engine.begin() as conn:
        assert conn.execute(text("SELECT returned_at FROM device_assignment WHERE employee_id = :e"),
                            {"e": employee}).scalar_one() is not None

    pay.tick()  # final_pay_calculator: parks on g_finalpay
    state = instance_state(engine, tenant, instance_id)
    assert state.state == "s06_final_settlement_calc"
    assert state.status == "waiting_gate"

    resolve_and_relay(engine, wf, tenant, "tenant_founder", founder_user, state.waiting_on_approval, "finalpay")
    assert instance_state(engine, tenant, instance_id).state == "s07_final_settlement_created"

    pay.tick()  # final_settlement_opener -> s08_disbursed
    assert instance_state(engine, tenant, instance_id).state == "s08_disbursed"

    with engine.begin() as conn:
        final_settlement_id, total_settlement, pending_wages, gratuity_payout, leave_encashment, recoveries = \
            conn.execute(text("SELECT id, total_settlement, pending_wages, gratuity_payout, "
                              "leave_encashment, recoveries FROM final_settlement WHERE employee_id = :e"),
                        {"e": employee}).one()
    assert total_settlement == pending_wages + gratuity_payout + leave_encashment - recoveries

    pay.tick()  # direct_deposit_disburser: only requests g_pay_disburse, does not advance
    assert instance_state(engine, tenant, instance_id).state == "s08_disbursed"
    disburse_approval_id = _scalar(engine, tenant, "SELECT id FROM approval_request WHERE "
                                   "gate_type = 'g_pay_disburse' AND subject_id = :i",
                                   {"i": final_settlement_id})

    with pytest.raises(DBAPIError):
        with tenant_session(engine, "agent_pay", tenant) as conn:
            disburse_final_settlement(conn, wf, instance_id, final_settlement_id=final_settlement_id,
                                      approval_request_id=disburse_approval_id)  # still pending

    with tenant_session(engine, "tenant_founder", tenant, user_id=founder_user) as conn:
        assert resolve(conn, disburse_approval_id, "approved") == "approved"
    with tenant_session(engine, "agent_pay", tenant) as conn:
        disburse_final_settlement(conn, wf, instance_id, final_settlement_id=final_settlement_id,
                                  approval_request_id=disburse_approval_id)
    assert instance_state(engine, tenant, instance_id).state == "s09_cobra"

    with engine.begin() as conn:
        assert conn.execute(text("SELECT disbursed_at FROM final_settlement WHERE id = :i"),
                            {"i": final_settlement_id}).scalar_one() is not None

    hr.tick()  # cobra_trigger_detector: IN employee -> no COBRA event, advances straight through
    assert instance_state(engine, tenant, instance_id).state == "s10_vesting"

    hr.tick()  # vesting_schedule_tracker -> s11_rehire_flag
    hr.tick()  # rehire_eligibility_flagger -> s12_employee_closeout
    hr.tick()  # employee_record_writer_closeout -> done
    assert instance_state(engine, tenant, instance_id).status == "completed"

    with engine.begin() as conn:
        is_active, date_of_exit = conn.execute(
            text("SELECT is_active, date_of_exit FROM employee WHERE id = :e"), {"e": employee}).one()
    assert is_active is False
    assert date_of_exit == date(2026, 6, 30)


def test_cobra_notice_is_impossible_without_an_approved_g_cobra_request(engine, exit_org):
    tenant = exit_org["tenant"]
    with engine.begin() as conn:
        le_us = insert(conn, "legal_entity", tenant_id=tenant, name="Exit Co US Inc", country_code="US")
        loc = insert(conn, "location", tenant_id=tenant, name="NY Office", country_code="US",
                    state_code="NY", legal_entity_id=le_us)
        employee = insert(conn, "employee", tenant_id=tenant, full_name="US Departing Employee",
                          legal_entity_id=le_us, department_id=exit_org["department"], location_id=loc,
                          hire_event_id=f"hire-{uuid.uuid4().hex[:10]}", date_of_joining="2024-01-01")

    with tenant_session(engine, "agent_hr", tenant) as conn:
        cobra_event_id = detect_cobra_event(conn, employee_id=employee, event_date=date(2026, 6, 30))
        assert cobra_event_id is not None
        approval_id = request_cobra_notice_approval(conn, cobra_event_id=cobra_event_id)

    with pytest.raises(DBAPIError):
        with tenant_session(engine, "agent_hr", tenant) as conn:
            conn.execute(text("UPDATE cobra_event SET approval_request_id = :a, notice_sent_at = now() "
                              "WHERE id = :i"), {"a": uuid.uuid4(), "i": cobra_event_id})

    with tenant_session(engine, "tenant_hr", tenant, user_id=exit_org["hr_user"]) as conn:
        assert resolve(conn, approval_id, "approved") == "approved"

    with tenant_session(engine, "agent_hr", tenant) as conn:
        conn.execute(text("UPDATE cobra_event SET approval_request_id = :a, notice_sent_at = now() "
                          "WHERE id = :i"), {"a": approval_id, "i": cobra_event_id})

    with engine.begin() as conn:
        notice_sent_at = conn.execute(text("SELECT notice_sent_at FROM cobra_event WHERE id = :i"),
                                      {"i": cobra_event_id}).scalar_one()
    assert notice_sent_at is not None
