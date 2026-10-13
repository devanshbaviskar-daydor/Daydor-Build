"""Payroll's own prerequisites (docs/sprint-plan.md Sprint 6): leave accrual, timecard capture
and manager approval (resolving finding 9 via the new g_timecard gate), and benefit elections.
None of this is part of a WorkflowEngine instance -- these are standalone, recurring operations
Payroll's own sprints will read from later."""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from daydor.benefits.election import elect_benefit
from daydor.agents.session import worker_session
from daydor.db.session import tenant_session
from daydor.gates.hard import resolve
from daydor.queue import Worker
from daydor.timekeeping.leave import accrue_leave
from daydor.timekeeping.punch import record_punch
from daydor.timekeeping.timecard import handle_timekeeping_gate_resolved, route_for_approval, \
    validate_timecard
from tests.factories import insert


@pytest.fixture
def leave_policy(engine, org):
    with engine.begin() as conn:
        return insert(conn, "leave_policy", tenant_id=org.tenant_a, legal_entity_id=org.legal_entity_a,
                     leave_type="annual", accrual_rule='{"days_per_month": 1.5}', carry_forward_cap="18")


@pytest.fixture
def benefit_plan(engine, org):
    with engine.begin() as conn:
        return insert(conn, "benefit_plan", tenant_id=org.tenant_a, legal_entity_id=org.legal_entity_a,
                     plan_type="health", carrier="Acme Health", plan_year=2026, employer_contribution="5000")


def test_leave_accrues_linearly_from_date_of_joining_capped_at_policy(engine, org, leave_policy):
    tenant = org.tenant_a
    with worker_session(engine, "pto-accrual-calculator", tenant) as conn:
        balance_id = accrue_leave(conn, employee_id=org.emp["report"], leave_policy_id=leave_policy,
                                  as_of=date(2026, 7, 17))  # hired 2026-01-01 (org fixture) -> 6 months
    with tenant_session(engine, "tenant_hr", tenant) as conn:
        row = conn.execute(text("SELECT balance_days FROM leave_balance WHERE id = :i"),
                           {"i": balance_id}).one()
    assert row.balance_days == Decimal("9.0")  # 6 months * 1.5

    # Recomputing (e.g. a later run) updates the same row rather than appending a new one.
    with worker_session(engine, "pto-accrual-calculator", tenant) as conn:
        again = accrue_leave(conn, employee_id=org.emp["report"], leave_policy_id=leave_policy,
                             as_of=date(2027, 7, 17))  # 18 months -> would be 27, capped at 18
    assert again == balance_id
    with tenant_session(engine, "tenant_hr", tenant) as conn:
        capped = conn.execute(text("SELECT balance_days FROM leave_balance WHERE id = :i"),
                              {"i": balance_id}).scalar_one()
    assert capped == Decimal("18")


def test_timecard_requires_manager_approval_via_g_timecard(engine, org):
    """Resolves finding 9: punches validate into a timecard pending approval, and only a real
    g_timecard gate resolution (by tenant_manager) flips it to approved -- not a bypass."""
    tenant = org.tenant_a
    employee_id = org.emp["report"]
    period_start, period_end = date(2026, 8, 3), date(2026, 8, 9)

    with tenant_session(engine, "tenant_employee", tenant, employee_id=employee_id) as conn:
        record_punch(conn, employee_id=employee_id,
                    punched_at=datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc), kind="in")
        record_punch(conn, employee_id=employee_id,
                    punched_at=datetime(2026, 8, 3, 18, 0, tzinfo=timezone.utc), kind="out")

    with worker_session(engine, "punch-validator", tenant) as conn:
        timecard_id = validate_timecard(conn, employee_id=employee_id, period_start=period_start,
                                        period_end=period_end)

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        card = conn.execute(text("SELECT status, regular_hours, overtime_hours FROM timecard WHERE id = :t"),
                            {"t": timecard_id}).one()
    assert card.status == "pending_approval"
    assert card.regular_hours == Decimal("9.000000")
    assert card.overtime_hours == Decimal("0")

    with worker_session(engine, "timecard-approval-router", tenant) as conn:
        approval_id = route_for_approval(conn, timecard_id=timecard_id)

    # The employee cannot approve their own timecard.
    with pytest.raises(DBAPIError, match="cannot resolve gate g_timecard"):
        with tenant_session(engine, "tenant_employee", tenant, employee_id=employee_id) as conn:
            resolve(conn, approval_id, "approved")

    with tenant_session(engine, "tenant_manager", tenant, user_id=org.user["manager"]) as conn:
        assert resolve(conn, approval_id, "approved") == "approved"

    # The 'timekeeping' queue is subscribed to every gate.resolved event, not just g_timecard
    # ones (see migrations/sql/0019_timecard_gates.sql) -- in a full test run it inherits a large
    # backlog of no-op jobs from every other sprint's gate resolutions, more than one tick's
    # batch can drain. A real worker just keeps ticking; so does this test.
    worker = Worker(engine, "timekeeping", "w-timekeeping", batch=50)
    worker.register("timekeeping.gate_resolved", worker="timecard-approval-router", fn=handle_timekeeping_gate_resolved)
    for _ in range(20):
        worker.tick()
        with tenant_session(engine, "tenant_hr", tenant) as conn:
            status = conn.execute(text("SELECT status FROM timecard WHERE id = :t"),
                                  {"t": timecard_id}).scalar_one()
        if status != "pending_approval":
            break

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        final = conn.execute(text("SELECT status, approved_by_user_id FROM timecard WHERE id = :t"),
                             {"t": timecard_id}).one()
    assert final.status == "approved"
    assert final.approved_by_user_id == org.user["manager"]


def test_benefit_election_is_processed_by_an_agent_not_the_employee_directly(engine, org, benefit_plan):
    """coverage_tier/employee_cost are C2 (HR/ops/agent WRITE, employee READ only) despite the
    table's own summary grant showing employee WRITE -- election-processor (an agent), not the
    employee's own session, is what actually writes the row."""
    tenant = org.tenant_a
    employee_id = org.emp["peer"]

    with pytest.raises(DBAPIError, match="permission denied"):
        with tenant_session(engine, "tenant_employee", tenant, employee_id=employee_id) as conn:
            elect_benefit(conn, employee_id=employee_id, benefit_plan_id=benefit_plan,
                          coverage_tier="employee_only", employee_cost=Decimal("500"),
                          effective_from=date(2026, 3, 1))

    with worker_session(engine, "election-processor", tenant) as conn:
        a = elect_benefit(conn, employee_id=employee_id, benefit_plan_id=benefit_plan,
                          coverage_tier="employee_only", employee_cost=Decimal("500"),
                          effective_from=date(2026, 3, 1))
        b = elect_benefit(conn, employee_id=employee_id, benefit_plan_id=benefit_plan,
                          coverage_tier="employee_only", employee_cost=Decimal("500"),
                          effective_from=date(2026, 3, 1))
    assert a == b

    with tenant_session(engine, "tenant_employee", tenant, employee_id=employee_id) as conn:
        mine = conn.execute(text("SELECT coverage_tier FROM benefit_election WHERE id = :i"),
                            {"i": a}).scalar_one()
    assert mine == "employee_only"  # the employee can read their own election
