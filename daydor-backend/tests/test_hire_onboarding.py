"""Hire flow steps 9-13 (background check -> employee -> employment_record -> consent ->
documents), driven end to end through the real WorkflowEngine + queue, using version 4 of
'hire' (see migrations/sql/0016_hire_workflow_v4.sql)."""
from sqlalchemy import text

from daydor.db.session import tenant_session
from daydor.hire.documents import handle_new_hire_doc_collector
from daydor.privacy.pii import decrypt_pii, encrypt_pii
from daydor.queue import Worker
from daydor.workflow.engine import WorkflowEngine
from tests.factories import insert
from tests.hire_helpers import comp_band, drive_to_consent_gate, resolve_and_relay, retention_policy  # noqa: F401


def test_adverse_background_check_requires_hr_signoff(engine, hire_org, comp_band, retention_policy):
    wf = WorkflowEngine()
    instance_id, requisition_id, employee_id, instance = drive_to_consent_gate(
        engine, hire_org, wf, comp_band_id=comp_band, retention_class_id=retention_policy,
        worker_name="w-adverse", bg_outcome="adverse")

    # bg_outcome="adverse" means employee creation only happens *after* HR signs off on
    # g_bg_adverse; drive_to_consent_gate's resolve_and_relay call for it already ran, so by now
    # the instance should be past it, parked on dpdp_consent instead.
    assert instance.state == "s12_consent_record"
    assert instance.status == "waiting_gate"

    with tenant_session(engine, "tenant_hr", hire_org["tenant"]) as conn:
        bg = conn.execute(text("SELECT status, adverse_action_stage FROM background_check bc "
                               "JOIN application a ON a.candidate_id = bc.candidate_id "
                               "WHERE a.requisition_id = :r"), {"r": requisition_id}).one()
    assert bg.status == "adverse"
    assert bg.adverse_action_stage == "pre_adverse"


def test_employee_created_with_null_pii_then_consent_unblocks_it(engine, hire_org, comp_band, retention_policy):
    """The actual finding-10/finding-12 payoff: employee is created with its 4 PII columns NULL,
    and only consent (captured against the now-real employee_id) unblocks app.encrypt_pii."""
    tenant = hire_org["tenant"]
    wf = WorkflowEngine()
    instance_id, requisition_id, employee_id, instance = drive_to_consent_gate(
        engine, hire_org, wf, comp_band_id=comp_band, retention_class_id=retention_policy,
        worker_name="w-consent")
    assert instance.state == "s12_consent_record"
    assert instance.status == "waiting_gate"
    consent_approval_id = instance.waiting_on_approval
    assert consent_approval_id is not None

    with tenant_session(engine, "tenant_founder", tenant) as conn:
        on_file = conn.execute(text("SELECT pan_encrypted_on_file FROM employee_masked WHERE id = :e"),
                               {"e": employee_id}).scalar_one()
    assert on_file is False

    # The employee grants consent (direct table write, not through an agent -- see
    # daydor.hire.consent's docstring) and then resolves the dpdp_consent gate themselves.
    with engine.begin() as conn:
        insert(conn, "consent_record", tenant_id=tenant, employee_id=employee_id, data_category="pan",
              purpose="identity_verification", status="granted", granted_at="2026-02-20",
              consent_artifact_ref="doc-onboarding-1")
        new_hire_user = insert(conn, "app_user", tenant_id=tenant, role="employee", employee_id=employee_id)
    resolve_and_relay(engine, wf, tenant, "tenant_employee", new_hire_user, consent_approval_id, "consent")

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        encrypt_pii(conn, "employee", "pan_encrypted", employee_id, "ABCDE1234F")
    with tenant_session(engine, "tenant_payroll", tenant) as conn:
        value = decrypt_pii(conn, "employee", "pan_encrypted", employee_id, "tax_filing")
    assert value == "ABCDE1234F"

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        final = conn.execute(text("SELECT state, status FROM app.workflow_instance WHERE id = :i"),
                             {"i": instance_id}).one()
    assert final.state == "s13_document"
    assert final.status == "running"


def test_new_hire_documents_are_collected_once_consent_clears(engine, hire_org, comp_band, retention_policy):
    tenant = hire_org["tenant"]
    wf = WorkflowEngine()
    instance_id, requisition_id, employee_id, instance = drive_to_consent_gate(
        engine, hire_org, wf, comp_band_id=comp_band, retention_class_id=retention_policy,
        worker_name="w-docs")

    with engine.begin() as conn:
        new_hire_user = insert(conn, "app_user", tenant_id=tenant, role="employee", employee_id=employee_id)
    resolve_and_relay(engine, wf, tenant, "tenant_employee", new_hire_user, instance.waiting_on_approval,
                     "docs-consent")

    # The "privacy" queue is shared platform-wide across tests in this session (e.g. the previous
    # test's instance also reaches s13_document and enqueues this same job kind without ever
    # running it), so more than one job may be claimed here; only this instance's own outcome
    # matters.
    priv_worker = Worker(engine, "privacy", "w-priv")
    priv_worker.register("new_hire_doc_collector", worker="new-hire-doc-collector", fn=handle_new_hire_doc_collector(wf))
    assert priv_worker.tick()["succeeded"] >= 1

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        docs = conn.execute(text("SELECT document_class FROM document WHERE subject_type = 'employee' "
                                 "AND subject_id = :e ORDER BY document_class"), {"e": employee_id}).scalars().all()
        instance_final = conn.execute(text("SELECT status FROM app.workflow_instance WHERE id = :i"),
                                      {"i": instance_id}).scalar_one()
    assert docs == ["id_proof", "offer_letter"]
    assert instance_final == "running"  # continues into work_authorization (Sprint 4), not terminal
