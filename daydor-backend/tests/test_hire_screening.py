"""Hire flow steps 5-8 (application -> screening -> interview -> offer), driven end to end
through the real WorkflowEngine + queue, using version 3+ of 'hire'
(see migrations/sql/0015_hire_workflow_v3.sql)."""
from datetime import date
from decimal import Decimal

from sqlalchemy import text

from daydor.agents.session import worker_session
from daydor.db.session import tenant_session
from daydor.hire.requisition import open_requisition
from daydor.hire.screening import intake_application
from daydor.workflow.engine import WorkflowEngine
from tests.hire_helpers import comp_band, drive_to_offer, drive_to_screening_result, resolve_and_relay  # noqa: F401


def test_application_intake_is_idempotent_per_requisition_and_email(engine, hire_org):
    tenant = hire_org["tenant"]
    with worker_session(engine, "hire-intake", tenant) as conn:
        req_id = open_requisition(conn, position_id=hire_org["position"],
                                  hiring_manager_id=hire_org["hiring_manager"],
                                  target_start_date=date(2026, 3, 1))
    with worker_session(engine, "candidate-screener", tenant) as conn:
        a = intake_application(conn, requisition_id=req_id, full_name="Jordan Candidate",
                               email="dup@example.test", phone="555-0101", resume_ref="r1", source="referral")
        b = intake_application(conn, requisition_id=req_id, full_name="Jordan Candidate",
                               email="dup@example.test", phone="555-0101", resume_ref="r1", source="referral")
    assert a == b


def test_screening_requires_aedt_signoff_before_interview(engine, hire_org, comp_band):
    tenant = hire_org["tenant"]
    wf = WorkflowEngine()
    instance_id, requisition_id, _ = drive_to_screening_result(
        engine, hire_org, wf, comp_band_id=comp_band, proposed_base="1200000", worker_name="w-aedt")

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        instance = conn.execute(text("SELECT state, status, waiting_on_approval FROM app.workflow_instance "
                                     "WHERE id = :i"), {"i": instance_id}).one()
        screened = conn.execute(text("SELECT count(*) FROM screening_result sr JOIN application a "
                                     "ON a.id = sr.application_id WHERE a.requisition_id = :r"),
                                {"r": requisition_id}).scalar_one()
    assert instance.state == "s06_screening_result"
    assert instance.status == "waiting_gate"
    assert instance.waiting_on_approval is not None
    assert screened == 1


def test_offer_within_band_needs_no_extra_gate(engine, hire_org, comp_band):
    wf = WorkflowEngine()
    instance_id, requisition_id, _, instance = drive_to_offer(
        engine, hire_org, wf, comp_band_id=comp_band, proposed_base="1200000", worker_name="w-inband")
    # No g_offer_band gate needed: the instance keeps running straight into background_check
    # (steps 9+, Sprint 3) instead of stopping here.
    assert instance.status == "running"

    with tenant_session(engine, "tenant_hr", hire_org["tenant"]) as conn:
        offer = conn.execute(text("SELECT within_band, proposed_base FROM offer o "
                                  "JOIN application a ON a.id = o.application_id "
                                  "WHERE a.requisition_id = :r"), {"r": requisition_id}).one()
    assert offer.within_band is True
    assert offer.proposed_base == Decimal("1200000")


def test_offer_outside_band_requires_founder_approval(engine, hire_org, comp_band):
    wf = WorkflowEngine()
    instance_id, requisition_id, _, instance = drive_to_offer(
        engine, hire_org, wf, comp_band_id=comp_band, proposed_base="2000000", worker_name="w-outband")
    assert instance.status == "waiting_gate"
    assert instance.waiting_on_approval is not None

    with tenant_session(engine, "tenant_hr", hire_org["tenant"]) as conn:
        offer = conn.execute(text("SELECT within_band FROM offer o JOIN application a "
                                  "ON a.id = o.application_id WHERE a.requisition_id = :r"),
                             {"r": requisition_id}).one()
    assert offer.within_band is False

    resolve_and_relay(engine, wf, hire_org["tenant"], "tenant_founder", hire_org["founder_user"],
                     instance.waiting_on_approval, "offerband")
    with tenant_session(engine, "tenant_hr", hire_org["tenant"]) as conn:
        final_status = conn.execute(text("SELECT status FROM app.workflow_instance WHERE id = :i"),
                                    {"i": instance_id}).scalar_one()
    assert final_status == "running"  # continues into background_check (Sprint 3), not terminal
