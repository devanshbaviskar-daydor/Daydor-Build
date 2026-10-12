"""Shared driving helpers for the hire-flow tests (tests/test_hire_*.py). Not a test module
itself -- no test_ prefix, so pytest does not collect it."""
from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import text

from daydor.db.session import tenant_session
from daydor.gates.hard import resolve
from daydor.hire.approvals import handle_requisition_approval_router
from daydor.hire.interview import handle_interview_scheduler
from daydor.hire.offer import handle_offer_letter_generator
from daydor.hire.posting import handle_job_posting_publisher
from daydor.hire.screening import handle_candidate_screener_assess, handle_candidate_screener_intake, \
    submit_application
from daydor.hire.workflow import start_hire
from daydor.queue import Worker
from daydor.workflow.engine import WorkflowEngine, gate_resolved_handler
from tests.factories import insert

# Scope simplification (see daydor.hire.interview / daydor.hire.offer docstrings): there is no
# calendar or comp-negotiation engine, so interview timing is decided up front, at start_hire()
# time, rather than computed by the step that actually uses it later.
SCHEDULED_AT = datetime(2026, 2, 10, 10, 0).isoformat()


@pytest.fixture
def comp_band(engine, hire_org):
    with engine.begin() as conn:
        return insert(conn, "comp_band", tenant_id=hire_org["tenant"], job_profile_id=hire_org["job_profile"],
                     currency="INR", band_min="1000000", band_mid="1250000", band_max="1500000",
                     effective_from="2026-01-01")


@pytest.fixture
def access_role_template(engine, hire_org):
    """Admin-entered reference data (IT admin writes it directly; see docs/sprint-plan.md's
    "Reference & admin-owned data" note)."""
    import json
    with engine.begin() as conn:
        return insert(conn, "access_role_template", tenant_id=hire_org["tenant"],
                     job_profile_id=hire_org["job_profile"],
                     app_bundle=json.dumps([{"app_name": "email", "permission_level": "standard"},
                                            {"app_name": "code-repo", "permission_level": "standard"}]))


@pytest.fixture
def retention_policy(engine):
    """Global reference data (daydor_admin-maintained, like statutory_rate_rule); seeded directly
    for tests the same way other admin-only reference tables are (see docs/sprint-plan.md's
    "Reference & admin-owned data" note). retention_class is unique cluster-wide, so each test
    gets its own."""
    import uuid
    with engine.begin() as conn:
        return insert(conn, "retention_policy", retention_class=f"new_hire_docs-{uuid.uuid4().hex[:8]}",
                     record_type="document", duration_months=84, anchor_field="created_at",
                     legal_basis="contract", jurisdiction="IN")


# New-hire personal details needed from step 10 (employee creation) onward. A real system collects
# these at offer acceptance; this prototype has no such step, so they ride in context from the
# start (see daydor.hire.employee_record's module docstring).
NEW_HIRE_CONTEXT = {
    "legal_entity_id": None,  # filled in per-test from hire_org["legal_entity"]
    "state_code": "KA",
    "date_of_birth": "1995-04-12",
    "personal_address": "1 MG Road, Bengaluru",
    "aadhaar_last4": "1234",
    "employment_type": "full_time",
    "basic_da_monthly": "50000",
    "tax_regime_election": "new",
    # payroll_profile inputs (step 18)
    "pay_frequency": "monthly",
    "payment_method": "bank_transfer",
    "work_state": "KA",
    "tax_state": "KA",
    "uan_number": "123456789012",
}


def drive_to_job_posting(engine, hire_org, wf: WorkflowEngine, **extra_context):
    """start_hire() through the budget gate; returns (instance_id, requisition_id, approval_id).
    The instance is left parked in waiting_gate on g_requisition_budget."""
    tenant = hire_org["tenant"]
    context = {"channel": "company_site", "pay_range_min": "1000000", "pay_range_max": "1500000",
              **extra_context}
    with tenant_session(engine, "agent_ta", tenant) as conn:
        instance_id = start_hire(conn, wf, position_id=hire_org["position"],
                                 hiring_manager_id=hire_org["hiring_manager"],
                                 target_start_date=date(2026, 3, 1), **context)
        requisition_id = conn.execute(
            text("SELECT subject_id FROM app.workflow_instance WHERE id = :i"),
            {"i": instance_id}).scalar_one()

    router_worker = Worker(engine, "platform", "w-platform-helper")
    router_worker.register("requisition_approval_router", role="agent_ro",
                           fn=handle_requisition_approval_router(wf))
    router_worker.tick()

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        instance = conn.execute(text("SELECT status, waiting_on_approval FROM app.workflow_instance "
                                     "WHERE id = :i"), {"i": instance_id}).one()
    assert instance.status == "waiting_gate"
    return instance_id, requisition_id, instance.waiting_on_approval


