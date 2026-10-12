# Integration notes

Working notes for wiring the frontend/api to the backend's current state. Backend is read-only
from here (never edited); anything that needs a backend change is logged under "Asks for the
backend" below instead.

## Phase 0 (done)

See the sync report in-session: contract synced clean (82 tables, 10 roles, 23 gates unchanged
since FE-6), enum discovery improved 14/88 -> 33/88, three stale `test_meta.py` assertions fixed
(hard gate count, served gate count, hire workflow version), Node pinned to 20 via `.nvmrc` (the
system default and Node 24 LTS both fail every frontend test on a jsdom/undici `AbortSignal`
incompatibility; vitest 2 + jsdom 25 need Node 20).

## Phase 1: what changed in the backend since FE-6

The model itself (`model/daydor_model.json`) hasn't changed shape: still 82 tables, 20 model-defined
gates, same table ACLs. What changed is that the backend now has real code and workers for
**Payroll** and **Exit** (previously undocumented to the frontend), on top of Hire, which itself
grew from "through offer" (4-5 states) to all 18 steps, ending at `payroll_profile`.

### Hire flow -- now the full 18 steps (was: through offer only)

Workflow `hire`, version 6 (was version 3 when FE-6 shipped), terminal state `s18_payroll_profile`.

| State | Queue | Kind (handler) | Role | Gate |
|---|---|---|---|---|
| s03_approval_request | platform | requisition_approval_router | agent_ro | `g_requisition_budget` (outgoing) |
| s04_job_posting | ta | job_posting_publisher | agent_ta | |
| s05_application | ta | candidate_screener_intake | agent_ta | |
| s06_screening_result | ta | candidate_screener_assess | agent_ta | `g_aedt` (outgoing) |
| s07_interview | ta | interview_scheduler | agent_ta | |
| s08_offer | ta | offer_letter_generator | agent_ta | `g_offer_band` (outgoing, conditional on out-of-band) |
| s09_background_check | ta | background_check_initiator | agent_ta | `g_bg_adverse` (outgoing, conditional on adverse finding) |
| s10_employee | hr | employee_record_writer_create | agent_hr | |
| s11_employment_record | hr | employee_record_writer_open | agent_hr | |
| s12_consent_record | -- | (no agent writer; employee-triggered via `daydor.hire.consent.request_consent`) | -- | `dpdp_consent` |
| s13_document | privacy | new_hire_doc_collector | agent_priv | |
| s14_work_authorization | hr | i9_e_verify_initiator (US only; no-op for India) | agent_hr | schedules `app.timer` for I-9 §2 deadline |
| s15_checklist_task | ob | onboarding_checklist_builder | agent_ob | |
| s16_identity_account | it | sso_identity_provisioner | agent_it | |
| s17_app_access_grant | it | app_access_granter | agent_it | `g_it_offtemplate` (outgoing, conditional on off-template) |
| s18_payroll_profile (terminal) | pay | employee_record_writer_payroll | agent_pay | |

