# Working on daydor-backend

Context for Claude Code. Read `docs/backend-plan.md`, `docs/model-findings.md` and `docs/adr/` first.

## Setup
- Postgres 16 with a superuser `daydor_owner` (password `dev`) and databases `daydor_dev`, `daydor_test`.
- `pip install -e ".[dev]"`, then `alembic upgrade head` and `pytest`. Tests recreate `daydor_test` each run.

## Rules that must not be broken
1. **The model is the source of truth.** Never hand-edit `migrations/sql/0002_*`, `0003_*`,
   `0007_*` or `0010_*`: they are generated. Change `model/` (or the generators), regenerate, and add a
   new migration. `tests/test_model_drift.py` fails on any mismatch.
   - Tables, RLS, grants: `python -m daydor.model.ddl migrations/sql`
   - Grant caps (`grant_caps` in `model/extensions.json`, e.g. finding 2) are generated into
     `0024_model_grant_caps.sql` by the same `python -m daydor.model.ddl` run; `0003` stays the uncapped baseline
   - Gates: `python -m daydor.gates.registry`
   - Workflows: `python -m daydor.workflow.definitions`
2. **Migrations are forward-only.** Never edit an applied migration; add a new one (see 0008).
3. **Hard human gates stay human.** Agents must never be able to resolve an approval. The soft-gate
   engine (Laya, behind `DeciderClient`; ADR-005. Today the code still has the Jev stub) runs only on soft
   gates, fails closed, starts in shadow mode, cannot enforce without a fitted calibration, and never
   receives C3/C4 or encrypted columns.
4. **Enforce in the database.** Tenant isolation, column access, maker-checker and guarded writes live in
   Postgres. Application checks are extra, never the only check.
5. **Everything is idempotent.** Queue delivery is at-least-once. Every handler and command takes an
   idempotency key or event id.
6. **Every function in `app` is opt-in.** New functions need explicit `GRANT EXECUTE`;
   `test_no_app_function_is_executable_by_public` enforces this.
7. **Roles:** business objects are owned by `daydor_schema_owner` (non-superuser, subject to FORCE RLS).
   Only functions that must see a whole tenant are owned by `daydor_system` (BYPASSRLS), and they must
   filter by tenant explicitly.

## Where things are
- Session context: `src/daydor/db/session.py` (`tenant_session`)
- Queue / outbox / timers: `src/daydor/queue/`, SQL in `migrations/sql/0005_queue.sql`
- Gates: `src/daydor/gates/` (hard, soft, decider client: currently `jev.py`, to become `DeciderClient`/`LayaClient` per ADR-005), SQL in `0006_gates.sql`
- Privacy: `src/daydor/privacy/pii.py` (`encrypt_pii`/`decrypt_pii`), SQL in `0011_privacy.sql`
- Hire flow (complete, steps 1-18; step 19/payslip is out of scope, see finding 15):
  `src/daydor/hire/` (`employee_record.py`, `requisition.py`, `approvals.py`, `posting.py`,
  `screening.py`, `interview.py`, `offer.py`, `background_check.py`, `consent.py`, `documents.py`,
  `work_authorization.py`, `checklist.py`, `identity.py`, `access_grant.py`, `workflow.py`), SQL
  in `0012_hire.sql`, `0013_platform_gates.sql`, `0014`-`0018_hire_workflow_v*.sql`
- Timekeeping: `src/daydor/timekeeping/` (`punch.py`, `timecard.py` incl. `g_timecard`'s
  `gate.resolved` subscriber, `leave.py`); Benefits: `src/daydor/benefits/election.py`
  (`election-processor` -- not employee self-service, see finding 16); SQL in
  `0019_timecard_gates.sql`
- Payroll computation (gross-to-net): `src/daydor/payroll/` (`gross_pay.py`,
  `tax_withholding.py`, `garnishment.py`, `compute.py`). `statutory_rate_rule.employee_rate`/
  `employer_rate` are `numeric(8,6)`, not the generated `numeric(14,2)` -- see finding 18 and
  `0020_statutory_rate_precision.sql`.
- Payroll run, anomaly gate, disbursal: `src/daydor/payroll/` (`run_builder.py`, `anomaly.py`,
  `disbursement.py`, `payslip_issuer.py`); bank adapter in `src/daydor/adapters/bank.py`. Not
  driven through `WorkflowEngine` -- see `run_builder.py`'s module docstring. `payroll_run`/
  `payslip`'s derived total columns are written only through the SECURITY DEFINER functions in
  `0021_payroll_run_functions.sql` (finding 19), same pattern as `daydor.privacy.pii`.
- Payroll filings and GL posting (flow complete end to end): `src/daydor/payroll/tax_filing.py`,
  `gl_posting.py`; adapters in `src/daydor/adapters/tax_filing.py`, `gl.py`. `gl-poster` uses the
  same create-the-row-then-gate-the-UPDATE shape as `g_pay_disburse`, for `g_close`.
- Adapters (external vendors, mocked until wired for real): `src/daydor/adapters/`
- Agentic worker harness (placeholder, not wired in yet): `src/daydor/agents/`
- Exit flow (complete, steps 1-14): `src/daydor/exit/` (`termination.py`, `legal_hold.py`,
  `checklist.py`, `deprovisioning.py`, `device_return.py`, `final_settlement.py`, `cobra.py`,
  `closeout.py`, `workflow.py`), SQL in `0022_exit_gate_guards.sql`, `0023_exit_workflow.sql`.
  Driven by `WorkflowEngine` like hire; see `workflow.py`'s module docstring for why
  `g_it_deprov`/`g_pay_disburse`/`g_cobra` are direct guarded-column calls instead of
  engine-level gates, unlike `g_legalhold`/`g_finalpay`.
- Sprint plan and status: `docs/sprint-plan.md`
- Workflows: `src/daydor/workflow/`, SQL in `0009_workflow.sql`
- Test org fixture: `tests/conftest.py` (two tenants, a five-person reporting tree, approver users)