def resolve_and_relay(engine, wf, tenant, role, user_id, approval_id, worker_suffix):
    """Resolve a parked hard gate as `role`, then relay+run the workflow's own
    gate.resolved handler so the instance actually advances (or follows on_reject)."""
    with tenant_session(engine, role, tenant, user_id=user_id) as conn:
        assert resolve(conn, approval_id, "approved") == "approved"
    workflow_worker = Worker(engine, "workflow", f"w-workflow-{worker_suffix}")
    workflow_worker.register("workflow.gate_resolved", role="agent_ro", fn=gate_resolved_handler(wf))
    workflow_worker.tick()


def ta_worker(engine, wf, name="w-ta", bg_outcome="clear"):
    """A Worker on the 'ta' queue with every hire-flow 'ta' handler registered (steps 4-9).
    `bg_outcome` controls the fake background-check adapter's result ("clear" or "adverse")."""
    from daydor.adapters.background_check import FakeBackgroundCheckAdapter
    from daydor.hire.background_check import handle_background_check_initiator
    w = Worker(engine, "ta", name)
    w.register("job_posting_publisher", role="agent_ta", fn=handle_job_posting_publisher())
    w.register("candidate_screener_intake", role="agent_ta", fn=handle_candidate_screener_intake(wf))
    w.register("candidate_screener_assess", role="agent_ta", fn=handle_candidate_screener_assess(wf))
    w.register("interview_scheduler", role="agent_ta", fn=handle_interview_scheduler(wf))
    w.register("offer_letter_generator", role="agent_ta", fn=handle_offer_letter_generator(wf))
    w.register("background_check_initiator", role="agent_ta",
               fn=handle_background_check_initiator(wf, FakeBackgroundCheckAdapter(outcome=bg_outcome)))
    return w


def drive_to_screening_result(engine, hire_org, wf, *, comp_band_id, proposed_base, worker_name="w-ta",
                              bg_outcome="clear", **extra_context):
    """requisition -> budget-approved -> posted -> candidate applied -> screened (parked on
    g_aedt). Returns (instance_id, requisition_id, ta_worker)."""
    tenant = hire_org["tenant"]
    instance_id, requisition_id, budget_approval_id = drive_to_job_posting(
        engine, hire_org, wf, comp_band_id=str(comp_band_id), proposed_base=proposed_base,
        interviewer_employee_id=str(hire_org["hiring_manager"]), scheduled_at=SCHEDULED_AT, **extra_context)
    resolve_and_relay(engine, wf, tenant, "tenant_founder", hire_org["founder_user"], budget_approval_id,
                     f"{worker_name}-budget")

    worker = ta_worker(engine, wf, worker_name, bg_outcome=bg_outcome)
    worker.tick()  # job_posting_publisher

    with tenant_session(engine, "agent_ta", tenant) as conn:
        submit_application(conn, wf, instance_id, full_name="Jordan Candidate",
                           email=f"{worker_name}@example.test", phone="555-0100", resume_ref="resume-1",
                           source="referral")
    worker.tick()  # candidate_screener_intake
    worker.tick()  # candidate_screener_assess
    return instance_id, requisition_id, worker


def drive_to_offer(engine, hire_org, wf, *, comp_band_id, proposed_base, worker_name="w-ta",
                   bg_outcome="clear", **extra_context):
    """Continues drive_to_screening_result through AEDT sign-off, interview, and offer.
    Returns (instance_id, requisition_id, ta_worker, final_instance_row)."""
    tenant = hire_org["tenant"]
    instance_id, requisition_id, worker = drive_to_screening_result(
        engine, hire_org, wf, comp_band_id=comp_band_id, proposed_base=proposed_base, worker_name=worker_name,
        bg_outcome=bg_outcome, **extra_context)

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        aedt_approval_id = conn.execute(text("SELECT waiting_on_approval FROM app.workflow_instance "
                                             "WHERE id = :i"), {"i": instance_id}).scalar_one()
    assert aedt_approval_id is not None
    resolve_and_relay(engine, wf, tenant, "tenant_hr", hire_org["hr_user"], aedt_approval_id,
                     f"{worker_name}-aedt")

    worker.tick()  # interview_scheduler
    worker.tick()  # offer_letter_generator

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        instance = conn.execute(text("SELECT state, status, waiting_on_approval FROM app.workflow_instance "
                                     "WHERE id = :i"), {"i": instance_id}).one()
    return instance_id, requisition_id, worker, instance


