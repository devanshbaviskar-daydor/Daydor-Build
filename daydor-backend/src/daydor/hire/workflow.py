"""The hire flow's hand-written workflow definition, replacing the generated skeleton for
`name='hire'` (daydor.workflow.definitions generates one for every model flow; this module is
the hand-written override its own docstring says flows may use).

Ten corrections over what the generator would produce for the same steps:

1. **Gate placement.** The generator attaches a step's gate to the transition *entering* that
   step's own state (literally: "step k's gate guards advancing into state k"). That reads
   correctly for a gate whose condition is known before the step runs. It reads backwards for
   `g_requisition_budget` (docs/model-findings.md finding 11): you want the founder's approval
   checked *after* the requisition is drafted and *before* a job posting goes out, not before the
   approval-routing step is even allowed to start. So here the gate sits on
   s03_approval_request's own outgoing transition.
2. **Real payload, not just an id.** Every entered state's enqueued job carries the instance's
   full `context` (see `daydor.workflow.engine.WorkflowEngine._enter`) alongside `subject_id`.
3. **Position check and requisition drafting are not queued steps.** `job_requisition.id` has to
   exist before `WorkflowEngine.start()` can use it as the instance's subject_id (ids are never
   insertable explicitly -- see daydor.hire.requisition's docstring) -- so both run synchronously
   in `start_hire()`, below, before the instance starts. s01_position/s02_job_requisition stay in
   the state graph with no `enter_jobs` of their own, purely so the transition log
   (`app.workflow_transition`) still shows every model step in order for audit, even though the
   real work already happened by the time they're entered.

4. **s04_job_posting does not auto-advance (added in Sprint 2).** Nothing about "a posting is
   live" implies "a candidate exists" -- advancing into s05_application has to wait for a real
   candidate to apply. See `daydor.hire.screening.submit_application`, the function that actually
   fires this transition, and `daydor.hire.posting`'s docstring for why its own handler no longer
   does.
5. **g_aedt and g_offer_band also move, for the same reason as g_requisition_budget (Sprint 2).**
   The generator would gate *entering* s06_screening_result / s08_offer. Both gates actually
   depend on something only known once that state's own work is done (whether the tool's
   automated recommendation needs HR sign-off; whether the offer is outside the comp band), so
   both sit on those states' own outgoing transitions instead, conditional on a `requires_*` flag
   the state's own handler sets via `context_patch`.

6. **s12_consent_record has no enter_jobs (added in Sprint 3).** `consent_record` has no agent
   writer by design (only the employee may grant their own consent -- see
   `daydor.hire.consent`'s docstring); there is no work for a job to do when entering this state,
   only the `dpdp_consent` gate to wait on when leaving it. `daydor.hire.consent.request_consent`
   is the function that actually fires past it.
7. **Steps 10/11 reuse one worker under two kind names, like steps 5/6 (Sprint 3).**
   `employee-record-writer` is the model's name for both `employee` (step 10) and
   `employment_record` (step 11); `employee_record_writer_create`/`_open` avoid the same
   kind-collision candidate-screener had in Sprint 2.

8. **s14_work_authorization is conditional on its own data, checked inside the handler (Sprint
   4).** I-9/E-Verify is US-only; rather than a context flag the caller must remember to set
   (like the `requires_*` gate flags), `daydor.hire.work_authorization.initiate_work_authorization`
   reads the employee's own `legal_entity.country_code` and no-ops outside the US. No gate is
   involved -- this isn't an approval, it's "does this step apply at all."
9. **g_it_offtemplate moves too, for the same reason as the other requires_* gates (Sprint 5).**
   It sits on s17_app_access_grant's own outgoing transition; the off-template grant row is still
   created immediately (see daydor.hire.access_grant's docstring for why that's not a gap).
10. **Step 19 (`payslip`) is out of scope, permanently, not just "later" (added in Sprint 5 --
    finding 15).** `payslip.payroll_run_id` is NOT NULL: a payslip cannot exist without a real
    `payroll_run`, which is a per-period batch covering every employee on it, built end to end by
    the Payroll flow's own sprints (docs/sprint-plan.md Sprints 6-9), gated by `g_pay_anomaly` and
    `g_pay_disburse`. There is no "just this one employee's first payslip" shortcut that doesn't
    either duplicate that machinery or fake a payroll_run into existence. The hire flow's own
    graph ends at s18_payroll_profile; this employee's first payslip is whatever Payroll Sprint 8
    produces once a cycle including them runs -- the model flow's name ("Requisition to first
    payslip") describes the employee's end-to-end journey, not one flow's sole responsibility for
    producing it.

Scope boundary: this covers hire flow steps 1-18 (position check through payroll profile) --
everything the hire flow itself is responsible for; see point 10 above for why step 19 ends the
story elsewhere. `s18_payroll_profile`'s "advance" goes to "done", which here really is this
flow's last word on the matter. Versions: `app.workflow_definition` version 1 is the generated
skeleton (`0010_workflow_seed.sql`), version 2 is Sprint 1's steps 1-4 (`0014_hire_workflow.sql`),
version 3 is Sprint 2's steps 5-8 (`0015_hire_workflow_v3.sql`), version 4 is Sprint 3's steps
9-13 (`0016_hire_workflow_v4.sql`), version 5 is Sprint 4's steps 14-16
(`0017_hire_workflow_v5.sql`), version 6 (this one) is Sprint 5's steps 17-18
(`0018_hire_workflow_v6.sql`).
"""
from __future__ import annotations

