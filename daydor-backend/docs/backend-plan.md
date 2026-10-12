# Backend plan

Status: v1.4, Oct 11 2026. Build steps 1-7 done; Hire flow complete (Sprints 1-5); Payroll flow
complete (Sprints 6-9); Exit flow complete (Sprints 10-11, 125 tests passing). Validated against
the 82-table model in `model/daydor_model.json`. Sprint-by-sprint plan and status:
`docs/sprint-plan.md`.

## Principles

1. **The model is the source of truth.** Tables, row-level security, column grants, masked and
   aggregate views are generated from `model/daydor_model.json`. Tests fail on drift.
2. **The database enforces the rules.** Tenant isolation, column access, append-only tables,
   maker-checker and "no disbursal without an approved gate" are enforced in Postgres, so a
   buggy agent or service cannot bypass them.
3. **Agents never write raw SQL.** Each table has one owning domain service. Agents call services
   as their own database role (`agent_<domain>`).
4. **Every write is idempotent.** Agents retry, so commands carry an idempotency key.
5. **Hard gates stay human.** Jev runs only on soft gates, fails closed, and never sees C3/C4 data.

## Components

| # | Component | Decision |
|---|---|---|
| 1 | Session context | `SET LOCAL app.tenant_id / app.role / app.actor / app.purpose` per transaction |
| 2 | Write services | One owner per table, idempotency keys, outbox in the same transaction |
| 3 | Queue and timers | Postgres: `FOR UPDATE SKIP LOCKED` leases, retries with backoff, dead-letter (ADR-001) |
| 4 | State machines | Definitions and transitions stored as data, guarded by gates |
| 5 | Gate service | Registry of the 20 hard gates, `approval_request` as the record, DB-enforced maker-checker |
| 6 | Soft gates (Jev) | Typed questions, calibrated thresholds, `gate_evaluation` log, shadow mode first, fail closed |
| 7 | Privacy | `app.decrypt_pii(column, purpose)` checks consent and writes `audit_log`; per-tenant keys |
| 8 | Jurisdiction packs | Effective-dated `statutory_rate_rule` / `pt_slab_rule`; deterministic payroll code |
| 9 | Derived structures | `reporting_closure`, `employee_directory`, threshold recompute |
| 10 | Adapters | IdP, carriers, bank, E-Verify, tax filing, background checks, GL via outbox and webhook inbox |

## Build order

1. Model export and DDL generator
2. Platform schema: roles, session context functions, RLS, grants
3. Queue, outbox, timers
4. State-machine runner
5. Gate service and Jev soft-gate hook
6. Tests: access matrix, maker-checker, queue semantics, model drift

## Known model gaps (from validation)

Tables with no writing worker in the agent map. Each needs an owner (admin UI, seed, or
human-only service): `job_profile`, `comp_band`, `skill`, `benefit_plan`, `leave_policy`,
`course`, `certification`, `pt_slab_rule`, `statutory_rate_rule`, `retention_policy`,
`legal_hold`, `garnishment_order`, `access_role_template`, `valuation_409a`, `time_punch`,
`performance_review`, `consent_record` (employee-only, by design), `self_identification`
(employee-only, by design).

## Status

