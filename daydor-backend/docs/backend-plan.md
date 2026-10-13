# Backend plan

Status: v1.5, Oct 13 2026. Worker registry and per-worker roles built (Phase 1, below). Build steps 1-7 done; Hire flow complete (Sprints 1-5); Payroll flow
complete (Sprints 6-9); Exit flow complete (Sprints 10-11), findings 2 and 23 closed (Sprints 12a-12b), 276 tests passing. Validated against
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
5. **Hard gates stay human.** The soft-gate engine (Laya, ADR-005) runs only on soft gates, fails closed,
   starts in shadow mode, cannot enforce without a calibration, and never sees C3/C4 data.

## Components

| # | Component | Decision |
|---|---|---|
| 1 | Session context | `SET LOCAL app.tenant_id / app.role / app.actor / app.purpose` per transaction |
| 2 | Write services | One owner per table, idempotency keys, outbox in the same transaction |
| 3 | Queue and timers | Postgres: `FOR UPDATE SKIP LOCKED` leases, retries with backoff, dead-letter (ADR-001) |
| 4 | State machines | Definitions and transitions stored as data, guarded by gates |
| 5 | Gate service | Registry of the 20 hard gates, `approval_request` as the record, DB-enforced maker-checker |
| 6 | Soft gates (Laya, ADR-005) | `DeciderClient` interface, typed questions, thresholds on `answer_confidence` only, calibration required to enforce (`0030`), `gate_evaluation` log, shadow mode first, fail closed. Built; `LayaClient` smoke-tested against a real pinned checkpoint Oct 13 (`docs/laya-runbook.md`), shadow only |
| 7 | Privacy | `app.decrypt_pii(column, purpose)` checks consent and writes `audit_log`; per-tenant keys. Role checks use `app.current_actor_role()` (finding 24) |
| 8 | Jurisdiction packs | Effective-dated `statutory_rate_rule` / `pt_slab_rule`; deterministic payroll code |
| 8b | Worker registry and roles | 89 workers + 2 platform actors in `app.worker_definition`; per-tenant `worker_tenant_policy` (a tenant may only lower autonomy); one `worker_<name>` role per worker with derived column grants; `worker_platform` group; fail-closed `app.assert_worker_enabled` (ADR-004, `0025`-`0029`) |
| 9 | Derived structures | `reporting_closure`, `employee_directory`, threshold recompute |
| 10 | Adapters | IdP, carriers, bank, E-Verify, tax filing, background checks, GL via outbox and webhook inbox |

## Build order

