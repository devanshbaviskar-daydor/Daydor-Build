# Open issues

Everything that is open, undecided or deliberately not done, in one place, so we can go through it together once the agentic-infrastructure
phases (A to F, `agentic-infra-plan.md`) are finished. Items are added as they come up and struck out when resolved, with the commit.
Started Oct 14 2026. "Needs you" means the next step is a decision only you can make.

## A. Decisions waiting on you
| # | Issue | Why it is open | Needs you |
|---|---|---|---|
| A1 | **Finding 29: nobody can write `leave_request.fmla_designation`.** | ADR-006 guards the column but no worker or role owns it. | Which role designates FMLA leave (HR is the obvious candidate), and whether it is a gated act. |
| A2 | **Finding 32: the model has no home for a job description.** | The requisition drafter's committed draft lives only in `app.agent_proposal` and a `requisition_drafted` job. | Where the text should live (a column on `job_requisition`, or on `job_posting`). It is a model change, so it needs your yes. |
| A3 | **Model-artifact push-back (13e, `docs/model-sync.md`).** | The artifact is hosted at claude.ai, and one group of changes would alter applied baselines. | Approve or amend the plan; nothing has been applied. |
| A4 | **No cap values for tenant AI budgets.** | Phase C builds the mechanism; no cap is assumed. | A default monthly cap per plan tier, and who may change it. |
| A5 | **Escalation policy numbers** (Phase D): 48 h window (24 h for `g_pay_disburse`, `g_it_deprov`, `g_cobra`), founder as target, one escalation. | I chose them. | Confirm or change; changing is a one-row migration. |
| A6 | **Canary needs 5 committed runs and none rejected** (Phase C). | I chose it. | Confirm or change. |

## B. Cannot be done without outside access or money
| # | Issue | Why |
|---|---|---|
| B1 | **Nothing has run against the real Claude API.** No live eval has ever been run, so no LLM worker can reach general availability. | Needs your API key and a spending decision. Run `python -m daydor.agents.evals --live --tenant T --record`. |
| B2 | **Laya production pin and vendoring of weights; real shadow data to fit calibrations on.** | Needs real traffic and a place to host the weights (`docs/laya-runbook.md`). |
| B3 | **All vendor integrations are fakes** (bank, tax filing, GL, background check, e-verify, and so on). | Phase F; each needs vendor credentials and a contract. |

## C. Built but incomplete
| # | Issue | Detail |
|---|---|---|
| C1 | **No React screen** for the inbox and the worker controls. | Endpoints exist (`/api/inbox`, `/api/worker-controls`); the UI is the contract's consumer. |
| C2 | **Notifications are in-app only.** | No email, chat or push delivery. |
| C3 | **One escalation level.** | A request escalates once; there is no second level or reminder. |
| C4 | **No alert when a circuit opens or a tenant nears its AI cap.** | State is visible in tables only. |
| C5 | **Circuit breaker covers the model provider only.** | Vendor adapters are fakes; each real one registers an integration (a migration). |
| C6 | **`requisition-drafter` is not wired into the hire flow.** | It is the reference worker; the flow still opens requisitions deterministically. Wiring it is a product decision. |
| C7 | **The other four `llm`-kind workers are deterministic placeholders.** (`interview-scheduler`, `knowledge-transfer-coordinator`, `vendor-bill-processor`, `contractor-invoice-processor`.) | Each is a per-worker policy call (ADR-006), then a contract, prompt, golden set. |
| C8 | **No flow reacts to another flow's events.** | The notification consumers are the only subscribers added; the plan's "cross-domain choreography" is still a sentence. |
| C9 | **`acknowledge_agent_run` and `reject_agent_run` are granted to every approver role.** | The inbox only shows a review to the worker's owner and the founder, but the database does not enforce it. Tighten if you want it enforced. |
| C10 | **Per-tenant canary: no way to see shadow-vs-human agreement.** | `app.agent_proposal_stats` counts proposals; nothing compares a shadow proposal with what a person later did. |
| C11 | **No React command bar or confirm screen for the front door.** | `/api/frontdoor/interpret` and `/commands` are the contract. The confirm step is the safety, so the screen must show the command in words and send it with the returned `idempotency_key`. |
| C12 | **`hire.start` asks for 23 fields.** | The endpoint collects offer, employee and payroll details at the start of a hire (a Sprint 2 simplification, `docs/integration-notes.md`), so the front door asks them one at a time. A real flow would collect them at the step that needs them. |
| C13 | **The front door has no live eval and only replay cases.** | Same dependency as B1. |
| C14 | **Front-door spend is not in `app.ai_usage_daily`.** | It counts against the tenant cap (`tenant_ai_headroom`) but the usage view lists workers only. |
| C15 | **Front-door lookups cover ten kinds of record, matched by name.** | Ambiguous matches are asked back; no fuzzy matching or synonyms. |
| C16 | **The front door is off for every tenant until ops enables it** (`app.frontdoor_tenant`), and there is no ops screen for that. | A one-row insert today. |

## D. Deviations and known rough edges
| # | Issue | Detail |
|---|---|---|
| D1 | `requisition-drafter` has `extra_scope` reads of `job_profile` and `department`. | Reviewed deviation (0042). |
| D2 | `worker_platform` holds INSERT on `audit_log`. | Needed so platform workers can write audit rows; worth a second look. |
| D3 | A Daydor ops session with a tenant and no user sees nothing. | By design (finding 6), but surprising in scripts. |
| D4 | Notification rows are written without `ON CONFLICT`/`RETURNING`. | Both apply the SELECT policy, and the notifier is not the audience (0044). A comment says why. |
| D5 | Clock-scan chains for a *new* tenant start only at the next `ensure_platform_schedules` run (up to 6 h). | Call it from tenant provisioning to close the gap. |
| D6 | **The dev database is stuck at 0033.** | Migration 0034 refuses to run while exit-workflow instances on version 2 are running. Tests build their own databases, so they are unaffected. |
| D7 | **`daydor-frontend/api/src/daydor_api/enums/provisional.json` is stale in your working tree.** | HEAD has the regenerated file; the working-tree copy differs, so `test_provisional_enum_file_matches_what_the_backend_writes` fails locally until you `git checkout` it or regenerate (`python scripts/gen_enums.py`). |
| D8 | The `anthropic` model ids and tiers are assumptions about what you will run. | Overridable with `DAYDOR_MODEL_SMALL|MEDIUM|LARGE`; no price is built in (`DAYDOR_MODEL_PRICES`). |

## E. Resolved
| # | Issue | Resolved in |
|---|---|---|
| E1 | `clock.due_soon` / `clock.overdue` had no consumer; `start_clock_scan` needed calling per tenant. | Phase D (0044), `daydor.notifications`, `daydor.schedules` |
| E2 | Approvals had deadline and escalation columns nothing used. | Phase D (0044) |
| E3 | Tenants could not set autonomy from the product. | Phase D: API (UI still open, C1) |
