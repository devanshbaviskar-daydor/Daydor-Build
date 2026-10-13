"""Hire flow steps 1-4 (position check -> requisition -> budget approval -> job posting), driven
end to end through the real WorkflowEngine + queue, using the hand-written definition in
daydor.hire.workflow (version 2 of 'hire', see migrations/sql/0014_hire_workflow.sql)."""
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from daydor.agents.session import worker_session
from daydor.db.session import tenant_session
from daydor.gates.hard import resolve
from daydor.hire.posting import handle_job_posting_publisher
from daydor.hire.requisition import NoVacantPosition, confirm_budgeted_seat, open_requisition
from daydor.hire.workflow import start_hire
from daydor.queue import Worker
from daydor.workflow.engine import WorkflowEngine, gate_resolved_handler
from tests.factories import insert
from tests.hire_helpers import drive_to_job_posting


def test_confirm_budgeted_seat_rejects_filled_or_missing_position(engine, hire_org):
    tenant = hire_org["tenant"]
    with worker_session(engine, "hire-intake", tenant) as conn:
        with pytest.raises(NoVacantPosition):
            confirm_budgeted_seat(conn, uuid.uuid4())

    with engine.begin() as conn:
        filled = insert(conn, "position", tenant_id=tenant, department_id=hire_org["department"],
                        job_profile_id=hire_org["job_profile"], status="open", budgeted_fte="1.0",
                        budgeted_cost="1000000", opened_at="2026-01-01",
                        current_employee_id=hire_org["hiring_manager"])
    with worker_session(engine, "hire-intake", tenant) as conn:
        with pytest.raises(NoVacantPosition):
            confirm_budgeted_seat(conn, filled)


def test_confirm_budgeted_seat_accepts_open_vacant_position(engine, hire_org):
    with worker_session(engine, "hire-intake", hire_org["tenant"]) as conn:
        confirm_budgeted_seat(conn, hire_org["position"])  # does not raise


def test_open_requisition_is_idempotent_per_position(engine, hire_org):
    tenant = hire_org["tenant"]
    with worker_session(engine, "hire-intake", tenant) as conn:
        a = open_requisition(conn, position_id=hire_org["position"],
                             hiring_manager_id=hire_org["hiring_manager"],
                             target_start_date=date(2026, 3, 1))
        b = open_requisition(conn, position_id=hire_org["position"],
                             hiring_manager_id=hire_org["hiring_manager"],
                             target_start_date=date(2026, 3, 1))
    assert a == b


def test_start_hire_replay_returns_existing_instance_without_advancing_it(engine, hire_org):
    tenant = hire_org["tenant"]
    wf = WorkflowEngine()
    instance_id, _, approval_id = drive_to_job_posting(engine, hire_org, wf)  # parked on g_requisition_budget

    with worker_session(engine, "hire-intake", tenant) as conn:
        again = start_hire(conn, wf, position_id=hire_org["position"],
                           hiring_manager_id=hire_org["hiring_manager"],
                           target_start_date=date(2026, 3, 1), channel="company_site",
                           pay_range_min="1000000", pay_range_max="1500000")
        inst = conn.execute(text("SELECT state, status, waiting_on_approval FROM app.workflow_instance "
                                 "WHERE id = :i"), {"i": instance_id}).one()
        moves = conn.execute(text("SELECT count(*) FROM app.workflow_transition WHERE instance_id = :i"),
                             {"i": instance_id}).scalar_one()
    assert again == instance_id
    assert (inst.state, inst.status, inst.waiting_on_approval) == ("s03_approval_request", "waiting_gate",
                                                                    approval_id)
    assert moves == 4  # three startup advances + the router's park; the replay added none


def test_hire_requisition_flow_to_job_posting(engine, hire_org):
    """start_hire -> budget gate parks the instance -> founder approves -> posting publishes."""
    tenant = hire_org["tenant"]
    wf = WorkflowEngine()
    instance_id, requisition_id, approval_id = drive_to_job_posting(engine, hire_org, wf)
    assert approval_id is not None

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        requisition = conn.execute(text("SELECT status, position_id FROM job_requisition WHERE id = :r"),
                                   {"r": requisition_id}).one()
    assert requisition.status == "draft"
    assert requisition.position_id == hire_org["position"]

    # A different user than whoever raised it resolves it (maker-checker); here it was
    # agent-raised, so any founder may approve.
    with tenant_session(engine, "tenant_founder", tenant, user_id=hire_org["founder_user"]) as conn:
        assert resolve(conn, approval_id, "approved") == "approved"

    # The "workflow" queue and "workflow.gate_resolved" kind are shared platform-wide (every gate
    # resolution across every test in this session relays through it), so other tests' pending
    # jobs may also be claimed and succeed in this tick; only this instance's own progress matters.
    workflow_worker = Worker(engine, "workflow", "w-workflow")
    workflow_worker.register("workflow.gate_resolved", worker="workflow-engine", fn=gate_resolved_handler(wf))
    assert workflow_worker.tick()["succeeded"] >= 1

    ta_worker = Worker(engine, "ta", "w-ta")
    ta_worker.register("job_posting_publisher", worker="job-posting-publisher", fn=handle_job_posting_publisher())
    assert ta_worker.tick()["succeeded"] == 1

    # job_posting_publisher does not auto-advance: s04_job_posting is a genuine parked state,
    # waiting for a real candidate to apply (daydor.hire.screening.submit_application).
    with tenant_session(engine, "tenant_hr", tenant) as conn:
        instance = conn.execute(text("SELECT state, status FROM app.workflow_instance WHERE id = :i"),
                                {"i": instance_id}).one()
        posting = conn.execute(text("SELECT channel, pay_range_min, pay_range_max, posted_at "
                                    "FROM job_posting WHERE requisition_id = :r"),
                               {"r": requisition_id}).one()
    assert instance.state == "s04_job_posting"
    assert instance.status == "running"
    assert posting.channel == "company_site"
    assert posting.pay_range_min == Decimal("1000000")
    assert posting.posted_at is not None


def test_budget_gate_blocks_job_posting_until_approved(engine, hire_org):
    """Without resolving the gate, the posting step never runs."""
    wf = WorkflowEngine()
    _, requisition_id, _ = drive_to_job_posting(engine, hire_org, wf)
    with tenant_session(engine, "tenant_hr", hire_org["tenant"]) as conn:
        posted = conn.execute(text("SELECT count(*) FROM job_posting WHERE requisition_id = :r"),
                              {"r": requisition_id}).scalar_one()
    assert posted == 0