import json
from datetime import date
from uuid import UUID

from sqlalchemy import Connection

from daydor.hire.requisition import open_requisition
from daydor.workflow.engine import WorkflowEngine

HIRE_DEFINITION = {
    "title": "Requisition to payroll profile (hand-written, steps 1-18)",
    "description": "Seat check through payroll profile: requisition, posting, screening, "
                   "interview, offer, background check, employee record, consent, documents, "
                   "work authorization, onboarding checklist, SSO identity, access grant, "
                   "payroll profile. Step 19 (payslip) is out of scope -- see finding 15.",
    "initial": "start",
    "states": {
        "start": {"terminal": False, "on": {"advance": {"to": "s01_position"}}},
        "s01_position": {
            "terminal": False,
            "on": {"advance": {"to": "s02_job_requisition"}},
        },
        "s02_job_requisition": {
            "terminal": False,
            "on": {"advance": {"to": "s03_approval_request"}},
        },
        "s03_approval_request": {
            "terminal": False,
            "enter_jobs": [{"queue": "platform", "kind": "requisition_approval_router"}],
            "on": {"advance": {"to": "s04_job_posting", "gate": "g_requisition_budget"}},
        },
        "s04_job_posting": {
            "terminal": False,
            "enter_jobs": [{"queue": "ta", "kind": "job_posting_publisher"}],
            "on": {"advance": {"to": "s05_application"}},
        },
        "s05_application": {
            "terminal": False,
            "enter_jobs": [{"queue": "ta", "kind": "candidate_screener_intake"}],
            "on": {"advance": {"to": "s06_screening_result"}},
        },
        "s06_screening_result": {
            "terminal": False,
            "enter_jobs": [{"queue": "ta", "kind": "candidate_screener_assess"}],
            "on": {"advance": {"to": "s07_interview", "gate": "g_aedt", "gate_if": "requires_g_aedt"}},
        },
        "s07_interview": {
            "terminal": False,
            "enter_jobs": [{"queue": "ta", "kind": "interview_scheduler"}],
            "on": {"advance": {"to": "s08_offer"}},
        },
        "s08_offer": {
            "terminal": False,
            "enter_jobs": [{"queue": "ta", "kind": "offer_letter_generator"}],
            "on": {"advance": {"to": "s09_background_check", "gate": "g_offer_band",
                              "gate_if": "requires_g_offer_band"}},
        },
        "s09_background_check": {
            "terminal": False,
            "enter_jobs": [{"queue": "ta", "kind": "background_check_initiator"}],
            "on": {"advance": {"to": "s10_employee", "gate": "g_bg_adverse", "gate_if": "requires_g_bg_adverse"}},
        },
        "s10_employee": {
            "terminal": False,
            "enter_jobs": [{"queue": "hr", "kind": "employee_record_writer_create"}],
            "on": {"advance": {"to": "s11_employment_record"}},
        },
        "s11_employment_record": {
            "terminal": False,
            "enter_jobs": [{"queue": "hr", "kind": "employee_record_writer_open"}],
            "on": {"advance": {"to": "s12_consent_record"}},
        },
        "s12_consent_record": {
            "terminal": False,
            "on": {"advance": {"to": "s13_document", "gate": "dpdp_consent"}},
        },
        "s13_document": {
            "terminal": False,
            "enter_jobs": [{"queue": "privacy", "kind": "new_hire_doc_collector"}],
            "on": {"advance": {"to": "s14_work_authorization"}},
        },
        "s14_work_authorization": {
            "terminal": False,
            "enter_jobs": [{"queue": "hr", "kind": "i9_e_verify_initiator"}],
            "on": {"advance": {"to": "s15_checklist_task"}},
        },
        "s15_checklist_task": {
            "terminal": False,
            "enter_jobs": [{"queue": "ob", "kind": "onboarding_checklist_builder"}],
            "on": {"advance": {"to": "s16_identity_account"}},
        },
        "s16_identity_account": {
            "terminal": False,
            "enter_jobs": [{"queue": "it", "kind": "sso_identity_provisioner"}],
            "on": {"advance": {"to": "s17_app_access_grant"}},
        },
        "s17_app_access_grant": {
            "terminal": False,
            "enter_jobs": [{"queue": "it", "kind": "app_access_granter"}],
            "on": {"advance": {"to": "s18_payroll_profile", "gate": "g_it_offtemplate",
                              "gate_if": "requires_g_it_offtemplate"}},
        },
        "s18_payroll_profile": {
            "terminal": False,
            "enter_jobs": [{"queue": "pay", "kind": "employee_record_writer_payroll"}],
            "on": {"advance": {"to": "done"}},
        },
        "done": {"terminal": True},
    },
}


