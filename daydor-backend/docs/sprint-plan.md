# Sprint plan

Status: **approved 2026-10-08; Sprints 1-11, 12a and 12b done, Hire, Payroll and Exit flows complete** (187
tests passing). v2: revised after re-reading
`docs/backend-plan.md` and `docs/model-findings.md` against the actual table `writers`/grants in
`model/daydor_model.json` — this surfaced real prerequisite work the first draft missed (see
"What changed from v1" at the bottom).

## End goal (from `model/source_artifact.html`, `docs/backend-plan.md`, `CLAUDE.md`)

Daydor is an HR platform for SMEs (50-100 employees) where **AI domain agents do the operational
work** — hiring, payroll, benefits, time/leave, performance, learning, ER/offboarding — across
India + US jurisdictions. Postgres, not the application, enforces tenant isolation, column-level
access by data sensitivity (C0-C4), maker-checker approval, consent-gated PII and full audit, so a
buggy or compromised agent cannot bypass the rules. The model defines 82 tables, 6 end-to-end
flows (**hire, payroll, exit, erasure, merit, threshold-crossing**), ~20 hard human gates, and a
soft AI gate service (originally Jev, now Laya per ADR-005) that may only fast-track a decision, never replace human approval on
a hard gate. `docs/backend-plan.md`'s 10 components (session context, write services, queue,
state machines, gates, soft gates, privacy, **jurisdiction packs**, derived structures, adapters)
are the architecture; the 6 flows are what that architecture is *for*.

The backend's job is to make each flow real: a domain service (a "worker" in the model) per
table, wired through the queue and the state-machine runner, gated correctly, auditable, and
tenant-isolated.

## Decisions this plan is built on (confirmed 2026-10-08)

1. **Flow priority: Hire → Payroll → Exit.** Erasure, merit and threshold-crossing are real flows
   in the model but are **backlog**, after Exit ships.
2. **All adapters are mocks for now** (IdP, bank, carriers, E-Verify, tax filing, background
   checks, GL, job boards). Every sprint that touches an adapter builds it behind a narrow
   interface with a fake implementation.
3. **The soft-gate engine stays a stub / shadow mode.** Jev was the original engine; ADR-005 (Oct 12 2026)
   replaces it with Laya, behind a `DeciderClient` interface. Neither is wired to a real model yet.
4. **Open-ended, iterate sprint by sprint.** Each sprint is sized to be independently reviewable
   and mergeable; the next sprint gets planned after the current one is approved and merged.

## What "done" means for a sprint

- `alembic upgrade head` + `pytest` green (currently 90 tests, Postgres 16).
- `docs/backend-plan.md`, `docs/model-findings.md` and this file updated: status flipped, new
  findings logged, next steps adjusted.
- A short demo-able capability stated in the sprint's "Exit criteria."

## Reference & admin-owned data — not a gap, no sprint needed

Finding 4 lists 18 tables with no agent writer (`job_profile`, `comp_band`,
`access_role_template`, `benefit_plan`, `leave_policy`, `statutory_rate_rule`, `pt_slab_rule`,
`garnishment_order`, `legal_hold`, ...). Checked each against its `table_acl`: `tenant_hr`/
`tenant_founder`/`tenant_payroll`/`tenant_it` already hold direct `WRITE` on the tenant-owned ones,
and `daydor_ops` already holds direct `WRITE` on the global statutory ones (`statutory_rate_rule`,
`pt_slab_rule` — Daydor, not the tenant, maintains jurisdiction packs). **These are admin-entered
by design, through grants that already exist; no domain service needs to be built.** The only
consequence for sprints below: demos should seed this data with a real `tenant_session(...,
"tenant_hr", ...)` / `"daydor_ops"` insert, not `tests.factories.insert` (which bypasses RLS and is
test-only).

---

## Sprint 0 — Foundations (Done)

- Model loader, DDL generator, platform roles, session context, RLS, grants (migrations 0001-0003)
- Reporting closure, employee directory, access + drift tests
- Postgres job queue, outbox, timers, business-day calendars (0005)
- Gate service: hard gates (DB-enforced maker-checker), write guards, soft-gate scaffolding (0006-0008)
- State-machine runner; the 6 flows as generated skeletons (0009-0010)
- Privacy services: `app.encrypt_pii`/`app.decrypt_pii`, purpose + consent registry, for
  `employee`'s 4 encrypted columns (0011)
- Hire flow step 1: `employee-record-writer` for `employee` + `employment_record` (0012), fixing
  finding 10 (PII columns must start NULL; consent needs the employee row to exist first)

---

## HIRE flow (Sprints 1-5, Done)

Model steps: `position(R) → job_requisition(W) → approval_request(W) → job_posting(W) →
application(W) → screening_result(W, g_aedt) → interview(W) → offer(W, g_offer_band) →
background_check(W, g_bg_adverse) → employee(W) → employment_record(W) → consent_record(W,
dpdp_consent) → document(W) → work_authorization(W) → checklist_task(W) → identity_account(W) →
app_access_grant(W, g_it_offtemplate) → payroll_profile(W) → payslip(W)`

