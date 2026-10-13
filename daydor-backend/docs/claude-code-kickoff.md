# Claude Code kickoff

Rewritten Oct 13 2026 for the current `daydor-backend` (hire, payroll and exit flows built, migrations 0001
to 0024, worker registry and `DeciderClient` added, Laya decided in ADR-005 but not yet wired in). Paste the
prompt below into a Claude Code session started in `daydor-backend/`.

## Local setup (once)

```bash
# Postgres 16 with a superuser daydor_owner. This machine has Postgres 14 on 5432 and 16 on 5433.
# The migrations need 16 (they use INHERIT in CREATE ROLE), so point everything at 5433.
export DAYDOR_DATABASE_URL=postgresql+psycopg://daydor_owner:dev@localhost:5433/daydor_dev
export DAYDOR_TEST_DATABASE_URL=postgresql+psycopg://daydor_owner:dev@localhost:5433/daydor_test

python3 -m venv .venv && source .venv/bin/activate     # Python 3.11 or newer
pip install -e ".[dev]"
alembic upgrade head
pytest                                                  # expect 224 passed on Oct 13 2026
```

Without the two environment variables, the default URLs use port 5432 (Postgres 14) and about 180 tests
error in setup with a syntax error near `INHERIT`. That is a setup problem, not a code problem. Tests drop
and recreate `daydor_test` each run. Node is only needed to re-export the model from the artifact
(`scripts/export_model.js`).

## The prompt