1. Model export and DDL generator
2. Platform schema: roles, session context functions, RLS, grants
3. Queue, outbox, timers
4. State-machine runner
5. Gate service and soft-gate hook
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
| 4. Gate service: hard gates, write guards, Jev soft gates | Done (Jev HTTP client is a stub; Laya replaces it, ADR-005, not built) |
| 5. State-machine runner | Done (flow definitions are generated skeletons) |
| 6. Tests | 187 passing |
| 7. Privacy services | Done for the 4 encrypted `employee` columns (`0011_privacy.sql`) |
| 8. Hire flow, Sprints 1-5 of docs/sprint-plan.md (complete) | Done: position check → requisition → `g_requisition_budget` approval → job posting → application → screening (`g_aedt`) → interview → offer (`g_offer_band`) → background check (`g_bg_adverse`) → employee/employment_record creation → consent (`dpdp_consent`) → new-hire documents → work authorization (US-only, I-9/E-Verify timer) → onboarding checklist → SSO identity → access grant (`g_it_offtemplate`) → payroll profile, driven end to end through `WorkflowEngine` (`src/daydor/hire/`, `0012`-`0018`). Step 19 (payslip) is permanently out of the hire flow's scope -- see finding 15. |
| 9. Payroll flow, Sprint 6 of docs/sprint-plan.md | Done: leave accrual, timecard capture + manager approval (`g_timecard`, resolving finding 9), benefit elections (`src/daydor/timekeeping/`, `src/daydor/benefits/`, `0019_timecard_gates.sql`) |
| 10. Payroll flow, Sprint 7 of docs/sprint-plan.md | Done: jurisdiction-pack gross-to-net computation for India (PT/PF/TDS) and US (FICA/federal/state) (`src/daydor/payroll/`). Also fixed finding 18 (`statutory_rate_rule` rate precision, `0020_statutory_rate_precision.sql`) |
| 11. Payroll flow, Sprint 8 of docs/sprint-plan.md | Done: `payroll-run-builder` persists `payroll_run`/`payslip`/`payslip_line`/`gratuity_accrual_balance` (resolving finding 17); `sg_payroll_anomaly_precheck` soft gate always escalates to `g_pay_anomaly` in shadow mode; `g_pay_disburse` hard gate + mock bank adapter make disbursal provably impossible without an approved request; `payslip-issuer` refuses until disbursed (`src/daydor/payroll/run_builder.py`, `anomaly.py`, `disbursement.py`, `payslip_issuer.py`, `src/daydor/adapters/bank.py`). Fixed finding 19 (`derived` columns carry no grant at all; `0021_payroll_run_functions.sql`'s SECURITY DEFINER functions, same pattern as `daydor.privacy.pii`) |
| 12. Payroll flow, Sprint 9 of docs/sprint-plan.md (complete) | Done: `tax-filing-submitter` files one `filing_record` per statutory scheme (IN/US packs), idempotent, raises on an unregistered jurisdiction; `gl-poster` posts one summary `gl_journal_entry` per run, gated by `g_close` with the same create-then-gate shape as `g_pay_disburse` (`src/daydor/payroll/tax_filing.py`, `gl_posting.py`, `src/daydor/adapters/tax_filing.py`, `gl.py`). **Payroll flow is complete end to end**: accrue/punch/elect → compute → build run → anomaly screen → founder-approve → disburse → issue payslips → file → post to GL. |
| 13. Exit flow, Sprints 10-11 of docs/sprint-plan.md (complete) | Done: termination intake (HR admin), legal-hold check (`g_legalhold`, blocks IT deprovisioning while a hold is active), termination checklist, identity deprovisioning + access revocation (`g_it_deprov`), device return, final settlement calculation (`g_finalpay`) + creation + disbursal (`g_pay_disburse`, reusing Sprint 8's pattern), COBRA (`g_cobra`, US only), close-out (`src/daydor/exit/`, `0022_exit_gate_guards.sql`, `0023_exit_workflow.sql`). Driven by `WorkflowEngine` like the hire flow (long-lived, multi-week journey), with `g_it_deprov`/`g_pay_disburse`/`g_cobra` as direct guarded-column calls rather than engine-level gates -- see `daydor.exit.workflow`'s module docstring. Fixed finding 20 (`final_settlement`'s NOT NULL/derived-column gap, same shape as finding 19). **Exit flow is complete end to end.** |

## Soft gates with Laya (ADR-005, decided Oct 12 2026; interface and database rules built Oct 13)

Laya (Convai Innovations, Apache-2.0, `pip install laya`) is a bidirectional encoder (ModernBERT-large 421M or
mmBERT-base 322M) plus a decision head. It reads a state and typed questions and returns typed answers with
probabilities in one forward pass (`choice`, `score`, `noul`). It never generates text. It runs in our process
or in a `laya-serve` service, with no API key. Replaces Jev, which sent data to a third party.

Quality caveats (from Laya's own model card; only our own shadow data counts as evidence): base checkpoints are
near chance zero-shot (0.36 vs a 0.46 majority baseline) and ship over-confident (ECE 0.47, 0.08 after a
per-question-type temperature fit). On CPU, latency is 193 to 464 ms, no faster than Jev; 33 to 40 ms on a T4.

### Rules
1. Threshold on `answer_confidence` only. Ignore `confidence` and `action.act_probability`.
2. No enforcing without a calibration. Temperatures are fitted per (question type, option count) on held-out
   labelled data from our domain. The DB refuses `mode='enforce'` without a `calibration_version` and records
   which calibration decided each evaluation.
3. Pin the model: refuse to load unless `LAYA_REVISION` is set; production vendors weights, sets
   `LAYA_SHA256_DIGESTS` and `HF_HUB_OFFLINE=1`. Store repo and revision on every evaluation.
4. Truncation fails closed: refuse over-long states, treat any truncation report as an error.
5. Yes/no is sent as a two-option choice with neutral keys (laya issue 156).
6. At most 20 options per question; split larger sets hierarchically.
7. Language guard: gates that may see non-English text use the multilingual checkpoint, with a held-out slice per
   language, and escalate on unsupported languages.
8. Fine-tuning is the plan, not an option.
9. A decider must beat a rule baseline (for payroll, a z-score threshold) on held-out data before it may enforce.

### Restricted data (proposal, not implemented)
Running locally removes the vendor-transfer reason for keeping restricted data from the engine, but the
discrimination, purpose-limitation and self-identification reasons remain. Proposal: C4 and encrypted columns
are never inputs; C3 is closed by default and opens per gate only through a recorded decision, local model
only, with its own bias audit. Today the code refuses both. LLM workers keep the strict rule for C3 and C4.

### Deployment
Now: in-process `LayaClient` in the few workers that run soft gates (about 0.65 to 0.8 GB of weights per
checkpoint, preloaded; CPU is fine off the hot path; needs PyTorch via an optional extra). Later: a shared
`laya-serve`. It binds `0.0.0.0` with no authentication by default, so bind it privately and set `LAYA_API_KEY`.

### Labels and promotion to enforce
- Labels come from shadow mode: each shadow evaluation is paired with the human outcome on the hard gate it
  escalated to (`approval_request.status`). Gate inputs are not stored today (hash only), so training needs a
  separate, access-controlled, retention-limited example store, enabled per gate. Until enough labels exist,
  every gate escalates.
- Proposed starting points, set per gate with its owner: at least 300 labelled shadow decisions (50 of the rarer
  label); held-out ECE of 0.10 or lower per language slice; beats the rule baseline; fewer than 1% human
  disagreements on auto-passed decisions; two clean weeks in shadow after the last model or calibration change;
  a named owner signs off, recorded as the `calibration_version`.
- Open: may one tenant's decisions train a model serving other tenants? Recommended default: no, without an
  explicit contractual opt-in.

### Soft gates in this repo
`sg_payroll_anomaly_precheck` (then `g_pay_anomaly`; question `run_looks`: normal or unusual) and `sg_access_request_precheck` (then `g_it_offtemplate`; question `request_looks`) are wired
today. Candidates: an expense-policy precheck and a
shadow-only candidate screener (regulated, resume is C3; `g_aedt` stays human).

### Risks
Young project (0.4.x, one organisation, self-reported benchmarks): mitigated by `DeciderClient`, pinned and
vendored weights, and our own evals. Weights come from Hugging Face (supply chain). Confirm base encoder
licences in legal review. Known upstream issues on `noul` and `act_probability`.

### Worker roles (Phase 1, built Oct 13 2026)

| Step | Status |
|---|---|
| 1. `app.worker_definition`, generated from `registry/` | Done (`0025`) |
| 2. `app.worker_tenant_policy`, autonomy trigger, `app.assert_worker_enabled` | Done (`0026`) |
| 3. Per-worker NOLOGIN roles, derived column grants, `worker_platform` group | Done (`0027`, `0028`) |
| 4. Guarded columns only to named owners (`GUARD_OWNERS`) | Done (in `0028`) |
| 5. `worker_session`, queue `Worker.register(worker=...)`, `SessionContext` accepts worker roles | Done |
| 6. Remove the `agent_<domain>` roles | Done Oct 13 (`0034`): the API (`worker.py`, `sessions.py`, 18 router calls, `seed_dev`) and every backend test moved to worker roles first. `agent_runtime` stays, inert, as the model's agent access level |
| Exit close-out split into one handler per worker | Done: `0029` inserted version 3 inactive, `0033` activated it once the API registered the handlers (finding 27) |

Still open from the reconciliation (`docs/worker-roles-reconciliation.md`): `payroll/run_builder.py` is split later
(combined scope until then). The API move is done (steps 1 to 3, Oct 13): handlers register by worker, 18 actions use
`worker_session`, exit v3 is active, and the domain roles are dropped.

## Next steps

See `docs/sprint-plan.md` for the sprint-by-sprint plan (Hire → Payroll → Exit, then hardening).
Miscellaneous items below aren't yet scheduled to a specific sprint:

1. **Push model deviations back into the artifact**: `approval_request.requested_by_*`/
   `decision_note` (finding 1), `employee`'s nullable PII columns (finding 10),
   `g_requisition_budget` (finding 11) — consolidated into sprint-plan.md Sprint 13.
2. ~~Finding 2~~ closed in Sprint 12a (`grant_caps`, `0024`); finding 23 (the same over-grant on other tables' workflow-owned columns) closed in Sprint 12b. **Finding 9** (manager-approval gates,
   partly resolved for timecards in sprint-plan.md Sprint 6; `g_expense` still open) — both in
   Sprint 12.
3. **Laya**: interface, runner, `calibration_version` migration (0030) and the real-checkpoint smoke test are done.
   Remaining: production pinning and vendoring, the labelled-example store, calibration and the shadow-vs-human report
   (Sprint 13).
4. **Enum value lists** in the model, then generated CHECK constraints (finding 5) — Sprint 12.
5. **Ops tenant assignment** (finding 6) and k ≥ 5 aggregate views starting with EEO-1
   (finding 7) — Sprint 13.
6. **Insert-time PII encryption** for append-only PII columns (`er_case_note.note_body`), once
   the ER case flow is built: needs a column-level INSERT grant plus a pure encrypt-and-return
   function, distinct from the UPDATE-based `app.encrypt_pii` used for `employee`.
7. **Production key management:** replace `app.pii_key`'s dev passphrase (one shared GUC) with
   per-tenant data keys from a KMS; it is the one function that needs to change.
8. **CI:** run `alembic upgrade head` and `pytest` against Postgres 16 on every push — Sprint 12.