def hr_worker(engine, wf, name="w-hr"):
    """A Worker on the 'hr' queue with the hire-flow's 'hr' handlers (steps 10-11, 14)."""
    from daydor.hire.employee_record import handle_employee_record_writer_create, \
        handle_employee_record_writer_open
    from daydor.hire.work_authorization import handle_i9_e_verify_initiator
    w = Worker(engine, "hr", name)
    w.register("employee_record_writer_create", role="agent_hr", fn=handle_employee_record_writer_create(wf))
    w.register("employee_record_writer_open", role="agent_hr", fn=handle_employee_record_writer_open(wf))
    w.register("i9_e_verify_initiator", role="agent_hr", fn=handle_i9_e_verify_initiator(wf))
    return w


def priv_worker(engine, wf, name="w-priv"):
    from daydor.hire.documents import handle_new_hire_doc_collector
    w = Worker(engine, "privacy", name)
    w.register("new_hire_doc_collector", role="agent_priv", fn=handle_new_hire_doc_collector(wf))
    return w


def ob_worker(engine, wf, name="w-ob"):
    from daydor.hire.checklist import handle_onboarding_checklist_builder
    w = Worker(engine, "ob", name)
    w.register("onboarding_checklist_builder", role="agent_ob", fn=handle_onboarding_checklist_builder(wf))
    return w


def it_worker(engine, wf, name="w-it"):
    from daydor.hire.access_grant import handle_app_access_granter
    from daydor.hire.identity import handle_sso_identity_provisioner
    w = Worker(engine, "it", name)
    w.register("sso_identity_provisioner", role="agent_it", fn=handle_sso_identity_provisioner(wf))
    w.register("app_access_granter", role="agent_it", fn=handle_app_access_granter(wf))
    return w


def pay_worker(engine, wf, name="w-pay"):
    from daydor.hire.employee_record import handle_employee_record_writer_payroll
    w = Worker(engine, "pay", name)
    w.register("employee_record_writer_payroll", role="agent_pay",
               fn=handle_employee_record_writer_payroll(wf))
    return w


def drive_to_consent_gate(engine, hire_org, wf, *, comp_band_id, retention_class_id, proposed_base="1200000",
                          worker_name="w-ta", bg_outcome="clear", legal_entity_id=None, extra_access=None):
    """Continues drive_to_offer (assuming an in-band offer, so no extra founder approval) through
    background check, employee/employment_record creation, parking on the dpdp_consent gate.
    Returns (instance_id, requisition_id, employee_id, instance_row_at_consent_gate)."""
    tenant = hire_org["tenant"]
    context = {**NEW_HIRE_CONTEXT, "legal_entity_id": str(legal_entity_id or hire_org["legal_entity"]),
              "location_id": str(hire_org["location"]), "retention_class_id": str(retention_class_id)}
    if extra_access is not None:
        context["extra_access"] = extra_access
    instance_id, requisition_id, worker, instance = drive_to_offer(
        engine, hire_org, wf, comp_band_id=comp_band_id, proposed_base=proposed_base, worker_name=worker_name,
        bg_outcome=bg_outcome, **context)
    assert instance.status == "running"  # proposed_base is in-band: no g_offer_band pause

    worker.tick()  # background_check_initiator

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        instance = conn.execute(text("SELECT state, status, waiting_on_approval FROM app.workflow_instance "
                                     "WHERE id = :i"), {"i": instance_id}).one()
    if instance.status == "waiting_gate":   # g_bg_adverse: only when bg_outcome == "adverse"
        resolve_and_relay(engine, wf, tenant, "tenant_hr", hire_org["hr_user"], instance.waiting_on_approval,
                         f"{worker_name}-bgadverse")

    worker_hr = hr_worker(engine, wf, worker_name.replace("ta", "hr"))
    worker_hr.tick()  # employee_record_writer_create
    worker_hr.tick()  # employee_record_writer_open -> enters s12_consent_record (no enter_jobs)

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        employee_id = conn.execute(text("SELECT (context->>'employee_id')::uuid FROM app.workflow_instance "
                                        "WHERE id = :i"), {"i": instance_id}).scalar_one()

    # consent_record has no agent writer (daydor.hire.consent's docstring); request_consent is
    # the explicit trigger that checks the dpdp_consent gate once the employee has done their part.
    from daydor.hire.consent import request_consent
    with tenant_session(engine, "agent_hr", tenant) as conn:
        request_consent(conn, wf, instance_id)

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        instance = conn.execute(text("SELECT state, status, waiting_on_approval FROM app.workflow_instance "
                                     "WHERE id = :i"), {"i": instance_id}).one()
    return instance_id, requisition_id, employee_id, instance


