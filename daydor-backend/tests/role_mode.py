"""Run the existing flow tests with queue handlers on per-worker roles instead of agent_<domain>.

    DAYDOR_TEST_ROLES=worker pytest

When set, `Worker.register(kind, role="agent_...")` switches to the worker that owns that handler kind
(KIND_TO_WORKER) whenever there is one. Direct service calls inside tests still use their domain roles;
this proves the *handlers* (the real work of every flow) run inside the registry's scopes.
"""
from __future__ import annotations

import os

from daydor.queue.worker import Worker

KIND_TO_WORKER = {
    "workflow.gate_resolved": "workflow-engine",
    "requisition_approval_router": "requisition-approval-router",
    "job_posting_publisher": "job-posting-publisher",
    "candidate_screener_intake": "candidate-screener",
    "candidate_screener_assess": "candidate-screener",
    "interview_scheduler": "interview-scheduler",
    "offer_letter_generator": "offer-letter-generator",
    "background_check_initiator": "background-check-initiator",
    "employee_record_writer": "employee-record-writer",
    "employee_record_writer_create": "employee-record-writer",
    "employee_record_writer_open": "employee-record-writer",
    "employee_record_writer_payroll": "employee-record-writer",
    "i9_e_verify_initiator": "i9-e-verify-initiator",
    "i9_section2_due": "root-orchestrator",
    "new_hire_doc_collector": "new-hire-doc-collector",
    "onboarding_checklist_builder": "onboarding-checklist-builder",
    "sso_identity_provisioner": "sso-identity-provisioner",
    "app_access_granter": "app-access-granter",
    "legal_hold_checker": "root-orchestrator",
    "termination_checklist_builder": "termination-checklist-builder",
    "deprovisioning_agent": "deprovisioning-agent",
    "equipment_return_tracker": "equipment-return-tracker",
    "final_pay_calculator": "final-pay-calculator",
    "final_settlement_opener": "final-pay-calculator",
    "direct_deposit_disburser": "direct-deposit-disburser",
    "cobra_trigger_detector": "cobra-trigger-detector",
    "vesting_schedule_tracker": "vesting-schedule-tracker",
    "rehire_eligibility_flagger": "rehire-eligibility-flagger",
    "employee_record_writer_closeout": "employee-record-writer",
    "timekeeping.gate_resolved": "timecard-approval-router",
}


def install() -> None:
    original = Worker.register

    def register(self, kind, role=None, fn=None, purpose=None, *, worker=None):
        if worker is None and role is not None and role.startswith("agent_") and kind in KIND_TO_WORKER:
            return original(self, kind, None, fn, purpose, worker=KIND_TO_WORKER[kind])
        return original(self, kind, role, fn, purpose, worker=worker)

    Worker.register = register


if os.environ.get("DAYDOR_TEST_ROLES") == "worker":
    install()
