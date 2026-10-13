"""The exit flow on workflow version 3: every handler and guarded call runs as the worker that owns it.

Version 3 splits the close-out (vesting read, rehire flag, employee close) into one step per worker.
It is inserted inactive by 0029, so these tests switch it on for their own duration and restore it."""
import uuid
from datetime import date

import pytest
from sqlalchemy import text

from daydor.agents.session import worker_session
from daydor.db.session import tenant_session
from daydor.exit.checklist import handle_termination_checklist_builder
from daydor.exit.closeout import (handle_employee_record_writer_closeout, handle_rehire_eligibility_flagger,
                                  handle_vesting_schedule_tracker)
from daydor.exit.cobra import handle_cobra_trigger_detector
from daydor.exit.deprovisioning import deprovision_identity, handle_deprovisioning_agent
from daydor.exit.device_return import handle_equipment_return_tracker
from daydor.exit.final_settlement import (disburse_final_settlement, handle_direct_deposit_disburser,
                                          handle_final_pay_calculator, handle_final_settlement_opener)
from daydor.exit.legal_hold import handle_legal_hold_checker
from daydor.exit.workflow import EXIT_DEFINITION_V3, seed_sql_v3, start_exit
from daydor.gates.hard import resolve
from daydor.queue import Worker
from daydor.workflow.engine import WorkflowEngine
from tests.exit_helpers import exit_org, instance_state, resolve_and_relay  # noqa: F401
from tests.test_exit_flow import _scalar

from pathlib import Path

SQL = Path(__file__).resolve().parents[1] / "migrations" / "sql"


@pytest.fixture
def wf():
    return WorkflowEngine()


@pytest.fixture
def exit_v3(engine):
    """Make version 3 the active 'exit' definition for one test, then put version 2 back."""
    def flip(v_off, v_on):
        with tenant_session(engine, "daydor_ops") as conn:
            conn.execute(text("UPDATE app.workflow_definition SET active = false WHERE name = 'exit' AND version = :o"),
                         {"o": v_off})
            conn.execute(text("UPDATE app.workflow_definition SET active = true WHERE name = 'exit' AND version = :n"),
                         {"n": v_on})
    flip(2, 3)
    try:
        yield
    finally:
        flip(3, 2)


def test_committed_v3_sql_matches_the_definition():
    assert (SQL / "0029_exit_workflow_v3.sql").read_text() == seed_sql_v3()


def test_v3_is_inserted_inactive_and_v2_stays_active(engine, org):
    with engine.connect() as conn:
        rows = dict(conn.execute(text("SELECT version, active FROM app.workflow_definition WHERE name = 'exit'")).all())
    assert rows == {1: False, 2: True, 3: False}


def test_v3_keeps_every_state_and_replaces_only_the_closeout():
    from daydor.exit.workflow import EXIT_DEFINITION as V2
    assert set(V2["states"]) - set(EXIT_DEFINITION_V3["states"]) == {"s10_closeout"}
    assert set(EXIT_DEFINITION_V3["states"]) - set(V2["states"]) == {"s10_vesting", "s11_rehire_flag",
                                                                       "s12_employee_closeout"}
    kinds = {j["kind"] for s in EXIT_DEFINITION_V3["states"].values() for j in s.get("enter_jobs", [])}
    assert "employee_closeout" not in kinds


def _workers(engine, wf):
    hr, it, pay = Worker(engine, "hr", "w-hr"), Worker(engine, "it", "w-it"), Worker(engine, "pay", "w-pay")
    hr.register("legal_hold_checker", worker="root-orchestrator", fn=handle_legal_hold_checker(wf))
    hr.register("termination_checklist_builder", worker="termination-checklist-builder",
                fn=handle_termination_checklist_builder(wf))
    hr.register("cobra_trigger_detector", worker="cobra-trigger-detector", fn=handle_cobra_trigger_detector(wf))
    hr.register("vesting_schedule_tracker", worker="vesting-schedule-tracker", fn=handle_vesting_schedule_tracker(wf))
    hr.register("rehire_eligibility_flagger", worker="rehire-eligibility-flagger",
                fn=handle_rehire_eligibility_flagger(wf))
    hr.register("employee_record_writer_closeout", worker="employee-record-writer",
                fn=handle_employee_record_writer_closeout(wf))
    it.register("deprovisioning_agent", worker="deprovisioning-agent", fn=handle_deprovisioning_agent(wf))
    it.register("equipment_return_tracker", worker="equipment-return-tracker", fn=handle_equipment_return_tracker(wf))
    pay.register("final_pay_calculator", worker="final-pay-calculator", fn=handle_final_pay_calculator(wf))
    pay.register("final_settlement_opener", worker="final-pay-calculator", fn=handle_final_settlement_opener(wf))
    pay.register("direct_deposit_disburser", worker="direct-deposit-disburser",
                 fn=handle_direct_deposit_disburser(wf))
    return hr, it, pay