def grant_consent_and_clear_gate(engine, hire_org, wf, *, employee_id, instance_id, approval_id,
                                 data_category="pan", worker_suffix="consent"):
    """Grants one consent_record (direct table write, like a real new hire would) and resolves
    the dpdp_consent gate as that same employee."""
    tenant = hire_org["tenant"]
    with engine.begin() as conn:
        insert(conn, "consent_record", tenant_id=tenant, employee_id=employee_id, data_category=data_category,
              purpose="identity_verification", status="granted", granted_at="2026-02-20",
              consent_artifact_ref=f"doc-{worker_suffix}")
        new_hire_user = insert(conn, "app_user", tenant_id=tenant, role="employee", employee_id=employee_id)
    resolve_and_relay(engine, wf, tenant, "tenant_employee", new_hire_user, approval_id, worker_suffix)


def drive_to_identity(engine, hire_org, wf, *, comp_band_id, retention_class_id, proposed_base="1200000",
                      worker_name="w-ta", bg_outcome="clear", legal_entity_id=None, extra_access=None):
    """Continues drive_to_consent_gate through consent, documents, work authorization, the
    onboarding checklist and identity provisioning. Returns (instance_id, requisition_id,
    employee_id, final_instance_row)."""
    tenant = hire_org["tenant"]
    instance_id, requisition_id, employee_id, instance = drive_to_consent_gate(
        engine, hire_org, wf, comp_band_id=comp_band_id, retention_class_id=retention_class_id,
        proposed_base=proposed_base, worker_name=worker_name, bg_outcome=bg_outcome,
        legal_entity_id=legal_entity_id, extra_access=extra_access)
    assert instance.status == "waiting_gate"

    grant_consent_and_clear_gate(engine, hire_org, wf, employee_id=employee_id, instance_id=instance_id,
                                 approval_id=instance.waiting_on_approval,
                                 worker_suffix=f"{worker_name}-consent")

    priv = priv_worker(engine, wf, worker_name.replace("ta", "priv"))
    priv.tick()  # new_hire_doc_collector

    hr = hr_worker(engine, wf, worker_name.replace("ta", "hr"))
    hr.tick()  # i9_e_verify_initiator

    ob = ob_worker(engine, wf, worker_name.replace("ta", "ob"))
    ob.tick()  # onboarding_checklist_builder

    it = it_worker(engine, wf, worker_name.replace("ta", "it"))
    it.tick()  # sso_identity_provisioner

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        instance = conn.execute(text("SELECT state, status FROM app.workflow_instance WHERE id = :i"),
                                {"i": instance_id}).one()
    return instance_id, requisition_id, employee_id, instance


def drive_hire_to_completion(engine, hire_org, wf, *, comp_band_id, retention_class_id,
                             proposed_base="1200000", worker_name="w-ta", bg_outcome="clear",
                             legal_entity_id=None, extra_access=None):
    """Continues drive_to_identity through access grant and payroll profile -- the hire flow's
    actual end (see finding 15: step 19/payslip is permanently out of its scope). Returns
    (instance_id, requisition_id, employee_id, final_instance_row)."""
    tenant = hire_org["tenant"]
    instance_id, requisition_id, employee_id, instance = drive_to_identity(
        engine, hire_org, wf, comp_band_id=comp_band_id, retention_class_id=retention_class_id,
        proposed_base=proposed_base, worker_name=worker_name, bg_outcome=bg_outcome,
        legal_entity_id=legal_entity_id, extra_access=extra_access)
    assert instance.status == "running"

    it = it_worker(engine, wf, worker_name.replace("ta", "it2"))
    it.tick()  # app_access_granter

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        instance = conn.execute(text("SELECT state, status, waiting_on_approval FROM app.workflow_instance "
                                     "WHERE id = :i"), {"i": instance_id}).one()
    if instance.status == "waiting_gate":   # g_it_offtemplate: only when extra_access was requested
        resolve_and_relay(engine, wf, tenant, "tenant_it", hire_org["founder_user"],
                         instance.waiting_on_approval, f"{worker_name}-offtemplate")

    pay = pay_worker(engine, wf, worker_name.replace("ta", "pay"))
    pay.tick()  # employee_record_writer_payroll

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        instance = conn.execute(text("SELECT state, status FROM app.workflow_instance WHERE id = :i"),
                                {"i": instance_id}).one()
    return instance_id, requisition_id, employee_id, instance
