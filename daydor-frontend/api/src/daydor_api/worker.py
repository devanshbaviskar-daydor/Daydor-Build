"""Runs the backend's queue workers.

The backend registers handlers in its tests but ships no process that ticks them, so nothing moves
a workflow forward in a running system. This is that process: it registers every handler the
backend has today (Hire, Exit) with the queue it runs on and the registry worker that owns it
(`worker=`: the database role, its column grants and its enabled flag all come from the backend's worker
registry, and a disabled worker's job fails closed), then ticks them in a loop. The `agent_<domain>`
roles and the version 2 `employee_closeout` handler are gone (0034).

Steps 9-18 (background check through payroll profile) were added once the backend's Hire flow grew
past the offer step; `employee_record_writer_create`/`_open`/`_payroll` replace the single
`employee_record_writer` kind this module used to register, which no version of the hire workflow
definition still in use (we're on version 6) ever enqueues -- see docs/integration-notes.md.

Run:  python -m daydor_api.worker
"""
from __future__ import annotations

import logging
import time

from sqlalchemy import Engine

from daydor.agents.runs import SETTLE_KIND, SETTLE_QUEUE, handle_agent_gate_resolved
from daydor.clocks import handle_statutory_clock_scan
from daydor.hire.access_grant import handle_app_access_granter
from daydor.hire.approvals import handle_requisition_approval_router
from daydor.hire.background_check import handle_background_check_initiator
from daydor.hire.checklist import handle_onboarding_checklist_builder
from daydor.hire.documents import handle_new_hire_doc_collector
from daydor.hire.employee_record import (
    handle_employee_record_writer_create,
    handle_employee_record_writer_open,
    handle_employee_record_writer_payroll,
)
from daydor.hire.identity import handle_sso_identity_provisioner
from daydor.hire.interview import handle_interview_scheduler
from daydor.hire.offer import handle_offer_letter_generator
from daydor.hire.posting import handle_job_posting_publisher
from daydor.hire.screening import handle_candidate_screener_assess, handle_candidate_screener_intake
from daydor.hire.work_authorization import handle_i9_e_verify_initiator
from daydor.exit.checklist import handle_termination_checklist_builder
from daydor.exit.closeout import (
    handle_employee_record_writer_closeout,
    handle_rehire_eligibility_flagger,
    handle_vesting_schedule_tracker,
)
from daydor.exit.cobra import handle_cobra_trigger_detector
from daydor.exit.deprovisioning import handle_deprovisioning_agent
from daydor.exit.device_return import handle_equipment_return_tracker
from daydor.exit.final_settlement import (
    handle_direct_deposit_disburser,
    handle_final_pay_calculator,
    handle_final_settlement_opener,
)
from daydor.exit.legal_hold import handle_legal_hold_checker
from daydor.queue import Worker
from daydor.timekeeping.timecard import handle_timekeeping_gate_resolved
from daydor.workflow.engine import WorkflowEngine, gate_resolved_handler

from .onboarding import provision_employee_signin
from .state import get_engine

log = logging.getLogger("daydor_api.worker")


def _employee_created_then_provision_signin(wf: WorkflowEngine):
    """Wraps the real handler: after the employee row exists, also provision their own sign-in
    (see onboarding.py's module docstring for why this has to happen now, not at the SSO step)."""
    inner = handle_employee_record_writer_create(wf)

    def handle(conn, job):
        result = inner(conn, job)
        provision_employee_signin(conn, tenant_id=job.tenant_id, employee_id=result["employee_id"])
        return result
    return handle