def start_hire(conn: Connection, engine: WorkflowEngine, *, position_id: UUID, hiring_manager_id: UUID,
               target_start_date: date, **extra_context) -> UUID:
    """Confirm the seat, draft the requisition, and start the hire workflow instance against it,
    advancing synchronously through the two already-done steps so the transition log records
    them. Returns the workflow_instance id. `extra_context` (channel, pay_range_min/max, ...) is
    whatever later steps need; it rides in the instance's context alongside position_id/
    hiring_manager_id/target_start_date, which are added automatically."""
    requisition_id = open_requisition(conn, position_id=position_id, hiring_manager_id=hiring_manager_id,
                                      target_start_date=target_start_date)
    context = {"position_id": str(position_id), "hiring_manager_id": str(hiring_manager_id),
              "target_start_date": target_start_date.isoformat(), **extra_context}
    instance_id = engine.start(conn, "hire", "job_requisition", requisition_id, context)
    engine.fire(conn, instance_id, "advance")  # start -> s01_position
    engine.fire(conn, instance_id, "advance")  # s01_position -> s02_job_requisition
    engine.fire(conn, instance_id, "advance")  # s02_job_requisition -> s03_approval_request (enqueues the router)
    return instance_id


def seed_sql(version: int) -> str:
    """Each call is a one-off, hand-authored migration (like 0011-0014), not a regenerate-in-place
    tool: bumping `version` here and re-running does not touch earlier versions' already-applied
    migration files (0014 for version 2 stays exactly as it was committed)."""
    body = json.dumps(HIRE_DEFINITION, sort_keys=True).replace("'", "''")
    return "\n".join([
        "-- Hand-written, NOT generated: see daydor.hire.workflow.HIRE_DEFINITION for why.",
        f"-- Supersedes 'hire' version {version - 1}.",
        "SET ROLE daydor_schema_owner;",
        "",
        "UPDATE app.workflow_definition SET active = false WHERE name = 'hire' AND active;",
        "INSERT INTO app.workflow_definition (name, version, definition, source) "
        f"VALUES ('hire', {version}, '{body}'::jsonb, 'hand-written');",
        "",
        "RESET ROLE;",
        "",
    ])


if __name__ == "__main__":  # pragma: no cover
    from pathlib import Path
    Path("migrations/sql/0018_hire_workflow_v6.sql").write_text(seed_sql(6))
    print("wrote migrations/sql/0018_hire_workflow_v6.sql")
