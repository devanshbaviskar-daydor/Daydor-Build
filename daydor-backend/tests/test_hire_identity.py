"""Hire flow steps 14-16 (work authorization -> onboarding checklist -> SSO identity), driven
end to end through the real WorkflowEngine + queue, using version 5 of 'hire'
(see migrations/sql/0017_hire_workflow_v5.sql)."""
from sqlalchemy import text

from daydor.db.session import tenant_session
from daydor.workflow.engine import WorkflowEngine
from tests.factories import insert
from tests.hire_helpers import comp_band, drive_to_identity, retention_policy  # noqa: F401


def test_hire_completes_through_identity_provisioning(engine, hire_org, comp_band, retention_policy):
    """India-based hire (hire_org's own legal_entity): I-9/E-Verify does not apply, but the
    checklist and SSO identity still get created."""
    tenant = hire_org["tenant"]
    wf = WorkflowEngine()
    instance_id, requisition_id, employee_id, instance = drive_to_identity(
        engine, hire_org, wf, comp_band_id=comp_band, retention_class_id=retention_policy,
        worker_name="w-india")
    # Continues into access grant/payroll profile (Sprint 5), not terminal at s16 anymore.
    assert instance.state == "s17_app_access_grant"
    assert instance.status == "running"

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        work_auth_count = conn.execute(text("SELECT count(*) FROM work_authorization WHERE employee_id = :e"),
                                       {"e": employee_id}).scalar_one()
        checklist = conn.execute(text("SELECT status FROM checklist WHERE employee_id = :e AND kind = 'onboarding'"),
                                 {"e": employee_id}).one()
        task_count = conn.execute(text("SELECT count(*) FROM checklist_task ct JOIN checklist c "
                                       "ON c.id = ct.checklist_id WHERE c.employee_id = :e"),
                                  {"e": employee_id}).scalar_one()
        identity = conn.execute(text("SELECT status, directory_provider FROM identity_account "
                                     "WHERE employee_id = :e"), {"e": employee_id}).one()
    assert work_auth_count == 0  # not US: no I-9/E-Verify row
    assert checklist.status == "open"
    assert task_count == 3
    assert identity.status == "active"
    assert identity.directory_provider == "fake-directory"


def test_us_hire_schedules_a_real_i9_timer(engine, hire_org, comp_band, retention_policy):
    """A US-based hire gets a real work_authorization row and a real app.timer for the I-9
    section 2 deadline -- not a TODO."""
    tenant = hire_org["tenant"]
    with engine.begin() as conn:
        us_legal_entity = insert(conn, "legal_entity", tenant_id=tenant, name="Hire Co US Inc",
                                 country_code="US")

    wf = WorkflowEngine()
    instance_id, requisition_id, employee_id, instance = drive_to_identity(
        engine, hire_org, wf, comp_band_id=comp_band, retention_class_id=retention_policy,
        worker_name="w-us", legal_entity_id=us_legal_entity)
    assert instance.state == "s17_app_access_grant"
    assert instance.status == "running"

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        work_auth = conn.execute(text("SELECT status, everify_case_no, next_action_due "
                                      "FROM work_authorization WHERE employee_id = :e"),
                                 {"e": employee_id}).one()
    # app.timer has no SELECT grant for tenant roles (only daydor_ops, for operational
    # visibility); read it directly, the same way tests/test_queue.py inspects app.job.
    with engine.connect() as conn:
        timer = conn.execute(text("SELECT queue, kind, status, fire_at FROM app.timer "
                                  "WHERE timer_key = :k"), {"k": f"i9-section2-{employee_id}"}).one()
    assert work_auth.status == "pending"
    assert work_auth.everify_case_no is not None
    assert timer.queue == "hr"
    assert timer.kind == "i9_section2_due"
    # target_start_date in this test fixture (2026-03-01, see tests/hire_helpers.py's
    # drive_to_job_posting) is in the past relative to "now" in this environment (2026-10-08), so
    # the timer's due date is already past and app.fire_due_timers() (run inside every
    # Worker.tick()) has already fired it -- which is itself the proof this is a real timer, not
    # a TODO: it actually fires when due, rather than just sitting there.
    assert timer.status == "fired"
    assert timer.fire_at.date() == work_auth.next_action_due