def build_workers(engine: Engine | None = None, name: str = "api") -> list[Worker]:
    engine = engine or get_engine()
    wf = WorkflowEngine()
    workflow = Worker(engine, "workflow", f"{name}-workflow")
    workflow.register("workflow.gate_resolved", worker="workflow-engine", fn=gate_resolved_handler(wf))
    platform = Worker(engine, "platform", f"{name}-platform")
    platform.register("requisition_approval_router", worker="requisition-approval-router", fn=handle_requisition_approval_router(wf))
    # The daily statutory-clock scan (COBRA, expiries, 409A, thresholds): raises clock.due_soon / clock.overdue events.
    # A tenant's chain starts with daydor.clocks.start_clock_scan and then reschedules itself.
    platform.register("statutory_clock_scan", worker="root-orchestrator", fn=handle_statutory_clock_scan)
    ta = Worker(engine, "ta", f"{name}-ta")
    ta.register("job_posting_publisher", worker="job-posting-publisher", fn=handle_job_posting_publisher())
    ta.register("candidate_screener_intake", worker="candidate-screener", fn=handle_candidate_screener_intake(wf))
    ta.register("candidate_screener_assess", worker="candidate-screener", fn=handle_candidate_screener_assess(wf))
    ta.register("interview_scheduler", worker="interview-scheduler", fn=handle_interview_scheduler(wf))
    ta.register("offer_letter_generator", worker="offer-letter-generator", fn=handle_offer_letter_generator(wf))
    ta.register("background_check_initiator", worker="background-check-initiator", fn=handle_background_check_initiator(wf))
    hr = Worker(engine, "hr", f"{name}-hr")
    hr.register("employee_record_writer_create", worker="employee-record-writer", fn=_employee_created_then_provision_signin(wf))
    hr.register("employee_record_writer_open", worker="employee-record-writer", fn=handle_employee_record_writer_open(wf))
    hr.register("i9_e_verify_initiator", worker="i9-e-verify-initiator", fn=handle_i9_e_verify_initiator(wf))
    hr.register("legal_hold_checker", worker="root-orchestrator", fn=handle_legal_hold_checker(wf))
    hr.register("termination_checklist_builder", worker="termination-checklist-builder", fn=handle_termination_checklist_builder(wf))
    hr.register("cobra_trigger_detector", worker="cobra-trigger-detector", fn=handle_cobra_trigger_detector(wf))
    # Exit workflow version 3 (0029, active since 0033): one close-out step per worker.
    hr.register("vesting_schedule_tracker", worker="vesting-schedule-tracker", fn=handle_vesting_schedule_tracker(wf))
    hr.register("rehire_eligibility_flagger", worker="rehire-eligibility-flagger",
                fn=handle_rehire_eligibility_flagger(wf))
    hr.register("employee_record_writer_closeout", worker="employee-record-writer",
                fn=handle_employee_record_writer_closeout(wf))
    privacy = Worker(engine, "privacy", f"{name}-privacy")
    privacy.register("new_hire_doc_collector", worker="new-hire-doc-collector", fn=handle_new_hire_doc_collector(wf))
    ob = Worker(engine, "ob", f"{name}-ob")
    ob.register("onboarding_checklist_builder", worker="onboarding-checklist-builder", fn=handle_onboarding_checklist_builder(wf))
    it = Worker(engine, "it", f"{name}-it")
    it.register("sso_identity_provisioner", worker="sso-identity-provisioner", fn=handle_sso_identity_provisioner(wf))
    it.register("app_access_granter", worker="app-access-granter", fn=handle_app_access_granter(wf))
    it.register("deprovisioning_agent", worker="deprovisioning-agent", fn=handle_deprovisioning_agent(wf))
    it.register("equipment_return_tracker", worker="equipment-return-tracker", fn=handle_equipment_return_tracker(wf))
    pay = Worker(engine, "pay", f"{name}-pay")
    pay.register("employee_record_writer_payroll", worker="employee-record-writer", fn=handle_employee_record_writer_payroll(wf))
    pay.register("final_pay_calculator", worker="final-pay-calculator", fn=handle_final_pay_calculator(wf))
    pay.register("final_settlement_opener", worker="final-pay-calculator", fn=handle_final_settlement_opener(wf))
    pay.register("direct_deposit_disburser", worker="direct-deposit-disburser", fn=handle_direct_deposit_disburser(wf))
    # g_timecard's resolution isn't tracked by a WorkflowEngine instance (pay periods recur, no
    # single start/end) -- it fans out to this second, dedicated 'timekeeping' queue instead of
    # the workflow engine's own (daydor.timekeeping.timecard's module docstring).
    timekeeping = Worker(engine, "timekeeping", f"{name}-timekeeping")
    timekeeping.register("timekeeping.gate_resolved", worker="timecard-approval-router", fn=handle_timekeeping_gate_resolved)
    # Agent runs (0040): when a tenant holds a worker behind approval, the person's decision on g_agent_action lands here
    # and puts the held job back (or stops it).
    agent_runs = Worker(engine, SETTLE_QUEUE, f"{name}-agent-runs")
    agent_runs.register(SETTLE_KIND, worker="workflow-engine", fn=handle_agent_gate_resolved)
    return [workflow, platform, ta, hr, privacy, ob, it, pay, timekeeping, agent_runs]


def tick_all(workers: list[Worker], rounds: int = 3) -> dict[str, int]:
    """Several rounds, because one job's result (a transition) often enqueues the next job."""
    totals: dict[str, int] = {}
    for _ in range(rounds):
        for w in workers:
            for k, v in w.tick().items():
                totals[k] = totals.get(k, 0) + v
    return totals


def run(interval: float = 1.0) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    workers = build_workers()
    log.info("queue workers started (%d queues)", len(workers))
    while True:
        try:
            done = tick_all(workers, rounds=1)
            if done.get("succeeded") or done.get("failed"):
                log.info("tick: %s", done)
        except Exception:  # noqa: BLE001 - keep the loop alive; the job table records failures
            log.exception("tick failed")
        time.sleep(interval)


if __name__ == "__main__":
    run()