`employee`/`employment_record` done (Sprint 0). `job_profile`/`comp_band`/`access_role_template`
needed along the way are admin-entered (see above), seeded directly, not built as services.

### Sprint 1 — Workflow data-passing + requisition intake (Done)
- **Infra:** `WorkflowEngine._enter` now puts the instance's full `context` dict into every
  entered state's enqueued job payload (`job.payload["context"]`), not just `subject_id` — a
  generic engine fix, not hire-specific, so every future flow gets it for free.
- **Infra:** `src/daydor/adapters/` (an `Adapter`-style convention: a narrow Protocol + a Fake
  implementation per vendor) and `src/daydor/agents/` (a placeholder for the future agentic
  worker harness, not wired into anything yet — see its docstring).
- `position` (read: `confirm_budgeted_seat`, hire flow step 1)
- `job_requisition` writer (`open_requisition`, step 2) and `job_posting` writer
  (`job-posting-publisher`, step 4) in `src/daydor/hire/`
- `requisition-approval-router` (step 3) — thin; the gate check itself lives on the state
  transition (see finding 11 below)
- Hand-written `daydor.hire.workflow.HIRE_DEFINITION` (version 2 of `app.workflow_definition`,
  superseding the generated skeleton for steps 1-4) and `start_hire()`, the orchestration entry
  point
- **Exit criteria (met):** `tests/test_hire_requisition.py` opens a requisition against a real
  `position`, gets it budget-approved through the hard-gate machinery, and publishes a posting —
  driven end to end through `WorkflowEngine` + the real queue, not called directly.

**Two new findings this sprint surfaced** (see `docs/model-findings.md`):
- **Finding 11:** no gate in the model covers requisition budget sign-off. Added
  `g_requisition_budget` as a platform-defined hard gate (`daydor.gates.registry.
  PLATFORM_HARD_GATES`), and placed it on the *outgoing* transition of the approval-routing
  state rather than the generated skeleton's convention (gate on the transition *entering* a
  gated step) — the model's placement reads backwards for this gate (you want approval checked
  after drafting, before posting, not before routing is even allowed to start).
- **Finding 12:** `id` columns never carry an INSERT grant for any role, so a workflow
  instance's subject (fixed at `start()`) can't be a row whose id is allocated after the
  instance starts. `start_hire()` creates `job_requisition` (DB-generated id) *before* starting
  the instance against it; the position-check and requisition-draft steps run synchronously
  ahead of the instance and appear as pass-through states purely for the transition log's audit
  trail. Any later sprint with the same shape (a step before its row exists) needs this pattern.