Every gate approval is still raised against the requisition (`job_requisition`, the workflow
instance's fixed subject), never against the screening/offer/background-check row that actually
triggered it -- `WorkflowEngine.fire()` calls `request_approval(conn, gate, inst.subject_table,
inst.subject_id, ...)`, and `subject_id` never changes after `start()`.

### Payroll flow -- complete end to end (new to the frontend)

Not driven through `WorkflowEngine` -- `payroll_run.status` carries its own bookkeeping, and every
step is a plain function the caller (the API layer) invokes directly as the right role, not a
queue-triggered handler reached through a state machine. **This matters for api/worker.py: there
is nothing to `register()` for payroll.** The API needs new endpoints/actions that call these
functions directly.

| Step | Function | Module | Role |
|---|---|---|---|
| Leave accrual | `accrue_leave` | `daydor.timekeeping.leave` | (caller's role; on-demand, no scheduler) |
| Timecard from punches | `validate_timecard` | `daydor.timekeeping.timecard` | (caller's role) |
| Timecard approval routing | `route_for_approval` | `daydor.timekeeping.timecard` | raises `g_timecard` (approver: `tenant_manager`) |
| Timecard gate resolution | `handle_timekeeping_gate_resolved` (queue handler, kind `timekeeping.gate_resolved`) | `daydor.timekeeping.timecard` | agent_time |
| Benefit election | `elect_benefit` | `daydor.benefits.election` | agent_ben (not the employee's own session -- finding 16) |
| Build payroll run | `build_payroll_run` | `daydor.payroll.run_builder` | agent_pay; idempotent on `(legal_entity_id, period_start, period_end)`; writes `payroll_run`/`payslip`/`payslip_line`/`gratuity_accrual_balance` via the `0021_payroll_run_functions.sql` SECURITY DEFINER functions |
| Anomaly pre-check | `check_payroll_run` | `daydor.payroll.anomaly` | soft gate `sg_payroll_anomaly_precheck`, always escalates to `g_pay_anomaly` in shadow mode (approver: `tenant_payroll`/`daydor_ops`) |
| Disbursal approval + disburse | `request_disbursal_approval` / `disburse_payroll_run` | `daydor.payroll.disbursement` | `g_pay_disburse` (approver: founder); `FakeBankAdapter` |
| Issue payslips | `issue_payslips` | `daydor.payroll.payslip_issuer` | raises `PayrollRunNotDisbursed` until `disbursed_at` is set |
| File statutory returns | `file_payroll_run` | `daydor.payroll.tax_filing` | one `filing_record` per scheme (IN: ecr/24q; US: 941/w2/state_ui), idempotent |
| Post to GL | `open_journal_entry` / `request_gl_close_approval` / `post_journal_entry` | `daydor.payroll.gl_posting` | `g_close`; same create-then-gate shape as disbursal |

Gross-to-net computation (`daydor.payroll.gross_pay`, `tax_withholding`, `garnishment`, `compute`)
is explicitly **illustrative**: one flat rate per scheme (India PT+PF+flat TDS, US
FICA+federal+one state), not real slabs/exemptions/YTD caps. The UI should label payroll numbers
accordingly, same as the backend's own docs do.

### Exit flow -- complete end to end (new to the frontend)

Driven through `WorkflowEngine` like Hire. Workflow `exit`.

| State | Queue | Kind | Role | Gate |
|---|---|---|---|---|
| s02_legal_hold_check | hr | legal_hold_checker | agent_hr | `g_legalhold` (conditional -- only if a hold is active) |
| s03_checklist | hr | termination_checklist_builder | agent_hr | |
| s04_identity_account | it | deprovisioning_agent | agent_it | `g_it_deprov` (direct guarded-column call, not an engine-level transition gate) |
| s05_device_assignment | it | equipment_return_tracker | agent_it | |
| s06_final_settlement_calc | pay | final_pay_calculator | agent_pay | `g_finalpay` (outgoing) |
| s07_final_settlement_created | pay | final_settlement_opener | agent_pay | |
| s08_disbursed | pay | direct_deposit_disburser | agent_pay | `g_pay_disburse` (direct guarded-column call, reusing Payroll's pattern) |
| s09_cobra | hr | cobra_trigger_detector | agent_hr | `g_cobra` (US only, no-op elsewhere) |
| s10_closeout (terminal) | hr | employee_closeout | agent_hr | sets `employee.is_active = false`, `date_of_exit` |

`legal_hold` and `vesting_event` are read-only inputs (legal_hold is admin-entered by
`tenant_hr`/`tenant_founder`; vesting_event may legitimately be empty -- equity/vesting is Merit's
backlog, not built).

### Gates: 23 hard (20 model + 3 platform), 2 soft -- was fewer at FE-6

Platform-defined hard gates not in the model artifact (`docs/model-findings.md` findings 9, 11):
`g_requisition_budget` (approver: founder), `g_timecard` (approver: manager), `g_expense`
(approver: manager, no domain service raises it yet). Soft gates: `sg_payroll_anomaly_precheck`
and `sg_access_request_precheck`, both shadow-mode only (never auto-resolve anything), escalating
to `g_pay_anomaly`/`g_it_offtemplate`.

### No HTTP layer, worker runner, enum value lists, or sign-in path shipped by the backend

Checked directly in the backend source: no FastAPI/Flask dependency, no `app.py`/`main.py`, no
auth/login module. `src/daydor/queue/worker.py`'s `Worker` is a library class the caller
instantiates and registers handlers on -- `api/src/daydor_api/worker.py` remains the only process
that actually runs the queue. Enum columns are still plain `text` with no CHECK constraints
(Sprint 12 work, not done: sprint-plan.md shows Sprints 1-11 done, 12-13 not started). **Recommend
no change** to the api/ layer's ownership of these three things; keep them thin wrappers, as today.

## Earlier findings, rechecked against the current backend

| # | Finding | Status |
|---|---|---|
| 1 | A requisition takes exactly one candidate through the flow | **Still true.** `submit_application` fires `"advance"` on the workflow instance, moving it past `s04_job_posting`; the instance can't re-enter that state, so a second application against the same requisition has nothing to apply to. |
| 2 | Every gate approval is raised against the requisition, not the screening/offer row | **Still true.** `WorkflowEngine.fire()` -> `request_approval(conn, gate, inst.subject_table, inst.subject_id, ...)`; `subject_id` is fixed at `start()` and never changes. |
| 3 | Hiring managers cannot see candidate names (candidate row policy) | **Still true.** `migrations/sql/0003_model_security.sql`: `CREATE POLICY person_scope ON public.candidate ... USING (app.can_see_employee(converted_employee_id))` -- hidden until the candidate becomes an employee. |
| 4 | Only HR can rate a skill (`employee_skill.proficiency_level`) | **Still true.** Column access: H(HR)=4 write, G(agents)=4 write; M(manager)=3, E(employee)=3 -- read only. |
| 5 | IT can write access templates but cannot read job profiles | **Still true.** `access_role_template` table ACL: I=4 (write); `job_profile` table ACL: I=0 (no access). |
| 6 | Start-hire context must carry comp band, proposed base/equity, interviewer and time | **Still true, but refined.** These aren't required at `start_hire()` itself (which only takes `position_id`/`hiring_manager_id`/`target_start_date` plus free-form `**extra_context`) -- they're required as `context_patch` on whatever transition precedes the step that reads them (`offer_letter_generator` reads `ctx["comp_band_id"]`/`ctx["proposed_base"]` from the merged context at the moment the offer job is enqueued). The frontend's single upfront Start-hiring dialog is a reasonable simplification, not something the backend requires, but it does mean the UI must collect these before the workflow reaches the offer step, not after. |
| 7 | `document` and `checklist_task` have no person-scope row policy | **Still true.** No `person_scope` policy on either table in `0003_model_security.sql` (confirmed by grep); only `tenant_isolation`. Not exploitable today because the API only ever queries for the caller's own subject, but worth flagging again. |
| 8 | Enum values were unlisted in the model (only 14 of 88 discovered by scanning) | **Changed (improved, not resolved).** Now 33 of 88 discovered by `api/scripts/gen_enums.py`, because Payroll and Exit code now writes values that didn't exist to scan before. The underlying gap (no model-declared value lists, no CHECK constraints) is unchanged -- that's Sprint 12, not done. |
| 9 | A second `start_hire` for the same position raised `WorkflowError` | **Still true.** `open_requisition()` is idempotent (returns the existing requisition for an open position), so `engine.start()` is called again with the *same* `subject_id` and itself no-ops (`ON CONFLICT DO NOTHING`, returns the existing instance) -- but `start_hire()` then unconditionally fires `"advance"` three times more, which is invalid from whatever state the existing instance is actually in, and raises. The API's existing workaround (map to 409, return the existing hire) is still needed. |
| 10 | Nothing ran the queue workers (`api/src/daydor_api/worker.py` is my runner) | **Still true.** Confirmed: `daydor.queue.worker.Worker` is a library class; the backend has no standalone runner process. No change needed in the backend's favor here -- `api/worker.py` keeps this job, and now also needs to run Payroll's direct-call functions on whatever trigger the API decides (an endpoint action, not a queue handler, since Payroll isn't engine-driven). |

## Live now vs. still mock (frontend screens)

| Screen | FE-6 status | Status after Phase 2 |
|---|---|---|
| Positions, Start hiring, Requisitions, candidate pipeline, out-of-band offer approval | Live | Live. Start-hiring dialog now also collects the new-hire personal/payroll-setup details steps 10/11/18 read from context (see Phase 2 notes below) |
| Reference data, People directory, person profile, My privacy | Live | Unaffected, still live |
| Background check step | Sample data | **Live.** `background_check_initiator` registered in `api/worker.py`; reads through the existing generic `/tables/background_check` call, no API change needed |
| Consent flow and documents | Sample data | **Live.** New `POST /hire/requisitions/{id}/request-consent` (HR-only) triggers `daydor.hire.consent.request_consent`; the employee resolves the resulting `dpdp_consent` approval through the existing Approvals screen; `new_hire_doc_collector` registered, documents readable generically |
| Work authorization (I-9/E-Verify, timer) | Sample data | **Live.** `i9_e_verify_initiator` registered; reads generically. The `i9_section2_due` timer fires but nothing processes it yet (matches the backend's own Sprint 13 backlog -- not something Phase 2 can close) |
| Onboarding checklist | Sample data | **Live.** `onboarding_checklist_builder` registered; task completion stays read-only (`checklist_task.status` only ever writes `'open'` -- no `'done'` value exists anywhere in the backend to write, so this is still a guess the UI correctly refuses to make) |
| Identity account | Sample data | **Live.** `sso_identity_provisioner` registered |
| App access grants (off-template gate) | Sample data | **Live.** `app_access_granter` registered |
| Payroll profile | Sample data | **Live.** `employee_record_writer_payroll` registered; this is the hire flow's real terminal step (`done`, not `s18_payroll_profile` -- the engine fires one more `"advance"` into a generic terminal state) |
| Payslip | Sample data | **Live.** `PersonTabs.tsx`'s payslip tab shows a real payslip once a payroll run issues one, now with a permanent "Illustrative tax figures" badge (FE-8) |
| Timecards, leave, benefit elections, expenses | Not in FE-6 scope | **Live** (FE-7). New `/time` screen: self-service punches, timecard build (+ real `g_timecard` approval), leave balances + an HR/ops accrual trigger, benefit elections (agent-processed, not self-service), expenses (an API-layer gap-fill -- see below) |
| Payroll run / disbursal / filing / GL | Not in FE-6 scope | **Live** (FE-9/FE-10). New `/payroll` and `/payroll/:id` screens: build a run, the anomaly and disbursal gates linked inline, payslip issuance, statutory filings, GL posting |
| Exit flow (termination through closeout) | Not in FE-6 scope | Not built this pass |

## Phase 2: what was actually done

- `api/src/daydor_api/worker.py`: registered the 8 missing hire-flow handlers (steps 9-18:
  `background_check_initiator`, `employee_record_writer_create`/`_open`/`_payroll`,
  `new_hire_doc_collector`, `i9_e_verify_initiator`, `onboarding_checklist_builder`,
  `sso_identity_provisioner`, `app_access_granter`) with the queue/role the backend's own tests
  use, and removed a stale `employee_record_writer` registration that no version of the hire
  workflow still in use (version 6) ever enqueues -- this is why the live flow previously stalled
  silently after the offer step even though the backend had already built these steps.
- `POST /hire/requisitions/{id}/request-consent` (new, HR-only): the only step with no agent
  worker by design (`consent_record` is employee-only to write). Also added an `onboarding` block
  to `GET /hire/requisitions/{id}` (employee id, workflow state/status, whether the flow is
  waiting on this trigger) so the UI knows when to show it.
- Extended `StartHire` (both the API's Pydantic model and the frontend's dialog) with the new-hire
  personal and payroll-setup fields steps 10/11/18 read from workflow context -- optional on the
  API side (a hire can still run through the offer without them), but the dialog requires the ones
  that are genuinely required everywhere, including `aadhaar_last4` (flagged as a backend gap:
  NOT NULL regardless of jurisdiction, even though it is only meaningful in India -- see "Asks for
  the backend" below). Seeded one `retention_policy` row in `seed_dev.py` (global, admin-only
  reference data the document-collector step needs; nothing seeded one before).
- `api/tests/test_hire_onboarding.py` (new): drives the full chain through the real API, the real
  queue workers and a real Postgres backend, including resolving the employee's own `dpdp_consent`
  gate (by provisioning a real `app_user` row for them, same as the backend's own tests do), and
  proves the engine reaches its true terminal state (`done`).
- `frontend/src/api/live.test.ts`: new test proves steps 9-12 (background check through the raised
  consent gate) run against a real API, worker and Postgres -- run twice in a row, both green. It
  cannot drive all the way to `payroll_profile` the way the Python test does, because resolving
  `dpdp_consent` needs a sign-in for the new hire that no endpoint provisions yet; it stops at
  proving the gate is correctly raised against the right role. Also fixed a latent flakiness in
  `freshSeat()` (picked `/tables/employee`'s first row with no ordering -- harmless before Phase 2
  because no hire completed far enough live to add a new employee row; now it does, and the
  unfiltered pick was no longer stable run over run).

## Not done this pass (flagging rather than leaving silently inconsistent)

- **Mock backend parity.** The task's own rule says "when you make something live, update the mock
  to match real behaviour." The mock's simulated hire flow still stops at the offer, same as
  before Phase 2 -- it was not extended to simulate background check through payroll profile. This
  is a real gap, not an oversight: doing it properly means simulating 9 more steps' worth of
  state, the consent gate's request/resolve split, and the new-hire context fields, which is
  substantial work in its own right. The preview build (sample data only) therefore still shows
  these screens empty past the offer, while live data now populates them. Logged here rather than
  silently left inconsistent; worth its own pass before relying on the preview for a full demo.
- **Payroll and Exit screens.** Both flows are backend-complete (Phase 1's table) and Payroll now
  has real API actions (Phase 3), but neither has a frontend screen yet.

## Phase 3: hire end to end on live data, through a real first payslip

- **New hire sign-in, provisioned automatically** (`api/src/daydor_api/onboarding.py`). The
  model's `dpdp_consent` gate can only be resolved by the employee themselves, but the backend's
  own identity-provisioning step (16, SSO) runs *after* consent (step 12) -- so if sign-in waited
  for that step, no new hire could ever clear their own gate through this API. Provisioning it
  instead at employee creation (step 10) is the API's own design choice, not a backend change.
  Runs as `tenant_founder`, not the seemingly-obvious `tenant_it`: IT's actual column grant on
  `app_user` is `INSERT (role, employee_id, is_active, mfa_enrolled, last_login_at)` -- no
  `email` -- so IT can link an account to an employee but not choose its sign-in address; founder
  is the only tenant-side role granted `email` too. Worth a second look once this is more than a
  prototype.
- **`api/src/daydor_api/routers/payroll.py`** (new): `POST /payroll/runs` (build + anomaly
  pre-check in one call -- shadow mode always escalates, so there's no real decision point between
  them), `POST /payroll/runs/{id}/request-disbursal`, `POST /payroll/runs/{id}/disburse`,
  `POST /payroll/runs/{id}/issue-payslips`. Filing and GL posting are not wired (not needed to
  reach "first payslip"). Runs as `agent_pay`, added to `sessions.py`'s `ALLOWED_AGENT_ROLES`
  (it only listed `agent_ta`/`agent_hr`/`agent_ro` before).
- **Seed data additions** (`api/src/daydor_api/seed_dev.py`): `statutory_rate_rule`/`pt_slab_rule`
  rows (India PF/TDS/PT, US FICA/federal/TX -- same values as the backend's own
  `tests/test_payroll_compute.py`, so a demo payslip's numbers are hand-checkable), an
  `employment_record` for the two pre-existing seeded employees (Payroll's run-builder processes
  every active employee under a legal entity, not just new hires, and would otherwise crash the
  first time a real run touches them), a second US legal entity/location (Austin, TX) so the
  work-authorization path is reachable at all, and an `app_user` row for `daydor_ops` (missing
  entirely before -- see "Asks for the backend" below, it's not actually a backend issue).
- **`api/tests/test_hire_end_to_end.py`** (new, parametrized IN/US): drives a hire from a new
  requisition through offer, background check, consent (resolved by the new hire's own real
  sign-in, not a stand-in), documents, work authorization (US only) or no row at all (India),
  onboarding, access, payroll profile, and a real payroll run through to a first payslip with
  correct withholding -- the right role doing each human step (HR enters the application and
  requests consent, the new hire grants and resolves their own consent, the founder approves the
  budget and disbursal, payroll builds the run and requests disbursal, daydor_ops clears the
  anomaly check since the payroll person who raised it can't also clear it). Both the US and
  India-first paths pass.
- **`frontend/src/api/live.test.ts`** extended the same way, through the same real sign-in and a
  real payslip -- removes the limitation the Phase 2 commit noted ("cannot drive all the way to
  payroll_profile, because resolving dpdp_consent needs a sign-in no endpoint provisions"); that
  endpoint now exists. Run twice in a row against a live API and worker, both green.
- **Two real bugs found and fixed along the way, both pre-existing, not introduced by Phase 3**:
  `daydor_ops` had no `app_user` row at all, so resolving any approval naming them as an approver
  (e.g. `g_pay_anomaly`) failed with a misleading generic "forbidden" (the real cause, several
  layers down, is "resolving an approval needs a signed-in user"); and `test_hire_flow.py`'s
  `_open_position()` picked blindly from the shared `/tables/position?status=open` pool with no
  isolation, which broke once a hire was driven all the way to real completion for the first time
  (nothing in the backend marks a finished hire's position "filled" or closes its requisition, so
  a completed hire's position still looks exactly like a fresh open seat -- the same shape as
  finding 9, one step further down the flow). Fixed by having it create its own fresh position,
  matching the pattern every other test file already uses.

## FE-7 to FE-10: Payroll end to end, with frontend screens

The build plan's FE-9 outline assumed Payroll's run-level actions didn't exist yet; Phase 3 had
already built them. This pass added the remaining backend wiring (time/leave/benefits/expenses,
filing, GL) plus every screen: `/time` (FE-7), the payslip tab's illustrative-tax badge (FE-8),
`/payroll` and `/payroll/:id` (FE-9/FE-10).

- **`api/src/daydor_api/routers/timekeeping.py`** (new): `time_punch` added to
  `DIRECT_WRITE_TABLES` (self-service, matches the backend's own design). `POST
  /timekeeping/timecards` runs `validate_timecard` + `route_for_approval` in one call, as
  `agent_time` -- a plain function, not a queue handler, same shape as Payroll. `POST
  /benefits/elections` runs `elect_benefit` as `agent_ben`, not the employee's own session
  (finding 16). Registered `worker.py`'s missing `'timekeeping'` queue (`agent_time`, kind
  `'timekeeping.gate_resolved'`) -- without it, a resolved `g_timecard` approval never updated the
  timecard's own status, since it isn't tracked by a `WorkflowEngine` instance.
- **`expense` has no backend service at all**, despite a real `E: WRITE` grant and a registered
  `g_expense` platform gate -- the model names workers (`expense-policy-checker`,
  `expense-approval-router`) that were never implemented. `POST /expenses` fills this gap at the
  API layer: inserts the row and raises the gate in one `agent_hr` session, since
  `approval_request`'s own grant doesn't let an employee insert it directly.
- **`api/src/daydor_api/routers/payroll.py`** extended with filing (`file_payroll_run`) and GL
  posting (`open_journal_entry` + `request_gl_close_approval` combined, then `post_journal_entry`)
  -- same pattern as the existing run/disburse actions.
- Seeded `leave_policy` and `benefit_plan` reference rows, and added `leave_policy`,
  `benefit_plan`, `statutory_rate_rule`, `pt_slab_rule` to `DIRECT_WRITE_TABLES` and to the
  Reference Data screen's specs.
- **Two real bugs found and fixed, both pre-existing**: (1) `POST`/`PATCH /tables/{table}` built
  its SQL with no cast for jsonb columns, so a jsonb value sent as a JS object (exactly what
  `ModelForm` sends) made psycopg raise `cannot adapt type 'dict'` -- never hit before because no
  `DIRECT_WRITE_TABLES` entry had a jsonb column any passing test or real use ever wrote through
  this path until `leave_policy.accrual_rule`. Fixed with a per-column cast read from the model's
  own column type. (2) `ReferenceDataPage`'s edit gate used `canWriteTable` (the table-level
  summary) instead of real per-column access -- harmless for the original four specs, but would
  have shown a working-looking "Add" button for `daydor_ops` on `statutory_rate_rule`/
  `pt_slab_rule` that 403'd on submit (see the new finding below). Switched to `writableColumns`.
- Verified every new endpoint and read against a real running API, worker and Postgres via
  `curl`, matching the exact request/response shapes the new hooks and components use -- no
  browser automation tool was connected this session, so this replaced a live click-through.
- `nav.ts` promotes "Time and leave" and "Payroll" from the placeholder `soon` list to real links.

## FE-11/FE-12: Exit flow end to end, with frontend screens

Mirrors the Hire/Payroll shape: the exit workflow runs automatically end to end except for three
steps where the gate guards a column on a row other than the workflow's own fixed subject
(`g_it_deprov`/`g_pay_disburse`/`g_cobra`, per `daydor.exit.workflow`'s module docstring) -- those
are the only three actions a person triggers, same reasoning as Payroll's `g_pay_disburse` on
`payroll_run`.

- **`api/src/daydor_api/routers/exit.py`** (new): `POST /exit/start` (role-gated to
  `tenant_hr`/`tenant_founder`, runs `start_exit` as `agent_hr`); `POST
  /exit/identity-accounts/{id}/deprovision` (`tenant_it`/`daydor_ops`, runs `deprovision_identity`
  as `agent_it`); `POST /exit/final-settlements/{id}/disburse` (gated on `final_settlement`'s
  table-write level, runs `disburse_final_settlement` as `agent_pay`); `POST
  /exit/cobra-events/{id}/send-notice` (`tenant_hr`, runs `send_cobra_notice` as `agent_hr`). All
  409-map a failed gate check (`deprovisioning_not_approved`/`disbursal_not_approved`/
  `notice_not_approved`), same shape as Payroll's disbursal 409.
- **`api/src/daydor_api/worker.py`** registers all nine exit-flow queue handlers onto the existing
  `hr`/`it`/`pay` Worker instances (no kind collisions with Hire's registrations on the same
  queues).
- `legal_hold` added to `DIRECT_WRITE_TABLES` -- a direct `tenant_hr`/`tenant_founder` write, no
  service needed, per `daydor.exit.legal_hold`'s module docstring.
- **New backend finding, logged above**: `start_exit()` is not safely idempotent -- a second call
  for an employee already mid-exit silently fast-forwards the real instance, skipping steps.
  Worked around at the API layer (`/exit/start` now checks for an existing `termination` row and
  returns 409 before ever calling `start_exit()`), found and root-caused by driving the flow twice
  end to end in `api/tests/test_exit_flow.py` (the test's own deliberate "replay the start call"
  case, same as finding 9's hire-flow precedent, is what surfaced it).
- Frontend: `/exit` (list + start-termination dialog) and `/exit/:id` (termination detail: legal
  hold status, checklist, deprovisioning approval + action, device return, final settlement
  calc/approval/disbursal action, COBRA approval + action for US employees, closeout), following
  the same ModelTable/ModelForm/GateBadge patterns as Payroll's screens. `useStartExit`,
  `useDeprovision`, `useDisburseFinalSettlement`, `useSendCobraNotice` added to `hooks.ts`.
  `nav.ts` promotes "Exit" from the placeholder `soon` list to a real link.
- Verified end to end against a real running API, worker and Postgres via `curl`, matching the
  exact request/response shapes the new hooks and components use.

## FE-13 (trimmed scope): a role-matrix smoke test and an accessibility pass

The full FE-13 outline (self-ID/EEO-1 aggregates, ops tenant-scoping audit, a Jev shadow report,
full a11y/perf/responsive/handoff docs) assumes backend support that doesn't exist yet for most of
it; building those screens now would mean inventing scope against nothing real, the same trap FE-9
originally risked (docs/integration-notes.md's "Decisions made"). Scoped down instead to what's
genuinely checkable today: do the screens built in FE-7 through FE-12 actually work for every role,
and are they accessible.

- **New: `frontend/src/features/fe13.test.tsx`** -- none of Time and leave, Payroll, Exit or
  Reference data had *any* frontend test coverage before this (only `live.test.ts`'s integration
  suite touches them, and it's skipped without a running backend). Three things, all against the
  mock backend:
  - A role matrix: all 9 roles x all 4 screens (36 renders) asserting a real `<h1>` always appears,
    never a crash -- these pages gate access per-section/button, not at the top level, so this is a
    genuine regression guard for a role x screen combination no single existing test exercised.
  - Nav visibility for "Payroll"/"Exit" checked against `canReadTable`, not a hardcoded role list
    (same principle `nav.ts`'s own comment states): a role sees the link if and only if the
    contract says it can read the underlying table.
  - An accessibility pass (`jest-axe`, same pattern as `people.test.tsx`'s) across every tab of
    Time and leave, and across Payroll/Exit/Reference data: no automated violations.
- No new backend work and no mock-handler additions for `/exit`, `/payroll`, `/timekeeping`,
  `/benefits`, `/expenses` -- mock parity for these routes was explicitly deferred earlier this
  session ("test data is fine"), and the smoke test only renders these pages (GETs the mock already
  answers), never clicks their action buttons, so no gap was hit.

## Decisions made

- Keep `api/`'s ownership of the HTTP layer, the worker runner and the enum scanner: the backend
  ships none of these, by design, and nothing changed that would justify revisiting it.
- Payroll's direct-call functions (not queue handlers) mean the API needs explicit action
  endpoints (e.g. `POST /payroll/runs`, `POST /payroll/runs/{id}/disburse`) rather than relying on
  the queue worker the way Hire and Exit can.
- The Start-hiring dialog collects every new-hire field up front rather than adding a second
  "finish onboarding setup" step: matches the backend's own test convention (`NEW_HIRE_CONTEXT`),
  and there's nowhere else in the current flow to patch these in before the steps that need them
  run automatically.

## Asks for the backend (non-blocking; logged, not acted on)

- Finding 3: hiring managers cannot see the candidate they're interviewing until that candidate
  becomes an employee. Looks unintended for the person doing the interview -- worth a product
  decision on whether `candidate`'s person-scope policy should allow the assigned interviewer to
  see masked/full details before conversion.
- Finding 7: `document` and `checklist_task` have no person-scope row policy. Not exploitable
  through the API today (callers only ever query their own subject), but worth a security review
  before any screen queries these tables more broadly.
- Finding 9: a second `start_hire()` call for an already-hired-for position raises `WorkflowError`
  instead of returning the existing instance, because `start_hire()` unconditionally fires three
  `"advance"` transitions after `open_requisition`/`engine.start()` already no-op idempotently.
  Low-risk, API-side 409 mapping already covers it, but a backend-side fix (check instance state
  before firing) would remove the need for that workaround.
- New, found in Phase 2: `employee.aadhaar_last4` and `employee.aadhaar_ekyc_ref` are modelled
  `NOT NULL` regardless of jurisdiction (tagged `IN` in the model, but the column itself carries no
  conditional constraint), so every hire -- including a US one -- needs a value, even though the
  field is meaningless outside India. The backend's own test fixtures already work around this
  with a placeholder (`"0000"`/`"1234"`); the Start-hiring dialog now has to ask for it on every
  hire too. Same shape as findings 10/19/20 ("can't reference what doesn't exist yet"), one column
  over: worth either making the column nullable outside India or giving the model a per-jurisdiction
  NOT NULL concept.
- New, found in Phase 3: `app_user`'s per-column grants split oddly across the tenant-side human
  roles that can write it at all. `tenant_it` (table_acl `I: 4`, write) gets
  `INSERT/UPDATE (role, employee_id, is_active, mfa_enrolled, last_login_at)` -- everything except
  `email`. `tenant_founder` and `daydor_ops` get `email` too. IT provisioning an account without
  being able to set its own sign-in address looks like an oversight rather than intent (nothing in
  the model's narrative suggests founders, not IT, should pick people's work email addresses);
  worth checking whether `email` belongs in IT's column grant too.
- New, found in FE-7/FE-9: `time_punch`'s table_acl shows `tenant_manager` at write level, but the
  real per-column grant on `punched_at` itself is read-only for managers -- every other column
  (`employee_id`, `kind`, `source`) is writable. Since `punched_at` is `NOT NULL`, a manager can in
  practice never insert a `time_punch` row at all despite the table-level grant saying otherwise.
  Same shape as finding 16, one table over.
- New, found in FE-9: `statutory_rate_rule`/`pt_slab_rule`'s table_acl shows `daydor_ops` at write
  level, matching `docs/sprint-plan.md`'s own claim that ops maintains these jurisdiction packs --
  but the real per-column `GRANT` in `0003_model_security.sql` gives `INSERT`/`UPDATE` to
  `daydor_admin` only; ops gets `SELECT`. Same shape as the two findings above, meaning there is
  currently no practically-reachable way to maintain these rates day to day (`daydor_admin` is
  described as break-glass, two-approver platform access, not a routine jurisdiction-pack editor).
  Worth checking whether `daydor_ops` should have the column grant the sprint plan says it does.
- New, found in FE-11/FE-12, same shape as finding 9 but worse: `start_exit()` is not safely
  idempotent either. `initiate_termination()` is idempotent on `employee_id` (returns the existing
  row rather than raising), but `start_exit()` then unconditionally fires two `"advance"` events
  with no `event_id` after `engine.start()` -- and because `engine.fire()`'s duplicate check is
  only applied `if event_id`, these calls skip it entirely and blindly advance the instance's
  *current* state by two steps, regardless of what state that is or what's already in flight. A
  second `POST /exit/start` for an employee already mid-exit doesn't raise or no-op: it silently
  fast-forwards the real instance past steps that never ran (confirmed end to end -- a second call
  made during `s02_legal_hold_check` landed the instance on `s06_final_settlement_calc`, waiting on
  `g_finalpay`, having skipped the actual deprovisioning/device-return work and corrupted the
  `event_id` audit trail along the way). Worked around at the API layer (`exit.py`'s `/exit/start`
  now checks for an existing `termination` row for the employee and returns 409 before ever calling
  `start_exit()`), but finding 9's suggested fix -- check instance state before firing, inside the
  flow's own `start_*()` function -- would close this for good, and should probably be checked for
  every other flow's `start_*()` too.