def test_exit_flow_v3_runs_end_to_end_with_every_step_on_its_own_worker_role(engine, exit_org, wf, exit_v3):
    tenant, employee = exit_org["tenant"], exit_org["employee"]
    founder_user, hr_user = exit_org["founder_user"], exit_org["hr_user"]
    with tenant_session(engine, "agent_hr", tenant) as conn:
        instance_id = start_exit(conn, wf, employee_id=employee, termination_type="voluntary",
                                 reason_code="resignation", notice_date=date(2026, 6, 1),
                                 last_working_day=date(2026, 6, 30), initiated_by_user_id=hr_user)
    assert _scalar(engine, tenant, "SELECT definition_version FROM app.workflow_instance WHERE id = :i",
                   {"i": instance_id}) == 3
    hr, it, pay = _workers(engine, wf)

    hr.tick(); hr.tick()                                                 # legal hold check, checklist
    assert instance_state(engine, tenant, instance_id).state == "s04_identity_account"
    it.tick()                                                            # requests g_it_deprov
    approval_id = _scalar(engine, tenant, "SELECT id FROM approval_request WHERE gate_type = 'g_it_deprov' "
                          "AND subject_id = :i", {"i": exit_org["identity_account"]})
    with tenant_session(engine, "tenant_hr", tenant, user_id=hr_user) as conn:
        resolve(conn, approval_id, "approved")
    with worker_session(engine, "deprovisioning-agent", tenant) as conn:
        deprovision_identity(conn, wf, instance_id, identity_account_id=exit_org["identity_account"],
                             approval_request_id=approval_id)
    it.tick()                                                            # device return
    pay.tick()                                                           # final_pay_calculator parks on g_finalpay
    state = instance_state(engine, tenant, instance_id)
    resolve_and_relay(engine, wf, tenant, "tenant_founder", founder_user, state.waiting_on_approval, "finalpay")
    pay.tick()                                                           # opens the settlement
    settlement_id = _scalar(engine, tenant, "SELECT id FROM final_settlement WHERE employee_id = :e", {"e": employee})
    pay.tick()                                                           # requests g_pay_disburse
    disburse_id = _scalar(engine, tenant, "SELECT id FROM approval_request WHERE gate_type = 'g_pay_disburse' "
                          "AND subject_id = :i", {"i": settlement_id})
    with tenant_session(engine, "tenant_founder", tenant, user_id=founder_user) as conn:
        resolve(conn, disburse_id, "approved")
    with worker_session(engine, "direct-deposit-disburser", tenant) as conn:
        disburse_final_settlement(conn, wf, instance_id, final_settlement_id=settlement_id,
                                  approval_request_id=disburse_id)
    assert instance_state(engine, tenant, instance_id).state == "s09_cobra"

    for expected in ("s10_vesting", "s11_rehire_flag", "s12_employee_closeout"):
        hr.tick()
        assert instance_state(engine, tenant, instance_id).state == expected
    hr.tick()
    assert instance_state(engine, tenant, instance_id).status == "completed"
    with engine.connect() as conn:
        is_active, date_of_exit = conn.execute(text("SELECT is_active, date_of_exit FROM employee WHERE id = :e"),
                                               {"e": employee}).one()
        rehire = conn.execute(text("SELECT rehire_eligible FROM termination WHERE employee_id = :e"),
                              {"e": employee}).scalar_one()
    assert (is_active, date_of_exit, rehire) == (False, date(2026, 6, 30), "eligible")


def test_the_old_combined_closeout_cannot_run_under_one_worker_role(engine, exit_org, wf):
    """Why the split exists: employee_closeout needs termination, employee and vesting access at once."""
    from daydor.exit.closeout import handle_employee_closeout
    tenant = exit_org["tenant"]
    with tenant_session(engine, "agent_hr", tenant) as conn:
        instance_id = start_exit(conn, wf, employee_id=exit_org["employee"], termination_type="voluntary",
                                 reason_code="resignation", notice_date=date(2026, 6, 1),
                                 last_working_day=date(2026, 6, 30), initiated_by_user_id=exit_org["hr_user"])
    w = Worker(engine, "hr", "w-old")
    w.register("employee_closeout", worker="employee-record-writer", fn=handle_employee_closeout(wf))
    with tenant_session(engine, "agent_hr", tenant) as conn:
        from daydor.queue import enqueue
        jid = enqueue(conn, "hr", "employee_closeout", {
            "workflow_instance_id": str(instance_id),
            "context": {"employee_id": str(exit_org["employee"]),
                        "termination_id": _scalar(engine, tenant, "SELECT subject_id FROM app.workflow_instance "
                                                  "WHERE id = :i", {"i": instance_id}).__str__()}})
    w.tick()
    with engine.connect() as conn:       # failed and queued for retry: nothing skipped silently
        row = conn.execute(text("SELECT status, last_error FROM app.job WHERE id = :j"), {"j": jid}).one()
    assert row.status == "queued" and "permission denied" in row.last_error
