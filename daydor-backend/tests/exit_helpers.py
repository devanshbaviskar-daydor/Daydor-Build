"""Shared driving helpers for the exit-flow tests (tests/test_exit_*.py). Not a test module
itself -- no test_ prefix, so pytest does not collect it."""
from __future__ import annotations

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
from daydor.exit.deprovisioning import handle_deprovisioning_agent
from daydor.exit.device_return import handle_equipment_return_tracker
from daydor.exit.final_settlement import (handle_direct_deposit_disburser, handle_final_pay_calculator,
                                          handle_final_settlement_opener)
from daydor.exit.legal_hold import handle_legal_hold_checker
from daydor.queue import Worker
from daydor.timekeeping.leave import accrue_leave
from tests.factories import insert
from tests.hire_helpers import resolve_and_relay  # noqa: F401 -- reused directly, generic across flows


@pytest.fixture
def exit_org(engine):
    """A tenant of its own: one already-employed, already-provisioned employee ready to be
    terminated, so exit-flow tests don't have to drive the whole hire flow first."""
    with engine.begin() as conn:
        tenant = insert(conn, "tenant", legal_name="Exit Co", status="active")
        le = insert(conn, "legal_entity", tenant_id=tenant, name="Exit Co Pvt Ltd", country_code="IN")
        dept = insert(conn, "department", tenant_id=tenant, name="Engineering")
        loc = insert(conn, "location", tenant_id=tenant, name="Bengaluru", country_code="IN",
                    state_code="KA", legal_entity_id=le)
        job_profile = insert(conn, "job_profile", tenant_id=tenant, title="Engineer",
                             job_family="Engineering", level="L3", flsa_default="exempt",
                             description="Builds things")
        employee = insert(conn, "employee", tenant_id=tenant, full_name="Departing Employee",
                          legal_entity_id=le, department_id=dept, location_id=loc,
                          hire_event_id=f"hire-{uuid.uuid4().hex[:10]}", date_of_joining="2024-01-01")
        insert(conn, "employment_record", tenant_id=tenant, employee_id=employee,
              effective_from="2024-01-01", job_profile_id=job_profile, fte="1.0",
              ctc_annual="1200000", basic_da_monthly="50000", tax_regime_election="new",
              flsa_status="exempt")
        identity_account = insert(conn, "identity_account", tenant_id=tenant, employee_id=employee,
                                  directory_provider="fake-idp", external_id=f"ext-{uuid.uuid4().hex[:8]}",
                                  status="active", provisioned_at="2024-01-02")
        insert(conn, "app_access_grant", tenant_id=tenant, identity_account_id=identity_account,
              app_name="email", permission_level="standard", source="template", granted_at="2024-01-02")
        device = insert(conn, "device", tenant_id=tenant, asset_tag=f"AT-{uuid.uuid4().hex[:6]}",
                        model="Laptop", serial_no=uuid.uuid4().hex[:10], status="assigned",
                        purchase_cost="80000")
        insert(conn, "device_assignment", tenant_id=tenant, device_id=device, employee_id=employee,
              assigned_at="2024-01-02")
        leave_policy = insert(conn, "leave_policy", tenant_id=tenant, legal_entity_id=le,
                              leave_type="earned", accrual_rule='{"days_per_month": 1.5}',
                              carry_forward_cap="45")
        insert(conn, "gratuity_accrual_balance", tenant_id=tenant, employee_id=employee,
              as_of_period="2026-06-30", accrued_amount="50000", gratuity_wage_base="50000")
        founder_user = insert(conn, "app_user", tenant_id=tenant, role="founder")
        hr_user = insert(conn, "app_user", tenant_id=tenant, role="hr")
    with worker_session(engine, "pto-accrual-calculator", tenant) as conn:
        accrue_leave(conn, employee_id=employee, leave_policy_id=leave_policy, as_of=date(2026, 6, 1))
    return {"tenant": tenant, "legal_entity": le, "department": dept, "location": loc,
           "job_profile": job_profile, "employee": employee, "identity_account": identity_account,
           "device": device, "leave_policy": leave_policy, "founder_user": founder_user,
           "hr_user": hr_user}


def hr_worker(engine, wf, name="w-exit-hr"):
    w = Worker(engine, "hr", name)
    w.register("legal_hold_checker", worker="root-orchestrator", fn=handle_legal_hold_checker(wf))
    w.register("termination_checklist_builder", worker="termination-checklist-builder", fn=handle_termination_checklist_builder(wf))
    w.register("cobra_trigger_detector", worker="cobra-trigger-detector", fn=handle_cobra_trigger_detector(wf))
    w.register("vesting_schedule_tracker", worker="vesting-schedule-tracker", fn=handle_vesting_schedule_tracker(wf))
    w.register("rehire_eligibility_flagger", worker="rehire-eligibility-flagger", fn=handle_rehire_eligibility_flagger(wf))
    w.register("employee_record_writer_closeout", worker="employee-record-writer", fn=handle_employee_record_writer_closeout(wf))
    return w


def it_worker(engine, wf, name="w-exit-it"):
    w = Worker(engine, "it", name)
    w.register("deprovisioning_agent", worker="deprovisioning-agent", fn=handle_deprovisioning_agent(wf))
    w.register("equipment_return_tracker", worker="equipment-return-tracker", fn=handle_equipment_return_tracker(wf))
    return w


def pay_worker(engine, wf, name="w-exit-pay"):
    w = Worker(engine, "pay", name)
    w.register("final_pay_calculator", worker="final-pay-calculator", fn=handle_final_pay_calculator(wf))
    w.register("final_settlement_opener", worker="final-pay-calculator", fn=handle_final_settlement_opener(wf))
    w.register("direct_deposit_disburser", worker="direct-deposit-disburser", fn=handle_direct_deposit_disburser(wf))
    return w


def instance_state(engine, tenant, instance_id):
    with tenant_session(engine, "tenant_hr", tenant) as conn:
        return conn.execute(
            text("SELECT state, status, waiting_on_approval FROM app.workflow_instance WHERE id = :i"),
            {"i": instance_id}).one()