```
You are continuing work on daydor-backend: the backend for an HR platform for SMEs (50-100
employees) in which domain "workers" (agents) do HR tasks. Data lives in Postgres; workflows are
Postgres queues and state machines (ADR-001); hard human approval gates are enforced by the
database (ADR-003); workers are classified by kind and autonomy (ADR-004); soft gates in front of hard
gates use a typed-decision engine behind the DeciderClient interface (ADR-005: Laya, an open-weights
local model; the repo still has the Jev stub in gates/jev.py until Laya is wired in). The engine fails
closed, starts in shadow mode, and cannot enforce without a fitted calibration.

READ FIRST, in this order, before writing anything:
1. CLAUDE.md                      (rules that must not be broken)
2. docs/backend-plan.md           (components, status, next steps, "Soft gates with Laya")
3. docs/adr/ADR-001 to ADR-005
4. docs/model-findings.md         (23 findings; several are closed, some open items listed below)
5. docs/sprint-plan.md            (what Sprints 1 to 12b built and how)
6. docs/worker-classification.md and registry/worker_classification.json
   (89 workers: kind, effect, autonomy, owner; registry/workers.generated.json is derived)
Then run `git log --oneline` and `pytest` (with the environment variables from the setup section).
Tell me the result before continuing. Expect 224 passed. Note any uncommitted changes in
`git status` and do not touch or revert files you did not change.

WHAT EXISTS TODAY (verify each of these; do not assume)
- Roles: 15 per-domain roles `agent_<domain>` (agent_hr, agent_pay, ...), all members of the group role
  `agent_runtime`, which carries the grants. `app.current_app_role()` collapses every `agent_*` role to
  `agent_runtime` for RLS and grant checks. They are not narrowed per worker (finding 3).
- Handlers: the queue `Worker.register(kind, role, fn)` takes the role as a string chosen by the caller.
  Today only tests register handlers (`tests/exit_helpers.py`, `tests/hire_helpers.py`,
  `tests/test_hire_requisition.py`), with the worker's name as the kind, for example
  "deprovisioning_agent" with role "agent_it". Nothing checks that a handler's role matches the worker.
- Registry: `src/daydor/agents/registry.py` builds `registry/workers.generated.json` (89 workers) from the
  authored `registry/worker_classification.json` plus the model. `tests/test_registry.py` enforces the
  rules. `src/daydor/agents/base.py` is a placeholder harness, not wired in.
- Guards: `GUARDS` in `src/daydor/gates/registry.py` lists the guarded columns: `payroll_run.disbursed_at`,
  `final_settlement.disbursed_at`, `contractor_invoice.paid_at` (all g_pay_disburse),
  `gl_journal_entry.posted_at` (g_close), `identity_account.deprovisioned_at` (g_it_deprov),
  `cobra_event.notice_sent_at` (g_cobra), `er_case.outcome` (g_er_adjud). The registry marks 13 workers as
  writing guarded tables.
- Grant caps: `grant_caps` in `model/extensions.json`, applied to the employee role and generated into
  `0024_model_grant_caps.sql`. Worker grants must respect the model's capped access.
- Decider: `src/daydor/gates/decider.py` (`DeciderClient`, `LayaClient`) exists and is unit-tested, but
  nothing imports it. `soft.py`, `anomaly.py`, `workflow/engine.py` and the tests still use JevClient /
  FakeJev. The Downloads fork's migration `0011_laya_decider` was NOT adopted (0011 is `0011_privacy`).

PHASE 0: RECONCILE THE REGISTRY WITH THE REPO (analysis only, no changes yet)
Write docs/worker-roles-reconciliation.md covering:
- Every handler in src and tests mapped to a registry worker, and the reverse: registry workers with no
  handler yet, handlers with no registry entry, and workers that run as several handler kinds (for
  example candidate-screener, employee-record-writer).
- For each guarded column, which registry worker the repo's code actually writes it from today, compared
  with the proposed owner list in Phase 1 step 4. Flag any disagreement.
- Every table each worker's code actually writes or reads, compared with the registry's `reads` and
  `writes`. List any worker whose real access is wider than its registry scope (that is a Phase 1 blocker,
  because a derived role would break working code).
- How roles interact with existing database objects: `app.current_app_role()` and other functions or
  policies that special-case `agent_*` or `agent_runtime` (migrations 0001 to 0024), SECURITY DEFINER
  functions that check the caller's role, and the model's `grant_caps`.
- A migration plan: next free number is 0025, and Phase 1 takes it. Laya adoption comes after Phase 1
  (decided), so its `calibration_version` migration takes the next free number after Phase 1's last one;
  note anything in Phase 1 that would make that harder.
- Anything in the registry that is out of date against the model or the repo.
STOP and wait for my decision. Do not modify migrations, the model or the registry in this phase.

PHASE 1: WORKER REGISTRY IN THE DATABASE, AND PER-WORKER ROLES (after I approve Phase 0)
Goal: make the worker classification real inside Postgres, so a worker's powers come from the
database and cannot be widened by application code. Do it in small committed steps, tests green
at each step. Do not stop for review between steps 1 to 6; run them through and stop only when Phase 1
is complete (or earlier only if a step is blocked by an open decision or a failing test you cannot fix
without loosening a rule). Every migration is new and forward-only; never edit an applied migration.

1. app.worker_definition: one row per worker, generated from registry/workers.generated.json by a
   generator in src/daydor/agents/ (same pattern as the gate seed and `grant_caps`: a generated SQL
   file, committed, with a drift test, plus a new migration). Columns: worker (pk), home_domain, kind,
   effect, autonomy, owner, triggers, llm_tier, assist (jsonb), flags (text[]), decision (jsonb),
   soft_gate, wave, writes (text[]), reads (text[]), enabled (bool, default true). Use only the fields
   the registry really has; if a column has no source (for example llm_tier), say so and propose one
   rather than inventing values.
2. app.worker_tenant_policy: per-tenant override (tenant_id, worker, autonomy, enabled), with row-level
   security like every tenant table. A database trigger must reject any override that RAISES autonomy
   above the worker's default (auto < review < approve is the safe direction; a tenant may only move
   toward approve), as ADR-004 says.
3. One NOLOGIN database role per worker (worker_<name with - replaced by _>), generated from the
   registry and model. Grants are derived: SELECT on tables in the worker's reads and writes,
   INSERT/UPDATE on tables in its writes, at column level, capped by the model's access level for the
   agent role ("G") and by `grant_caps`. Never grant encrypted columns. Never grant DELETE. Make each
   worker role a member of nothing that carries broader grants than its own.
4. Guarded columns go only to named workers (my proposed defaults, verify against Phase 0 and list them
   in the PR description so I can change them):
   - payroll_run.disbursed_at, final_settlement.disbursed_at -> direct-deposit-disburser
   - contractor_invoice.paid_at -> multi-currency-payment-router
   - gl_journal_entry.posted_at -> gl-poster
   - identity_account.deprovisioned_at -> deprovisioning-agent
   - cobra_event.notice_sent_at -> cobra-notice-generator
   - er_case.outcome -> investigation-tracker
   Every other worker that writes those tables gets the table but not the guarded column. These
   columns also stay behind `app.enforce_gate_guard`, which still requires an approved request.
5. Make `app.current_app_role()` and any policy or function that special-cases `agent_*` treat worker
   roles the same way (Phase 0 lists them). Let daydor_app SET ROLE to each worker role; extend
   `tenant_session` and `APP_ROLES` to accept worker roles. Make the queue `Worker` take the role from
   the registry by worker name instead of a caller-supplied string: a disabled worker, or a tenant
   policy that disables it, must fail the job closed (recorded and retried or dead-lettered, not
   skipped silently).
6. Keep the existing agent_<domain> roles working until Phase 1 is complete, then remove them in a
   separate migration with their tests moved to the worker roles. Move the existing test handlers
   (`tests/exit_helpers.py`, `tests/hire_helpers.py`, ...) onto worker roles, and list every worker whose
   real work needed a wider scope than the registry gives it.

TESTS (required; model them on tests/test_access.py, tests/test_registry.py and
tests/test_employee_self_service.py)
- A generated matrix test: every worker role's column privileges equal exactly what the registry and
  model say, as `test_column_grants_match_model` does for the people roles.
- Negative tests: payroll-run-builder cannot set disbursed_at even when an approved gate exists for the
  row; direct-deposit-disburser can, only with that approved gate; a worker cannot read a table outside
  its scope; no worker role can resolve an approval; a tenant policy cannot raise autonomy; a disabled
  worker's job fails closed.
- Mutation tests proving the new rules can fail, in the style of tests/test_registry.py.
- Drift tests for every new generated SQL file. The existing flow tests (hire, payroll, exit) must keep
  passing on worker roles without loosening any grant to make them pass.

CONSTRAINTS (from CLAUDE.md, restated because they matter most)
- Never hand-edit generated files. Change the source, regenerate, add a forward-only migration.
- Hard human gates stay human. No worker role may be able to resolve an approval.
- A model (a decider or an LLM) never touches a worker whose scope has C3, C4 or encrypted columns
  (ADR-004). The registry tests enforce this; keep them passing.
- Enforce in the database; application checks are extra, not the only check.
- Every new function in the app schema needs an explicit GRANT EXECUTE, and none may be executable
  by PUBLIC (`test_no_app_function_is_executable_by_public` enforces this).
- Commit after each step with a message saying what changed and why. Keep tests green. Do not revert
  or reformat files you did not change.

OPEN DECISIONS: do NOT decide these. Leave the stub or flag that exists, and list them for me:
- Workers whose effect is irreversible or external but that have no hard gate yet (check the registry's
  flags and `docs/worker-classification.md`; do not add gates).
- Whether candidate-screener may receive resume text (C3), and whether it may ever enforce (ADR-005).
- Restricted-data policy for models (C3 per gate, C4 never), and whether one tenant's decisions may train
  a model serving other tenants (docs/backend-plan.md, "Soft gates with Laya").
- Manager approval for expenses (`g_expense` exists in the registry but no service writes the guarded
  columns), and the missing guards on `expense.reimbursed_at` and `leave_request.status` (finding 23).
- The Laya adoption itself: renaming Jev to DeciderClient, the `calibration_version` migration, and a
  smoke test against a pinned checkpoint. `LayaClient` has never run against a real checkpoint; do not
  wire it into a flow until that test passes (see "Planned sessions").

WHEN DONE
Update docs/backend-plan.md (status and next steps), docs/sprint-plan.md and CLAUDE.md if rules changed.
Then tell me: what you built, tests added and the final pytest count, anything you chose that I should
review, and the open decisions still waiting on me. Do not start the next session.
```

## Planned sessions after this one

| Session | Scope |
|---|---|
| A | Laya adoption: rename Jev to `DeciderClient` in `soft.py`, `anomaly.py`, `engine.py` and tests; add the `calibration_version` migration (next free number; the Downloads 0011 must be renumbered); install, pin and vendor a checkpoint; smoke-test `LayaClient`; run the soft gates in shadow mode (ADR-005) |
| B | Shadow-versus-human report, the labelled-example store and the calibration pipeline (Sprint 13) |
| C | Hardening still open in the sprint plan: enum CHECK constraints (finding 5), ops tenant scoping (finding 6), aggregate views (finding 7), CI |
| D | Timers for statutory clocks beyond I-9 (COBRA follow-ups, 409A, expiries, thresholds) and the human approvals inbox |
| E | Backlog flows: erasure, merit, threshold-crossing; the webhook inbox when the first real vendor adapter replaces a mock |