| Step | Status |
|---|---|
| 1. Model export and DDL generator | Done |
| 2. Platform schema: roles, session context, RLS, grants | Done |
| 3. Queue, outbox, timers | Done |
| 4. Gate service: hard gates, write guards, Jev soft gates | Done (Jev HTTP client is a stub) |
| 5. State-machine runner | Done (flow definitions are generated skeletons) |
| 6. Tests | 125 passing |
| 7. Privacy services | Done for the 4 encrypted `employee` columns (`0011_privacy.sql`) |
| 8. Hire flow, Sprints 1-5 of docs/sprint-plan.md (complete) | Done: position check → requisition → `g_requisition_budget` approval → job posting → application → screening (`g_aedt`) → interview → offer (`g_offer_band`) → background check (`g_bg_adverse`) → employee/employment_record creation → consent (`dpdp_consent`) → new-hire documents → work authorization (US-only, I-9/E-Verify timer) → onboarding checklist → SSO identity → access grant (`g_it_offtemplate`) → payroll profile, driven end to end through `WorkflowEngine` (`src/daydor/hire/`, `0012`-`0018`). Step 19 (payslip) is permanently out of the hire flow's scope -- see finding 15. |
| 9. Payroll flow, Sprint 6 of docs/sprint-plan.md | Done: leave accrual, timecard capture + manager approval (`g_timecard`, resolving finding 9), benefit elections (`src/daydor/timekeeping/`, `src/daydor/benefits/`, `0019_timecard_gates.sql`) |
| 10. Payroll flow, Sprint 7 of docs/sprint-plan.md | Done: jurisdiction-pack gross-to-net computation for India (PT/PF/TDS) and US (FICA/federal/state) (`src/daydor/payroll/`). Also fixed finding 18 (`statutory_rate_rule` rate precision, `0020_statutory_rate_precision.sql`) |
| 11. Payroll flow, Sprint 8 of docs/sprint-plan.md | Done: `payroll-run-builder` persists `payroll_run`/`payslip`/`payslip_line`/`gratuity_accrual_balance` (resolving finding 17); `sg_payroll_anomaly_precheck` soft gate always escalates to `g_pay_anomaly` in shadow mode; `g_pay_disburse` hard gate + mock bank adapter make disbursal provably impossible without an approved request; `payslip-issuer` refuses until disbursed (`src/daydor/payroll/run_builder.py`, `anomaly.py`, `disbursement.py`, `payslip_issuer.py`, `src/daydor/adapters/bank.py`). Fixed finding 19 (`derived` columns carry no grant at all; `0021_payroll_run_functions.sql`'s SECURITY DEFINER functions, same pattern as `daydor.privacy.pii`) |
| 12. Payroll flow, Sprint 9 of docs/sprint-plan.md (complete) | Done: `tax-filing-submitter` files one `filing_record` per statutory scheme (IN/US packs), idempotent, raises on an unregistered jurisdiction; `gl-poster` posts one summary `gl_journal_entry` per run, gated by `g_close` with the same create-then-gate shape as `g_pay_disburse` (`src/daydor/payroll/tax_filing.py`, `gl_posting.py`, `src/daydor/adapters/tax_filing.py`, `gl.py`). **Payroll flow is complete end to end**: accrue/punch/elect → compute → build run → anomaly screen → founder-approve → disburse → issue payslips → file → post to GL. |
| 13. Exit flow, Sprints 10-11 of docs/sprint-plan.md (complete) | Done: termination intake (HR admin), legal-hold check (`g_legalhold`, blocks IT deprovisioning while a hold is active), termination checklist, identity deprovisioning + access revocation (`g_it_deprov`), device return, final settlement calculation (`g_finalpay`) + creation + disbursal (`g_pay_disburse`, reusing Sprint 8's pattern), COBRA (`g_cobra`, US only), close-out (`src/daydor/exit/`, `0022_exit_gate_guards.sql`, `0023_exit_workflow.sql`). Driven by `WorkflowEngine` like the hire flow (long-lived, multi-week journey), with `g_it_deprov`/`g_pay_disburse`/`g_cobra` as direct guarded-column calls rather than engine-level gates -- see `daydor.exit.workflow`'s module docstring. Fixed finding 20 (`final_settlement`'s NOT NULL/derived-column gap, same shape as finding 19). **Exit flow is complete end to end.** |

## Next steps

See `docs/sprint-plan.md` for the sprint-by-sprint plan (Hire → Payroll → Exit, then hardening).
Miscellaneous items below aren't yet scheduled to a specific sprint:

1. **Push model deviations back into the artifact**: `approval_request.requested_by_*`/
   `decision_note` (finding 1), `employee`'s nullable PII columns (finding 10),
   `g_requisition_budget` (finding 11) — consolidated into sprint-plan.md Sprint 13.
2. **Decide finding 2** (employee self-write scope) and **finding 9** (manager-approval gates,
   partly resolved for timecards in sprint-plan.md Sprint 6; `g_expense` still open) — both in
   Sprint 12.
3. **Wire Jev** in `src/daydor/gates/jev.py` from TypeSafe's API docs once real API access
   exists; until then soft gates stay in shadow mode (Sprint 13 builds the shadow-vs-human
   comparison report).
4. **Enum value lists** in the model, then generated CHECK constraints (finding 5) — Sprint 12.
5. **Ops tenant assignment** (finding 6) and k ≥ 5 aggregate views starting with EEO-1
   (finding 7) — Sprint 13.
6. **Insert-time PII encryption** for append-only PII columns (`er_case_note.note_body`), once
   the ER case flow is built: needs a column-level INSERT grant plus a pure encrypt-and-return
   function, distinct from the UPDATE-based `app.encrypt_pii` used for `employee`.
7. **Production key management:** replace `app.pii_key`'s dev passphrase (one shared GUC) with
   per-tenant data keys from a KMS; it is the one function that needs to change.
8. **CI:** run `alembic upgrade head` and `pytest` against Postgres 16 on every push — Sprint 12.
