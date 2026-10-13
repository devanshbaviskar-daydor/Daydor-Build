# Proposed registry scope additions (for review before Phase 1 implementation)

Written Oct 13 2026. Nothing in `registry/` has been changed. Review this, mark each row accept, change or
reject, and Phase 1 then applies the accepted rows to `registry/worker_classification.json` and regenerates.

## Why
The registry's `reads` and `writes` come from the model's reader and writer lists. Per-worker database
roles are generated from them, so any table the code needs that the registry omits would be refused by the
database. This list is derived from a function-level scan of the SQL in `src/daydor/{hire,exit,payroll,
timekeeping,benefits}` (see `docs/worker-roles-reconciliation.md`, sections 2 and 4), after the handler splits
you approved.

## How I propose to record them
A new authored field per worker, `extra_scope: {"reads": [...], "writes": [...], "why": "..."}`, merged by
`agents/registry.py` into the generated `reads` and `writes`. This keeps the model-derived scope and the
reviewed additions apart, and each addition carries its reason. `tests/test_registry.py` keeps checking the
C3, C4 and encrypted-column rule on the merged scope, so an addition cannot quietly give a model-driven worker
restricted data. Writes also remain capped by the model's "G" column access and by `grant_caps`.
Tables a worker writes are readable by it, so own tables are not repeated below.

## Reads additions
| Worker | Add reads | Evidence |
|---|---|---|
| employee-record-writer | `job_profile`, `job_requisition` | `handle_employee_record_writer_open/_create` (seat and job profile lookup) |
| i9-e-verify-initiator | `employee`, `legal_entity` | `initiate_work_authorization` (country check); timer handler `check_i9_section2` also reads `employee` |
| app-access-granter | `employee`, `identity_account`, `position`, `job_requisition` | `_grant_state`, `handle_app_access_granter` |
| cobra-trigger-detector | `employee`, `legal_entity`, `termination` | `detect_cobra_event` (US check), handler |
| cobra-notice-generator | none | updates its own `cobra_event` only |
| termination-checklist-builder | none beyond existing `termination` | |
| tax-withholding-calculator | `employee`, `legal_entity` | `compute_withholding` (jurisdiction). `payroll_profile` stays listed but is unused |
| payslip-issuer | `payroll_run` | `issue_payslips` refuses until `disbursed_at` is set |
| tax-filing-submitter | `legal_entity`, `payroll_run` | `file_payroll_run`. `consent_record` stays listed but is unused |
| pto-accrual-calculator | `employee` | `accrue_leave` |
| timecard-approval-router | `approval_request`, `time_punch` | `timekeeping.gate_resolved` handler (see platform actors) |

## Writes additions
| Worker | Add writes | Evidence and note |
|---|---|---|
| employee-record-writer | `job_requisition` | `fill_seat` marks the requisition filled. Note: `requisition-drafter` (an llm worker) also writes this table; I propose `employee-record-writer` is limited to the status columns by the model's column access, and the matrix test checks it. Alternative: move `fill_seat` into a separate `hire-seat-closer`; I recommend not adding workers |
| termination-checklist-builder | `checklist_task` | `build_termination_checklist` writes tasks as well as the checklist |

## Combined role for `payroll-run-builder` (your decision 2)
`build_payroll_run` does the persistence work of four registry workers in one transaction. Until it is
split, `payroll-run-builder` gets a documented combined scope:

- reads: `employee`, `employment_record`, `legal_entity`, `payslip`, `payroll_run`, `payroll_profile`,
  `statutory_rate_rule`, `pt_slab_rule`, `garnishment_order`, `benefit_election`, `timecard`, `leave_balance`
- writes: `payslip`, `payslip_line`, `gratuity_accrual_balance`, `payroll_run` (derived totals still only
  through `app.open_payroll_run`, `record_payslip`, `finalize_payroll_run`)
- never: `payroll_run.disbursed_at` (guarded; owner `direct-deposit-disburser`)

The four narrower workers keep their own roles; the combined scope is marked in the registry with a
`flags` entry (`combined-scope-until-split`) and a test lists every worker that carries it, so it cannot
spread. Please confirm the reads list: I derived `benefit_election`, `timecard` and `leave_balance` from the
payroll flow's design (sprint plan, Sprint 6 to 8), not from a line of `run_builder.py`; if you want the
combined scope to be only what the code touches today, drop those three.

## Handler splits (decision 2)
Each becomes one handler kind per worker, with the workflow definitions regenerated and a new forward-only
workflow version, as the hire flow did.

| Today | Becomes | Role after |
|---|---|---|
| `employee_closeout` | `vesting_schedule_tracker`, `rehire_eligibility_flagger`, `employee_record_writer_closeout` | each worker's own role |
| `cobra_trigger_detector` (detects and sends) | `cobra_trigger_detector`, `cobra_notice_generator` | each worker's own role |
| `final_pay_calculator` + `final_settlement_opener` | `final_pay_calculator` (calculate and open); `direct_deposit_disburser` unchanged | `final_settlement_opener` merges into `final-pay-calculator`, which writes `final_settlement` through `app.open_final_settlement` |

## Platform actors (not workers in the registry)
Three handlers run no registry worker. They need roles too, so I propose a small separate list, outside the
89, in `registry/platform_actors.json` (reviewed the same way):

| Actor | Used by | Scope |
|---|---|---|
| `workflow-engine` | `workflow.gate_resolved` | read `approval_request`; platform workflow tables only; no model-table writes |
| `root-orchestrator` | `legal_hold_checker`; `i9_section2_due` timer | read `legal_hold`, `termination`, `employee`, `work_authorization`; platform workflow tables |
| (timecard gate handler) | `timekeeping.gate_resolved` | folded into `timecard-approval-router` above |

Every handler that calls `engine.fire` also needs the platform workflow table grants; those come from the
platform group (migration 0027), not the registry.

## Not proposed
- No additions for the 56 workers without code. Their scope stays the model's until code exists.
- No broader reads "just in case" and no shared lookup role.
- No change to guarded-column owners (they match the proposal).

## Update, Oct 13 2026
The combined `payroll-run-builder` scope above is retired: `payroll/run_builder.py` was split, the three calculators read what they need, and the builder keeps only `employee`, `employment_record`, `legal_entity`, `payslip` reads and `payslip_line` writes (`extra_scope` in the registry).