Also fixed a real, previously-latent bug in `tests/conftest.py`'s `_recreate_database`: it never
passed the port to its admin connection, so on any Postgres setup using a non-default port (ours,
since PG16 runs on 5433 alongside this machine's existing PG14 on 5432) the "fresh test database"
was silently never being recreated — `alembic`'s already-applied-migration bookkeeping then
masked any edit to an already-applied migration's SQL. Harmless for purely additive migrations
(which is all that existed before this sprint), but it would have silently hidden real bugs going
forward. Fixed by passing `port=u.port`.

### Sprint 2 — Screening, interview, offer (Done)
- `application`/`candidate` writer (`candidate-screener`, step 5: `intake_application`) and
  `screening_result` writer (same worker, step 6: `score_application`), gated by `g_aedt` — the
  screener is a deterministic placeholder (`src/daydor/hire/screening.py`), always flagged as
  needing sign-off since it *is* an automated hiring tool
- `interview` writer (`interview-scheduler`, step 7)
- `offer` writer (`offer-letter-generator`, step 8), gated by `g_offer_band` when
  `proposed_base` falls outside the `comp_band`
- Hire workflow definition bumped to version 3 (`0015_hire_workflow_v3.sql`), extending Sprint
  1's graph through offer; `s04_job_posting` no longer auto-advances (see finding 13) --
  `daydor.hire.screening.submit_application` is the real trigger, once a candidate exists
- **Exit criteria (met):** `tests/test_hire_screening.py` applies, screens (parked on `g_aedt`
  until HR signs off), interviews, and offers; an out-of-band offer correctly parks on
  `g_offer_band` for founder approval, an in-band one completes without it.

**One real engine bug found and fixed** (not hire-specific — affects every flow):
`WorkflowEngine._move()` entered the new state using the *old* `inst.context` instead of the
freshly merged context from `fire(..., context_patch=...)`, so a `context_patch` passed on the
same call that advances past a state was silently invisible to that state's own `enter_jobs`.
Sprint 1 never exercised this path (none of its transitions patched context and had `enter_jobs`
in the same `fire()` call); Sprint 2's `candidate_screener_intake` → `candidate_screener_assess`
handoff was the first to need both at once, and failed with a `KeyError` until fixed. Logged as
finding 14.

**Also found:** g_aedt's approver role is `tenant_hr`, not `tenant_founder` (per the model) --
caught by a test that resolved it as the wrong role, not by guessing. Added an `hr_user` to the
`hire_org` test fixture.

### Sprint 3 — Background check, employee creation, consent, documents (Done)
- `background_check` writer (`background-check-initiator`, step 9), gated by `g_bg_adverse` on
  its own outgoing transition (same correction as g_aedt/g_offer_band), mock
  `daydor.adapters.background_check` vendor adapter
- `employee`/`employment_record` writers (steps 10-11) wired into the real engine for the first
  time (`handle_employee_record_writer_create`/`_open` in `daydor.hire.employee_record`, built in
  Sprint 0 but only ever called directly from tests until now) -- another same-worker-two-kinds
  split, like candidate-screener in Sprint 2
- `consent_record` (step 12) has no agent writer by design (only the employee may grant their own
  consent); `daydor.hire.consent.request_consent` is the explicit trigger that checks the
  `dpdp_consent` gate once they have. Wired to the existing `daydor.privacy.pii` consent check, so
  the exact consent captured here is what `app.encrypt_pii` checks later
- `document` writer (`new-hire-doc-collector`, step 13) -- no adapter; local storage refs are data,
  not a vendor boundary
- Hire workflow bumped to version 4 (`0016_hire_workflow_v4.sql`), extending Sprint 2's graph
  through documents
- **Exit criteria (met):** `tests/test_hire_onboarding.py` proves an adverse background-check
  finding correctly escalates to HR before employee creation even starts, and that the employee
  row is created with its 4 PII columns NULL and only becomes readable through
  `app.encrypt_pii`/`app.decrypt_pii` after a real `consent_record` row exists and the
  `dpdp_consent` gate is resolved -- finding 10's fix, exercised for real for the first time.

### Sprint 4 — Work authorization, checklist, identity (Done)
- `work_authorization` writer (`i9-e-verify-initiator`, step 14): US-only, determined by reading
  the employee's own `legal_entity.country_code` rather than a context flag the caller must
  remember to set; mock `daydor.adapters.everify` adapter; schedules a real `app.timer` for the
  I-9 section 2 deadline via `app.add_business_days` against the `US-FED` calendar
- `checklist_task`/`checklist` writer (`onboarding-checklist-builder`, step 15): one `checklist`
  row plus a fixed 3-task template (documented as a simplification, not guessed-at business logic)
- `identity_account` writer (`sso-identity-provisioner`, step 16), mock `daydor.adapters.idp`
- Hire workflow bumped to version 5 (`0017_hire_workflow_v5.sql`), extending Sprint 3's graph
  through identity provisioning -- the hire flow's "done" here really is close to the model's own
  terminal state (only `app_access_grant`, `payroll_profile` and `payslip` remain for Sprint 5)
- **Exit criteria (met):** `tests/test_hire_identity.py` proves an India-based hire skips I-9/
  E-Verify entirely (no row created) while still getting a checklist and an SSO identity, and a
  US-based hire gets a real `work_authorization` row plus a real `app.timer` row for the I-9
  deadline that actually fires when due (not a placeholder never wired to anything).

### Sprint 5 — Access grant, payroll profile (Done)
- `app_access_grant` writer (`app-access-granter`, step 17), gated by `g_it_offtemplate` on its own
  outgoing transition (same correction as every other `requires_*` gate); off-template grants are
  still created immediately, same reasoning as g_aedt/g_offer_band/g_bg_adverse (see
  `daydor.hire.access_grant`'s docstring)
- `payroll_profile` writer (`employee-record-writer`, step 18) -- third split of that model
  worker under its own kind name, same pattern as steps 10/11
- **Finding 15, discovered this sprint: step 19 (`payslip`) is permanently out of the hire
  flow's scope**, not deferred to a later hire sprint. `payslip.payroll_run_id` is NOT NULL, and
  `payroll_run` is a per-period batch covering every employee on it, built end to end by Payroll's
  own sprints below (anomaly detection, disbursal gates). There is no "just this employee's first
  payslip" shortcut that doesn't duplicate or fake that machinery. The hire flow's engine-driven
  graph ends at step 18; this employee's first payslip is whatever Payroll Sprint 8 produces once
  a cycle including them runs.
- Hire workflow bumped to version 6 (`0018_hire_workflow_v6.sql`) -- **this is the hire flow's
  real, permanent terminal state.**
- **Exit criteria (met, revised per finding 15): the hire flow is demoable end to end** —
  requisition → screening → offer → background check → consent/onboarding → access →
  **payroll profile**, through domain services and the gate/queue/workflow machinery, for the
  full 18 steps that are actually the hire flow's responsibility.

---

## PAYROLL flow (Sprints 6-9)

Model steps: `timecard/leave_balance/employment_record/statutory_rate_rule/pt_slab_rule/
garnishment_order/benefit_election(R) → payroll_run(W) → payroll_run(R, g_pay_anomaly) →
approval_request(A, g_pay_disburse) → payroll_run(W, disburse) → payslip(W) → payslip_line(W) →
gratuity_accrual_balance(W) → filing_record(W) → gl_journal_entry(W, g_close)`

**This is bigger than it looks.** Four of payroll's seven read-inputs are not admin-entered rows
sitting ready to read — they are themselves written by workers nobody has built yet, and one of
those exposes a real gap (finding 9) that blocks it. Chasing this down is the main correction in
this revision; see Sprint 6 below.

### Sprint 6 — Payroll's own prerequisites: leave accrual, timecards, benefit elections (Done)
- `pto-accrual-calculator` (`src/daydor/timekeeping/leave.py`): writes `leave_balance`, linear
  accrual from `leave_policy.accrual_rule` (`{"days_per_month": N}`, a documented convention
  since the column is free-form jsonb), capped at `carry_forward_cap`. No recurring scheduler
  calls it yet (callable on demand, like every other "calculator" in this codebase); without this,
  "leave_balance(R)" in the payroll flow would have nothing real to read.
- `time_punch` is employee self-entered directly (table grant `E: WRITE`, same self-service
  pattern as `consent_record`, confirmed -- no service needed). `punch-validator`
  (`daydor.timekeeping.timecard.validate_timecard`) turns punches into `timecard` rows.
- **Resolves finding 9:** added `g_timecard` and `g_expense` to `PLATFORM_HARD_GATES`
  (`tenant_manager` approver), regenerated `0007_gate_seed.sql`, incremental
  `0019_timecard_gates.sql` for already-migrated databases. **Push both back into the artifact.**
  A timecard's approval isn't tracked by any `WorkflowEngine` instance (pay periods recur, there's
  no single start/end the way a hire has one), so `g_timecard`'s resolution needs its own delivery
  path: a second `gate.resolved` subscription on a new `'timekeeping'` queue, alongside the
  workflow engine's own. `daydor.timekeeping.timecard.handle_timekeeping_gate_resolved` ignores
  every gate resolution that isn't a `g_timecard`, the same way the engine's own handler no-ops
  for gates nothing is waiting on.
- **Finding 16, discovered this sprint: `benefit_election` is not actually employee
  self-service**, despite its table-level grant showing `E: WRITE` -- `coverage_tier` and
  `employee_cost` are C2-class, where the employee's own column access is READ, not WRITE (only
  HR/ops/agents can write them). This matches the model naming a real worker
  (`election-processor`) for this table, unlike `consent_record`/`time_punch`, which don't have
  one. `daydor.benefits.election.elect_benefit` runs as `agent_ben`, not the employee's own
  session; the employee can read their own election afterward.
- **Exit criteria (met):** `tests/test_timekeeping.py` proves an employee can punch time, have it
  validated into a timecard, and have it approved only through a real `g_timecard` gate
  resolution by a manager (not a bypass, and not by the employee themselves); leave accrues
  linearly and caps correctly; a benefit election is processed by an agent, not the employee
  directly, and is idempotent.

### Sprint 7 — Jurisdiction packs & deterministic tax computation (Done)
- `docs/backend-plan.md` component 8, not started before this sprint. `statutory_rate_rule`/
  `pt_slab_rule` are admin-entered (by `daydor_ops`, globally) — this sprint is the computation
  that reads them, not the rows.
- `gross-pay-calculator` (`src/daydor/payroll/gross_pay.py`), `tax-withholding-calculator`
  (`tax_withholding.py`, branches on the employee's own `legal_entity.country_code`, same pattern
  as `daydor.hire.work_authorization`'s I-9 check), `garnishment-processor` (`garnishment.py`,
  priority-ordered, never pushes net below zero) -- tax logic is explicitly **illustrative** (one
  flat rate per scheme, not real slabs/exemptions/YTD caps), scoped to one India case (PT slab +
  PF + flat TDS) and one US case (FICA + federal + one state withholding).
- **Finding 17, discovered this sprint: `payslip_line` cannot be written yet either** --
  `payslip_line.payslip_id` is NOT NULL and `payslip.payroll_run_id` is NOT NULL, the same shape
  as finding 15 one level down. `daydor.payroll.compute.compute_gross_to_net` returns a plain
  result object instead of row ids; Sprint 8's `payroll-run-builder` persists it once
  `payroll_run`/`payslip` rows exist to attach it to.
- **Finding 18, a real bug caught by an exact-amount test assertion, not inspection:** every
  numeric column in the generated DDL is `numeric(14,2)` (`daydor.model.ddl.SQL_TYPE`'s blanket
  mapping) -- correct for currency, but it silently rounded a real FICA rate (0.0765) to 0.08, a
  ~4.6% relative error in a legally mandated withholding. Widened
  `statutory_rate_rule.employee_rate`/`employer_rate` specifically to `numeric(8,6)`
  (`0020_statutory_rate_precision.sql`) -- a documented deviation from the generated DDL, not a
  `ddl.py` change (rates vs. amounts need their own physical-type distinction in the model to
  generate correctly, which is an artifact change).
- **Exit criteria (met):** `tests/test_payroll_compute.py` computes gross-to-net correctly for a
  hand-checked India case (PT + PF + TDS) and a hand-checked US case (FICA + federal + state),
  pulling real rates/slabs from `statutory_rate_rule`/`pt_slab_rule` with effective-dating proven
  by a rate-change test, not hardcoded numbers. Also proves garnishment priority ordering and an
  unsupported-jurisdiction case raises rather than silently skipping.

### Sprint 8 — Payroll run, anomaly gate, disbursal (Done)
- `payroll-run-builder` (`src/daydor/payroll/run_builder.py`): ties Sprints 6-7 together into
  `payroll_run` + `payslip` + `payslip_line` + `gratuity_accrual_balance` (India, illustrative flat
  rate) for every active employee under a legal entity, idempotent on `(legal_entity_id,
  period_start, period_end)`. Scope decision: not driven through `WorkflowEngine` — a payroll
  run's gates are checked via direct `run_soft_gate`/`request_approval` calls on the `payroll_run`
  row itself, the same pattern Sprint 6 uses for timecards, since `payroll_run.status` already
  carries the bookkeeping a workflow instance's `state` would for a flow this short.
- `payroll-anomaly-detector` (`src/daydor/payroll/anomaly.py`): soft gate
  `sg_payroll_anomaly_precheck`, always escalating to `g_pay_anomaly` in shadow mode.
- `g_pay_disburse` hard gate (founder approval) + `direct-deposit-disburser`
  (`src/daydor/payroll/disbursement.py`, `src/daydor/adapters/bank.py`'s `FakeBankAdapter`), using
  the existing `app.gate_guard` guarded-write pattern on `payroll_run.disbursed_at`.
- `payslip-issuer` (`src/daydor/payroll/payslip_issuer.py`): raises `PayrollRunNotDisbursed` until
  `disbursed_at` is set.
- Finding 19: `payroll_run`/`payslip`'s derived total columns carry no role's INSERT/UPDATE grant
  at all; added `migrations/sql/0021_payroll_run_functions.sql`'s SECURITY DEFINER functions
  (`app.open_payroll_run`, `app.record_payslip`, `app.finalize_payroll_run`), same pattern as
  `daydor.privacy.pii`.
- **Exit criteria (met):** `tests/test_payroll_run.py` proves disbursal is impossible without an
  approved `g_pay_disburse` request — attempting `disburse_payroll_run` against a still-pending or
  a bogus approval id raises (DB-enforced, not app-side), approving it as founder then lets
  disbursal through, and `issue_payslips` refuses until that disbursal has actually happened.

### Sprint 9 — Filings and GL (Done)
- `tax-filing-submitter` (`src/daydor/payroll/tax_filing.py`): one `filing_record` row per
  statutory scheme for the payroll run's jurisdiction (IN: ecr, 24q; US: 941, w2, state_ui),
  idempotent on `(legal_entity_id, scheme, period)`; raises `UnsupportedJurisdiction` (reused from
  `daydor.payroll.tax_withholding`) for any other country rather than silently skipping. Mock
  adapter: `src/daydor/adapters/tax_filing.py`.
- `gl-poster` (`src/daydor/payroll/gl_posting.py`): `gl_journal_entry`, gated by `g_close`, same
  "create the row with the guarded column NULL, then gate the UPDATE" shape as
  `daydor.payroll.disbursement`'s `g_pay_disburse` — `app.enforce_gate_guard` checks the
  approval's `subject_id` against the row's own id, so the row must already exist and be known
  before an approval can be requested against it. One illustrative summary line per run (debit
  payroll expense, credit cash, net amount), not a full chart-of-accounts posting. Mock adapter:
  `src/daydor/adapters/gl.py`.
- **Exit criteria (met): Payroll is demoable end to end** — accrue/punch/elect → compute → build
  run → anomaly screen → founder-approve → disburse → issue payslips → file → post to GL
  (`tests/test_payroll_filing_gl.py` proves filing and GL posting; `tests/test_payroll_run.py`
  proves the rest of the chain up to and including payslip issuance).

---

## EXIT flow (Sprints 10-11)

Model steps: `termination(W) → legal_hold(R, g_legalhold) → checklist(W) → identity_account(W,
g_it_deprov) → device_assignment(W) → leave_balance/gratuity_accrual_balance(R) →
final_settlement(W, g_finalpay) → approval_request(A, g_pay_disburse) → final_settlement(W,
disburse) → cobra_event(W, g_cobra) → vesting_event(R) → termination(W) → employee(W)`

`legal_hold` is admin-entered (`tenant_hr`/`tenant_founder` direct write, see above — no service
needed, just a real row to check against). `vesting_event` is read-only here and may legitimately
be empty (equity/vesting is written by Merit's backlogged `grant-drafter`/`vesting-schedule-
tracker`) — treat an employee with no equity as a normal case, not a bug.

### Sprint 10 — Termination intake, holds, deprovisioning (Done)
- `termination` writer (HR admin-initiated, `src/daydor/exit/termination.py`'s `initiate_termination`)
- Legal-hold check (`g_legalhold`) before anything else proceeds: `src/daydor/exit/legal_hold.py`'s
  `handle_legal_hold_checker`, the model's "root orchestrator" -- the flow itself checks
  `legal_hold`, not a domain agent, and only gates (natively, via `WorkflowEngine`, conditional on
  `requires_g_legalhold`) when a hold is actually active.
- `checklist` writer (termination-checklist-builder, `src/daydor/exit/checklist.py`, reusing the
  hire flow's `checklist`/`checklist_task` tables with `kind='termination'`)
- `identity_account`/`app_access_grant` revocation (deprovisioning-agent,
  `src/daydor/exit/deprovisioning.py`), gated by `g_it_deprov` -- **not** an engine-level transition
  gate (see `daydor.exit.workflow`'s module docstring point 2 for why): `request_deprovisioning_approval`
  opens the request against `identity_account`'s own id, `deprovision_identity` is the only thing
  that can set `deprovisioned_at` (DB-enforced via `app.enforce_gate_guard`) and is what actually
  advances the workflow instance.
- `device_assignment` writer (equipment-return-tracker, `src/daydor/exit/device_return.py`)
- **Exit criteria (met):** `tests/test_exit_flow.py::test_termination_under_active_legal_hold_is_blocked_from_it_deprovisioning`
  proves a termination under an active legal hold parks at `s02_legal_hold_check` -- the instance
  never reaches `s04_identity_account`, so IT deprovisioning is structurally unreachable until the
  hold is released and `g_legalhold` is approved.

### Sprint 11 — Final settlement, COBRA, close-out (Done)
- `final-pay-calculator`: reads `leave_balance` + `gratuity_accrual_balance` (both real since
  Sprint 6/8), computes the settlement (`src/daydor/exit/final_settlement.py`'s
  `calculate_final_settlement`), gated by `g_finalpay` (native engine gate -- the amounts are only
  known once this step runs, same "gate the outgoing transition" correction hire uses for
  `g_aedt`/`g_offer_band`), then writes `final_settlement` via `app.open_final_settlement` once
  approved, then disburses via `g_pay_disburse`, reusing Sprint 8's direct-call guarded-write
  pattern exactly (not rebuilt).
- `cobra-trigger-detector`: `cobra_event` (`src/daydor/exit/cobra.py`), gated by `g_cobra` (US
  only -- no-ops for other jurisdictions, same convention as I-9/tax-filing jurisdiction checks).
- `vesting-schedule-tracker` (read, may be empty -- equity is Merit's backlog, not this flow's),
  `rehire-eligibility-flagger`, final `employee` close-out (`is_active = false`, `date_of_exit`;
  all three in `src/daydor/exit/closeout.py`).
- Finding 20: `final_settlement.approval_request_id` was modelled NOT NULL and
  `total_settlement` is `derived` -- same "can't reference what doesn't exist yet" shape as
  findings 10/19. Relaxed to nullable plus a new `app.open_final_settlement` SECURITY DEFINER
  function (`migrations/sql/0022_exit_gate_guards.sql`), same pattern as `app.open_payroll_run`.
  Also corrected `final_settlement.disbursed_at`'s gate_guard from `g_finalpay` to
  `g_pay_disburse` (matching the model's own `g_pay_disburse.tables` list) and added
  `cobra_event.notice_sent_at`'s missing `g_cobra` guard.
- **Exit criteria (met): Exit is demoable end to end** —
  `tests/test_exit_flow.py::test_exit_flow_end_to_end_settlement_disbursal_and_closeout` drives
  termination through legal-hold check, checklist, deprovisioning (`g_it_deprov`), device return,
  final settlement calculation (`g_finalpay`), settlement creation, disbursal (`g_pay_disburse`,
  provably impossible without an approved request -- same proof shape as Sprint 8), COBRA check
  and close-out (`employee.is_active = false`); `test_cobra_notice_is_impossible_without_an_approved_g_cobra_request`
  covers the US-only COBRA gate separately.

---

## Phase 1: worker registry and per-worker roles (Done Oct 13 2026)

Built from `docs/claude-code-kickoff.md` after the Phase 0 reconciliation (`docs/worker-roles-reconciliation.md`)
and the reviewed scope additions (`docs/registry-scope-proposal.md`). 276 tests pass, also with
a test-only switch that ran queue handlers on worker roles (since removed: every test now uses worker roles).

- `registry/worker_classification.json` gained a reviewed `extra_scope` per worker, plus
  `registry/platform_actors.json` (workflow-engine, root-orchestrator); `daydor.agents.registry` merges and validates.
- `0025` `app.worker_definition` (generated), `0026` `app.worker_tenant_policy` and `app.assert_worker_enabled`,
  `0027` `worker_platform`, worker-aware role functions and the PII role-check fix (finding 24), `0028` one NOLOGIN
  role per worker with derived column grants and the PII registry seeds, `0029` exit workflow version 3 (inactive).
- `daydor.agents.roles` (generator and rules), `daydor.agents.session.worker_session`, `Worker.register(worker=...)`.
- **Follow-up done the same day (API move):** the API's worker process and 18 router actions run on worker roles, exit workflow
  version 3 is active (`0033`), and the `agent_<domain>` roles are dropped (`0034`) after every backend test moved off them.

---

## Cross-cutting hardening (Sprints 12-13)

### Sprint 12a — Employee write scope, finding 2 (Done)
- **Problem (verified, not assumed):** the model gives the employee role W on every `employee` column,
  and the generated grants matched it. A signed-in employee could `UPDATE` their own `is_active`,
  `date_of_exit`, `legal_entity_id` (payroll derives the tax jurisdiction from it), `department_id`,
  `position_id`, `date_of_joining`, `work_email`. The new tests failed against the old grants.
- **Decision (default, easy to change):** an employee self-edits `personal_address` only. Everything
  else on `employee` is HR-owned -- `full_name`, `date_of_birth` and `aadhaar_last4` included, since they
  feed identity verification and KYC. Corrections go through `tenant_hr` or `employee-record-writer`.
  To widen it, add the column to `except` in `grant_caps` and regenerate.
- **Mechanism:** a new `grant_caps` section in `model/extensions.json` (`table`, `role`, `cap`,
  `except`, `reason`). `daydor.model.loader` applies it (the model, the grant-matrix test and the
  frontend contract all see the capped access). Because applied migrations are never edited and
  `0003` is pinned to the model by the drift test, the baseline grants are still generated from the
  *uncapped* model and the cap lands as a separate generated migration, `0024_model_grant_caps.sql`
  (the same generated-baseline-plus-incremental shape as gates `0007` + `0013`). `0002`/`0003` are
  byte-identical.
- The frontend's `gen-contract.mjs` applies the same rule, so the UI shows employees as read-only on
  those fields and CI's contract-drift job stays green.
- **Exit criteria (met):** `tests/test_employee_self_service.py` -- an employee is refused on each of the
  14 HR-owned columns (self-assignment is enough, Postgres checks the privilege per column in `SET`),
  cannot deactivate themselves or change legal entity, cannot insert an `employee` row or edit a
  colleague's address, can still edit their own address; HR and agents are unaffected.

### Sprint 12b — Employee over-grants on workflow-owned columns, finding 23 (Done)
- Same hole as 12a on seven more tables, verified against live grants first. Per-table calls: an
  employee keeps only what they author. `timecard`, `checklist`, `training_assignment`: read-only
  (agents/managers own them). `expense`, `leave_request`, `benefit_election`, `life_event`: only the
  system-owned and approval/payout columns are capped (the loader's new `columns` form of `grant_caps`
  caps just those columns). Regenerated into the still-unreleased `0024` (never applied outside the
  throwaway test DB; dev DBs were at 0023), so no `0025` was needed.
- **Exit criteria (met):** `tests/test_employee_self_service.py` checks 17 capped columns (UPDATE and
  INSERT privilege, plus Postgres' own parse-time permission error), 13 authored columns that must stay
  writable, and that agents and HR keep the access the flows need. 178 backend tests pass; the
  grant-matrix and drift tests cover the generated SQL.
- **Not done, on purpose:** gate guards on `expense.reimbursed_at` (`g_expense`) and
  `leave_request.status`/`fmla_designation` (`g_fmla`). No service writes those columns yet, so a guard
  would be untestable; add it with the expense and leave services.

### Sprint 12c — Hire flow loose ends (Done)
- **Seat filled at hire completion.** `daydor.hire.employee_record.fill_seat` runs in step 18's handler:
  `position.status = 'filled'` with `current_employee_id` set (only while still vacant) and
  `job_requisition.status = 'filled'`. `open_requisition` already refuses a position that is not open and
  vacant, so a filled seat can no longer be hired for twice. An unfinished hire leaves the position open.
- **`sg_access_request_precheck` is invoked.** `grant_app_access` runs it on every off-template (manual)
  grant (inputs: app name, permission level, job title; all C0). It is called with
  `open_approval=False` (new `run_soft_gate` argument) so one escalation stays one approval: the hire
  flow still opens `g_it_offtemplate` on leaving step 17, now only if some grant escalated. Shadow mode
  and a failing or unwired Jev still escalate, so IT reviews every off-template grant until the gate
  is enforced (needs the Laya calibration work in ADR-005).
- **`i9_section2_due` has a consumer.** `handle_i9_section2_due` (registered on the API worker's `hr`
  queue) emits `i9.section2_overdue` when section 2 is still not completed and the employee is still
  active. The timer fires once, so the event is not repeated. Nothing subscribes to the event yet.
- No migration. `tests/test_hire_loose_ends.py` (9 tests); 187 backend tests, 59 API, 111 frontend. The API's
  `provisional.json` enum file was regenerated for the new `filled` values.

### Sprint 12 — Grants, constraints, CI
- Narrow `agent_runtime` into per-domain agent roles (finding 3), using the worker → domain map
  that now actually exists from Sprints 1-11
- ~~Decide finding 2~~ -- done as Sprint 12a below
- Enum value lists in the model → generated CHECK constraints (finding 5)
- CI: `alembic upgrade head` + `pytest` against Postgres 16 on every push

### Sprint 13 — Ops scoping, aggregate views, remaining timers, shadow report, model sync
- `daydor_ops` → assigned-tenant table + RLS check (finding 6)
- Aggregate-only (k ≥ 5 suppression) views for level-1 access, starting with EEO-1 (finding 7)
- Remaining statutory timers not already covered: COBRA follow-ups, 409A staleness, work-
  authorization/certification expiry, threshold-crossing deadlines
- Shadow-mode comparison report: for every soft gate run in shadow mode so far (`g_aedt`,
  `g_pay_anomaly`), compare `app.gate_evaluation.model_decision` against the human's actual
  decision, so there is real data for Laya calibration (ADR-005)
- **Laya adoption (ADR-005):** `DeciderClient`/`LayaClient` and the `calibration_version` migration are done (0030, Oct 13);
  still to do: pinned/vendored checkpoint and smoke test, labelled-example store, calibration pipeline
- **Model artifact sync:** push every local deviation back into `model/source_artifact.html` and
  re-export, in one pass, now that they've all stabilized: finding 1's `approval_request` columns,
  finding 10's nullable PII columns, Sprint 6's `g_timecard`/`g_expense` gates, and whatever Sprint
  12 decides for finding 2. Doing this once, after things settle, beats touching the artifact
  every sprint.

---

## Backlog (after Exit ships; re-prioritize then)

- **Erasure flow** (DPDP data-subject request): anonymize what's erasable, hold what statute
  requires, prove it
- **Merit flow** (comp cycle): review cycle → ratings → calibration → comp-band-validated
  compensation events → new effective-dated `employment_record`, gated by `wage_structure_change`
  and `g_409a` for equity (this is also what eventually populates real `vesting_event` data)
- **Threshold-crossing flow**: headcount crosses a statutory scheme threshold → obligation
  registered → founder-approved → filed, before the deadline
- **Webhook inbox** (component 10): every adapter is a synchronous in-process mock through Sprint
  13, so nothing has needed an inbound-callback path yet. Build it when a real vendor integration
  (the first one that calls back async — e.g. a background-check result or a bank disbursal
  confirmation) actually replaces a mock.

---

## Open risks to revisit as we go

- The hire-flow hand-written definition (Sprint 1) sets the pattern every later flow definition
  follows — worth reviewing carefully before Sprint 2, since mistakes there compound.
- Mocked adapters mean none of this is tested against real vendor failure modes (rate limits,
  partial failures, auth expiry). Flag clearly in each sprint's PR description.
- `g_pay_disburse` appears in both Payroll (Sprint 8) and Exit (Sprint 11) — Sprint 8 builds the
  reusable guarded-disbursal pattern once, Sprint 11 reuses it.
- Sprint 7's tax computation is explicitly illustrative, not compliance-grade — don't let it get
  mistaken for certified payroll tax logic in a demo.

---

## What changed from v1 (after re-reading backend-plan.md / model-findings.md)

- **Payroll grew from 3 sprints to 4.** The original plan assumed `timecard`, `leave_balance` and
  `benefit_election` were just rows to read; checking the model's `writers` lists showed
  `leave_balance` and `timecard` are themselves worker-written, and `timecard`'s approval step
  depends on finding 9 (no gate models the manager as approver) — a real blocker, not a nice-to-
  have, so it's now Sprint 6 instead of hardening-sprint backlog.
- **Jurisdiction packs (component 8) got its own sprint** (7) instead of being folded silently into
  "payroll run compute" — it's real tax-computation work, not data plumbing.
- **Finding 4 resolved as "no work needed," explicitly documented** — the 18 writerless tables
  already have direct grants to human roles; only the demo-seeding convention changes.
- **Finding 2 moved from unstated to an explicit decision point** in Sprint 12, since it's a real
  open product/security question, not something to guess silently.
- **Added a model-artifact-sync pass** (Sprint 13) consolidating findings 1, 9, 10 and whatever
  Sprint 12 decides for finding 2, instead of leaving "push back into the artifact" as a vague,
  never-scheduled line item.
- **Added "webhook inbox" to backlog** (component 10's other half, alongside adapters) — not
  needed while every adapter is a synchronous mock, but it's a real gap once one isn't.
