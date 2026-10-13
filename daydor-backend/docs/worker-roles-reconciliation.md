# Worker roles: reconciling the registry with the repo (Phase 0)

Written Oct 13 2026. Analysis only: no migration, model, registry or source file was changed for this
document. It answers the Phase 0 list in `docs/claude-code-kickoff.md` and ends with the decisions I need
before Phase 1.

## 0. Baseline

- `git log`: 3 commits, head `2bebeaf` (grant caps for the employee role).
- `pytest` with `DAYDOR_DATABASE_URL` / `DAYDOR_TEST_DATABASE_URL` pointed at Postgres 16 on port 5433:
  **224 passed**. With the default URLs (port 5432, Postgres 14) about 180 tests error in setup on
  `INHERIT` in `CREATE ROLE`; that is the machine's setup, not the code.
- `git status`: uncommitted edits I did not make, which I have not touched: `src/daydor/gates/soft.py`
  (new `open_approval` argument), `src/daydor/hire/{access_grant,employee_record,work_authorization}.py`,
  `tests/test_hire_loose_ends.py`, and two files under `daydor-frontend/api`. Everything under
  `registry/`, the worker docs, `agents/registry.py`, `gates/decider.py` and the two new test files is
  the Downloads fork's material I added earlier.

## 1. What I found, in order of how much it changes Phase 1

1. **A latent bug: agent roles can never encrypt or decrypt PII.** `app.current_app_role()` collapses every
   `agent_*` role to `agent_runtime`, but `app.pii_column.collect_roles` and `app.pii_purpose.allowed_roles`
   (migration 0011) list `agent_hr`, `agent_ob`, `agent_pay`. The checks are `current_app_role() = ANY(...)`,
   so they never match. I confirmed it live: as `agent_hr`, `current_app_role()` is `agent_runtime`, and
   `'agent_runtime' = ANY(ARRAY['tenant_hr','agent_hr','agent_ob'])` is false. No test exercises PII as an
   agent, so nothing has caught it. It will bite `direct-deposit-disburser` (bank account, purpose
   `payroll_disbursal`) and `employee-record-writer` as soon as they run for real. Phase 1 must fix it,
   because per-worker roles change what `current_app_role()` should return.
2. **`agent_runtime` carries platform grants that worker roles also need.** It holds 81 model tables at
   column level, plus 7 `app` tables (`gate_definition`, `gate_evaluation`, `gate_guard`, `holiday` SELECT;
   `workflow_definition` SELECT; `workflow_instance`, `workflow_transition` SELECT and INSERT) and EXECUTE on
   23 `app` functions (`enqueue`, `emit_event`, `schedule_timer`, `cancel_timer`, `add_business_days`,
   `is_business_day`, `record_gate_evaluation`, `open_payroll_run`, `record_payslip`, `finalize_payroll_run`,
   `open_final_settlement`, `encrypt_pii`, `decrypt_pii`, the session-context helpers, and others). If a
   worker role simply joins `agent_runtime`, it inherits all 81 tables and narrowing means nothing. If it does
   not, it loses the platform grants. So Phase 1 needs to split `agent_runtime` into a platform group
   (the `app` objects) and the model-table grants, which only worker roles then receive, narrowed.
3. **Production runs through the frontend API, not only tests.** `daydor-frontend/api/src/daydor_api/worker.py`
   registers every flow handler with `role="agent_<domain>"`. `sessions.py` keeps `ALLOWED_AGENT_ROLES`
   (`agent_ta, agent_hr, agent_ro, agent_pay, agent_time, agent_ben, agent_it`) and 18 router calls use
   `agent_session(ident, "agent_pay")` and similar to run services as a domain agent. Phase 1 step 5
   (the queue `Worker` takes the role from the registry) and step 6 (remove `agent_*`) therefore touch that
   repo too. You said to keep changes in `daydor-backend`; I need your decision on how to handle this (see
   section 9).
4. **Several handlers do the work of more than one registry worker in one transaction.** A single role per
   worker cannot run them unchanged; they must be split or given a combined role (section 3).
