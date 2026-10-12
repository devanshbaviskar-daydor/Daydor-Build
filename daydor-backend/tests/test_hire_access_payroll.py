"""Hire flow steps 17-18 (app access grant -> payroll profile), driven end to end through the
real WorkflowEngine + queue, using version 6 of 'hire' (see
migrations/sql/0018_hire_workflow_v6.sql). This is the hire flow's actual end: step 19
(payslip) is permanently out of scope -- see docs/model-findings.md finding 15."""
from sqlalchemy import text

from daydor.db.session import tenant_session
from daydor.workflow.engine import WorkflowEngine
from tests.hire_helpers import access_role_template, comp_band, drive_hire_to_completion, retention_policy  # noqa: F401


def test_hire_completes_with_on_template_access_and_payroll_profile(engine, hire_org, comp_band,
                                                                     retention_policy, access_role_template):
    tenant = hire_org["tenant"]
    wf = WorkflowEngine()
    instance_id, requisition_id, employee_id, instance = drive_hire_to_completion(
        engine, hire_org, wf, comp_band_id=comp_band, retention_class_id=retention_policy,
        worker_name="w-ontemplate")
    assert instance.state == "done"
    assert instance.status == "completed"

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        grants = conn.execute(
            text("SELECT ag.app_name, ag.source FROM app_access_grant ag "
                 "JOIN identity_account ia ON ia.id = ag.identity_account_id "
                 "WHERE ia.employee_id = :e ORDER BY ag.app_name"), {"e": employee_id}).all()
        payroll_profile = conn.execute(
            text("SELECT pay_frequency, payment_method, work_state, uan_number "
                 "FROM payroll_profile WHERE employee_id = :e"), {"e": employee_id}).one()
    assert [(g.app_name, g.source) for g in grants] == [("code-repo", "template"), ("email", "template")]
    assert payroll_profile.pay_frequency == "monthly"
    assert payroll_profile.payment_method == "bank_transfer"
    assert payroll_profile.work_state == "KA"
    assert payroll_profile.uan_number == "123456789012"


def test_off_template_access_requires_it_signoff(engine, hire_org, comp_band, retention_policy,
                                                 access_role_template):
    """An access request outside the role template is still granted immediately (the row exists
    right away, like every other requires_* gate in this flow), but parks the hire flow for IT
    to review before it's considered done."""
    tenant = hire_org["tenant"]
    wf = WorkflowEngine()
    instance_id, requisition_id, employee_id, instance = drive_hire_to_completion(
        engine, hire_org, wf, comp_band_id=comp_band, retention_class_id=retention_policy,
        worker_name="w-offtemplate",
        extra_access=[{"app_name": "production-db", "permission_level": "admin"}])
    assert instance.state == "done"
    assert instance.status == "completed"

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        grants = conn.execute(
            text("SELECT ag.app_name, ag.source FROM app_access_grant ag "
                 "JOIN identity_account ia ON ia.id = ag.identity_account_id "
                 "WHERE ia.employee_id = :e ORDER BY ag.app_name"), {"e": employee_id}).all()
    assert ("production-db", "manual") in [(g.app_name, g.source) for g in grants]
    assert ("email", "template") in [(g.app_name, g.source) for g in grants]