5. **Payroll, timekeeping and benefits services have no queue handler.** They are plain functions the API
   calls inside `agent_session`. The queue-based "role from the registry" mechanism does not cover them.
6. **The registry's `reads` lists are too narrow** for about a dozen workers whose code reads tables the registry does
   not list (section 5). A generated role would break working code.

## 2. Handlers and services mapped to registry workers

Handler kind → registry worker, with the role the code registers it under, versus the worker's registry
`home_domain`. Production registrations are in `daydor-frontend/api/.../worker.py`; the tests register the
same kinds (`tests/hire_helpers.py`, `tests/exit_helpers.py`, and others).

| Handler kind | Registry worker | Registered role | Registry home_domain |
|---|---|---|---|
| requisition_approval_router | requisition-approval-router | agent_ro | ro |
| job_posting_publisher | job-posting-publisher | agent_ta | ta |
| candidate_screener_intake, candidate_screener_assess | candidate-screener (one worker, two kinds) | agent_ta | ta |
| interview_scheduler | interview-scheduler | agent_ta | ta |
| offer_letter_generator | offer-letter-generator | agent_ta | ta |
| background_check_initiator | background-check-initiator | agent_ta | ta |
| employee_record_writer_create, _open | employee-record-writer (one worker, three kinds) | agent_hr | hr |
| employee_record_writer_payroll | employee-record-writer | **agent_pay** | hr (mismatch) |
| i9_e_verify_initiator | i9-e-verify-initiator | agent_hr | hr |
| i9_section2_due | none (timer handler of i9-e-verify-initiator) | agent_hr | n/a |
| new_hire_doc_collector | new-hire-doc-collector | **agent_priv** | ob (mismatch) |
| onboarding_checklist_builder | onboarding-checklist-builder | agent_ob | ob |
| sso_identity_provisioner | sso-identity-provisioner | agent_it | it |
| app_access_granter | app-access-granter | agent_it | it |
| legal_hold_checker | none (the model's "root orchestrator", a pseudo-actor) | agent_hr | n/a |
| termination_checklist_builder | termination-checklist-builder | **agent_hr** | ob (mismatch) |
| deprovisioning_agent | deprovisioning-agent | agent_it | it |
| equipment_return_tracker | equipment-return-tracker | agent_it | it |
| final_pay_calculator | final-pay-calculator | **agent_pay** | er (mismatch) |
| final_settlement_opener | none (the write step of final-pay-calculator) | agent_pay | n/a |
| direct_deposit_disburser | direct-deposit-disburser | agent_pay | pay |
| cobra_trigger_detector | cobra-trigger-detector (also does cobra-notice-generator's job) | **agent_hr** | ben (mismatch) |
| employee_closeout | none: three workers in one handler (see below) | agent_hr | n/a |
| workflow.gate_resolved | none (platform: the workflow engine) | agent_ro | n/a |
| timekeeping.gate_resolved | none (platform: `g_timecard` resolution) | agent_time | n/a |

The role-versus-home_domain mismatches mean today's domain role is not the worker's registry domain. With
per-worker roles this stops mattering, but the tests and the API register those roles by name and must move.

**Handlers that run several workers' jobs in one transaction** (each needs a split or an explicit combined
role; decision in section 9):
- `employee_closeout` (`exit/closeout.py`): reads `vesting_event`/`equity_grant` (vesting-schedule-tracker),
  flags `termination.rehire_eligible` (rehire-eligibility-flagger) and sets `employee.is_active` and
  `date_of_exit` (employee-record-writer's close-out).
- `employee_record_writer_open` (`hire/employee_record.py`): writes `employee`, `employment_record`, and also
  updates `position` and `job_requisition`. The registry gives employee-record-writer `position` but not
  `job_requisition` (that is requisition-drafter's table).
- `exit/cobra.py`: detecting the event (cobra-trigger-detector) and sending the notice that sets
  `notice_sent_at` (cobra-notice-generator, per the proposal) are one module and one handler today.
- `exit/final_settlement.py`: the calculation (final-pay-calculator) and the disbursal UPDATE
  (direct-deposit-disburser) share a module; `final_settlement_opener` is a handler with no registry name.
- `payroll/run_builder.py`: one function does what the registry splits across payroll-run-builder,
  gross-pay-calculator, tax-withholding-calculator and garnishment-processor (it writes `payslip_line` and
  calls `app.record_payslip`; the registry gives `payslip_line` only to the last three).

**Registry workers with code:** I mapped 33 of the 89 to source modules (hire 13, exit 9, payroll 8,
timekeeping and benefits 3). The other 56 have no code yet, almost all wave 3 and 4 (benefits carriers and
QLEs, ER, comp, learning, finance, device, performance, remaining timekeeping). They get roles and grants from
the registry but nothing runs as them yet. **Handlers with no registry worker:** the three platform handlers
above, `legal_hold_checker`, `final_settlement_opener`, `i9_section2_due`, `employee_closeout`.

## 3. Guarded columns: who writes them today

| Guarded column (gate) | Proposed owner (kickoff) | What the code does today |
|---|---|---|
| `payroll_run.disbursed_at` (g_pay_disburse) | direct-deposit-disburser | `payroll/disbursement.py` UPDATE, matches |
| `final_settlement.disbursed_at` (g_pay_disburse) | direct-deposit-disburser | `exit/final_settlement.py` `handle_direct_deposit_disburser`, matches |
| `contractor_invoice.paid_at` (g_pay_disburse) | multi-currency-payment-router | no code yet |
| `gl_journal_entry.posted_at` (g_close) | gl-poster | `payroll/gl_posting.py`, matches. `period-close-runner` also lists the table; no code |
| `identity_account.deprovisioned_at` (g_it_deprov) | deprovisioning-agent | `exit/deprovisioning.py`, matches |
| `cobra_event.notice_sent_at` (g_cobra) | cobra-notice-generator (confirmed) | `exit/cobra.py` `send_cobra_notice`, same module and handler as the detector; the registry marks cobra-notice-generator wave 4 with no flows, which is out of date |
| `er_case.outcome` (g_er_adjud) | investigation-tracker | no code yet; case-intake-router also writes `er_case` |

All seven agree with the proposal where code exists. Two columns (`contractor_invoice.paid_at`,
`er_case.outcome`) have nothing to verify against yet. Note `payroll-run-builder` and `final-pay-calculator`
are also flagged in the registry as writing a guarded table (`payroll_run`, `final_settlement`) without
owning its guarded column; that is the table-but-not-column case from step 4.

## 4. Real table access versus registry scope

Static scan of each mapped module's SQL (INSERT, UPDATE, SELECT/JOIN). Shared modules can overstate a
worker, so I only list items I checked by hand. Column-level checks against the model's "G" access are left
to the Phase 1 matrix test.

| Worker | Code touches beyond the registry's scope |
|---|---|
| i9-e-verify-initiator | reads `employee`, `legal_entity` (registry reads: none) |
| app-access-granter | reads `employee`, `identity_account`, `job_requisition`, `position` (registry: `access_role_template`, `job_profile`) |
| sso-identity-provisioner | within scope |
| termination-checklist-builder | writes `checklist_task` (registry writes `checklist` only) |
| cobra-trigger-detector | reads `employee`, `legal_entity` (registry: `termination`) |
| cobra-notice-generator | same module also reads `employee`, `legal_entity`, `termination`; registry reads none |
| vesting-schedule-tracker | reads `termination` (inside the closeout handler) |
| tax-withholding-calculator | reads `employee`, `legal_entity` (registry: `payroll_profile`, `pt_slab_rule`, `statutory_rate_rule`); `payroll_profile` is unused by the code |
| payroll-run-builder | writes `payslip_line`; reads `employee`, `employment_record`, `legal_entity`, `payslip`, via `app.open_payroll_run`, `record_payslip`, `finalize_payroll_run` (registry reads: none) |
| payslip-issuer | reads `payroll_run` (registry reads: none) |
| tax-filing-submitter | reads `legal_entity`, `payroll_run` (registry reads: `consent_record`, which the code does not read) |
| pto-accrual-calculator | reads `employee` (registry: `leave_policy`) |
| punch-validator | reads `approval_request` for `g_timecard` resolution |
| employee-record-writer | updates `job_requisition`; reads `job_profile` (registry has neither) |
| direct-deposit-disburser | the exit handler reads `employment_record`, `gratuity_accrual_balance`, `leave_balance` (that is final-pay-calculator's work) |

The pattern: the registry's `reads` come from the model's reader list and omit join and lookup tables
(`employee`, `legal_entity`, `job_requisition`, `position`) that every real flow needs. Those are
**Phase 1 blockers**: generating roles from the registry as-is would break about a dozen workers.
Either the registry gets `reads` additions (an authored change to `worker_classification.json` or a
documented generated baseline of join tables) or the roles get a shared "lookup" read set. I recommend the
first, reviewed per worker.

## 5. How roles interact with existing database objects

- **`app.current_app_role()`** (0001) maps `agent_%` to `agent_runtime`. Callers: `app.can_see_employee`
  (0001; lists `agent_runtime` among tenant-wide roles), `app.is_daydor_staff`, the audit `actor_role`
  defaults in 0005 and 0009, `app.resolve_approval` approver checks (0006), and the PII functions (0011).
  Worker roles must be treated like agents here (`worker_%` → a worker group), or person-scope RLS stops
  working for them.
- **`app.current_agent_role()`** returns the raw `agent_*` name and is used by 0011 to label audit rows
  `human` or `agent`. It would need to recognise `worker_%`.
- **RLS policies** in 0002/0003 use `app.tenant_id()` and `app.can_see_employee()`, not role names, apart
  from the grants. So policies need no change if `can_see_employee` is updated.
- **Grants**: 229 `agent_runtime` mentions in the generated 0003; `0021` (`open_payroll_run`,
  `record_payslip`, `finalize_payroll_run`), `0022` (`open_final_settlement`), `0011` (`encrypt_pii`,
  `decrypt_pii`), `0006` (`record_gate_evaluation`, `approval_allowed_roles`) and `0004` (`derived`) all
  grant to `agent_runtime`. Worker roles need the same EXECUTE grants (through the platform group).
- **PII registries** (0011): `collect_roles` and `allowed_roles` name `agent_hr`, `agent_ob`, `agent_pay`
  (the bug in section 1). They should be re-seeded with worker roles in a new migration; the registries
  are data, not generated, so this is a plain forward-only migration.
- **Hard gates**: no `agent_*` role can resolve an approval (`app.resolve_approval` checks the registry's
  approver roles, which are people). A negative test for worker roles must keep that true.
- **`grant_caps`**: `0024` only caps the employee role. The loader's `G` letter maps to `agent_runtime`;
  worker grants should derive from `access["G"]`, so any future `grant_caps` entry for `G` would apply
  to all workers at once.
- **Direct role names in code**: `APP_ROLES` in `db/session.py` (15 domain roles), `ALLOWED_AGENT_ROLES` in
  `daydor_api/sessions.py`, and `TENANT_WIDE_ROLES` in `model/loader.py` (contains `agent_runtime`).
- **Soft-gate registry columns**: the registry's `soft_gate` value for expense-policy-checker is the string
  `sg_expense_policy_precheck (proposed)`, which is not a real gate id; `app.worker_definition.soft_gate`
  cannot be a foreign key to `app.gate_definition` unless that value is cleaned. `SOFT_GATES` in
  `gates/registry.py` defines two (`sg_payroll_anomaly_precheck`, `sg_access_request_precheck`); only the
  first runs in code.

## 6. Migration plan and order

- Next free number is **0025**. Phase 1 takes 0025 onward, one migration per kickoff step, plus the data
  fixes below. Laya adoption follows afterwards and takes the next free number (decided).
- Suggested numbering (generated SQL files plus migration files, same shape as 0024):
  - 0025 `app.worker_definition` (generated from the registry, with a drift test)
  - 0026 `app.worker_tenant_policy` and the autonomy trigger
  - 0027 split `agent_runtime`: a platform group for the `app` objects; update `current_app_role`,
    `current_agent_role` and `can_see_employee` to recognise worker roles; re-seed the PII registries
  - 0028 the per-worker NOLOGIN roles and derived column grants (generated)
  - 0029 the guarded-column owner grants (can be inside 0028's generator, kept as its own migration if you
    want the review split)
  - 0030 remove the `agent_<domain>` roles after the API and tests have moved
- Things in Phase 1 that would make the Laya migration harder: none, as long as `app.gate_definition` and
  `app.record_gate_evaluation` are left alone. 0027's updates to `current_app_role` only touch role-name
  mapping. The decider migration will replace `record_gate_evaluation`, which already grants EXECUTE to
  `agent_runtime`; it should grant to the platform group instead, so it should be written after 0027.

## 7. Registry out of date or inconsistent with the repo

- `cobra-notice-generator` is wave 4 with no flows, but the exit flow already runs its job.
- `final-pay-calculator` home_domain `er` and `termination-checklist-builder` home_domain `ob`, `cobra-trigger-detector`
  `ben`, `new-hire-doc-collector` `ob`: the code registers them under other domains. Not wrong, but the
  per-worker roles make it moot.
- `reads` omissions listed in section 4.
- `payroll-run-builder` registry `writes` lacks `payslip_line` (the code writes it).
- Expense `soft_gate` value includes "(proposed)" (section 5).
- `tests/test_registry.py` hardcoded 6 two-writer guarded tables; I changed it to 7 because this repo's
  `0022` also guards `cobra_event.notice_sent_at`.

## 8. What I did not check

- Column-level conflicts between what the code writes and the model's `G` access. The generated matrix test
  in Phase 1 does this properly.
- Whether the 56 workers without code would need wider scope when built.
- The frontend API's tests under the new roles; I only read its role usage.

## 9. Decisions needed before Phase 1

1. **Frontend API.** Phase 1 changes `worker.py`, `sessions.py` (`ALLOWED_AGENT_ROLES`) and the 18
   `agent_session(...)` calls in `daydor-frontend/api`. Options: (a) change them in the same Phase 1 work,
   keeping both repos green; (b) keep `daydor-backend` only and leave the `agent_<domain>` roles in place
   (step 6 postponed) until a separate API change. Recommended: (b) first, with the new `worker_session()`
   helper and registry-driven `Worker` landing in the backend, then the API moves in a follow-up. This keeps
   step 6 out of Phase 1.
2. **Multi-worker handlers (section 2).** Split them into one handler per worker (cleanest, changes the
   workflows' job kinds and so the generated flow definitions), or give each such handler a documented
   combined role for now. Recommended: split `employee_closeout`, `cobra_trigger_detector` and the
   final-settlement pair; give `payroll/run_builder.py` a combined role for now with a TODO to split.
3. **Service calls with no handler** (payroll, timekeeping, benefits): add a `worker_session(worker_name)`
   helper (role taken from the registry, same fail-closed behaviour for a disabled worker) so API-started
   actions also run as the right worker. Recommended: yes.
4. **Registry `reads`.** Add the join and lookup tables per worker in `worker_classification.json` (reviewed
   change), versus a shared lookup role. Recommended: per-worker additions.
5. **PII fix.** The latent bug in section 1 gets fixed in Phase 1 (0027) by re-seeding the registries with
   worker roles, not by changing the check. Confirm.
6. **`agent_runtime` split** as in 0027, versus keeping `agent_runtime` and revoking from it per table.
   Recommended: the split.

## 10. Open decisions from the kickoff, untouched

Irreversible workers with no hard gate, candidate-screener and resume text, restricted-data policy and
shared-model training, `g_expense` and the leave guards, and the Laya adoption itself. Nothing here decides
them.

## 11. Decisions received (Oct 13 2026)

1. Frontend API: keep `daydor-backend` only; the `agent_<domain>` roles stay and step 6 (removing them) is postponed.
2. Multi-worker handlers: split as recommended; `payroll/run_builder.py` gets a combined role for now.
3. `worker_session(worker_name)` helper: yes.
4. Registry `reads`: add per-worker scope, **reviewed before implementation**: see `docs/registry-scope-proposal.md`.
5. PII registries: re-seed with worker roles in a migration (0027).
6. `agent_runtime`: split into a platform group and per-worker model grants.
