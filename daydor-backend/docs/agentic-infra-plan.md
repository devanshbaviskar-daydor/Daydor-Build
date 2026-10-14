# Agentic infrastructure: gaps and the plan

Written Oct 13 2026, from the design discussion of the same week, checked against the code. The architecture that
discussion recommends (workflow-first, per-worker least privilege, deciders that are soft and humans that are hard, LLMs
only inside a step) is the one the backend already follows. This document says what is true today, where the discussion's
guesses differ from the repo, what is missing, and the order to build it.

## 1. What the discussion guessed, and what the registry says

The registry classifies every worker from the model's data classes, not from its name (ADR-004), and tests enforce it.

| The discussion | The registry today |
|---|---|
| "15 to 20 workers genuinely need an LLM" | **5 `llm` workers** (`requisition-drafter`, `interview-scheduler`, `knowledge-transfer-coordinator`, `vendor-bill-processor`, `contractor-invoice-processor`) and **1 model assist** (`expense-policy-checker` extracts receipt fields). 55 rules, 15 integrations, 10 monitors, 4 deciders. |
| `onboarding-checklist-builder`, `case-intake-router`, `qle-validator`, `punch-validator` as LLM or Jev | All four are **rules**: their scope includes C3, C4 or encrypted tables, and a model may never touch those (ADR-004, tested). `offer-letter-generator` is a rule at `approve`. |
| Jev deciders | **Laya** deciders (ADR-005), 4 of them, soft, shadow-first, calibration-gated in the database. |
| One orchestrator per domain | None. The state machines are the orchestrator (ADR-001); cross-step work is a queue job. |

So the 15 to 20 is an upper bound that the data classes already cut to about 6, and the pressure runs the other way: a
few more workers will want a model for drafting, which is a policy question each time (ADR-006), not an engineering one.

## 2. What exists, against the discussion's six sections

| Section | State |
|---|---|
| Workers vs deciders vs LLMs | **Done.** Kinds, autonomy defaults, effect ladder, "an LLM is never the final decider": a decider only feeds a hard gate, an LLM worker cannot have an irreversible effect, nothing but a person resolves a hard gate. |
| Workflow-first architecture | **Done** for hire, payroll and exit (engine, definitions as data, gates, timers). |
| Registry as data, generated roles | **Done.** 89 workers plus 4 platform actors, `app.worker_definition`, one NOLOGIN role each with derived column grants, guarded columns to named owners, fail-closed enabled flag, tenant policy that can only lower autonomy. |
| Propose, validate, commit; bounded tool loop; context builder; injection | **Not built.** `agents/base.py` is a sketch. |
| Rollout, evals, trace, kill switches, inbox | **Partly.** Kill switches (worker and tenant) and soft-gate shadow mode exist. No trace spine, no evals, no rollout states for LLM workers, no cost accounting. |
| Build vs adopt | Decided: Postgres is the spine. `anthropic` is installed; nothing calls it. |

## 3. The gaps

Ordered by how much else depends on them. "Verified" means I checked the code.

| # | Gap | Why it matters |
|---|---|---|
| G1 | **Autonomy is data, not behaviour.** `effective autonomy` is computed (`app.worker_effective_autonomy`) and returned by `assert_worker_enabled`, and **no code reads it** (verified: no use outside the registry). A tenant that sets a worker to `approve` changes nothing. | The promise of "suggest only / act with review / act autonomously per tenant" is not kept. |
| G2 | **No trace spine.** `agent_task_run` exists in the model ("one row per agent worker execution", writer "every worker") and is **never written** (verified). `audit_log`, `gate_evaluation` and `approval_request` carry an `agent_task_run_id` that is always NULL. | Without it there is no "one trace per piece of work", no durable idempotency record for irreversible workers, and no place to hang a proposal or a review. |
| G3 | **No LLM runtime.** No model client interface, tool loop, context builder, prompt registry, budgets, or propose-validate-commit. | The 5 LLM workers are deterministic placeholders; nothing can safely run a model yet. |
| G4 | **Registry has no contract for LLM workers.** `llm_tier` exists; no prompt version, tool list, highest data class, token, time and cost budgets, no typed input and output schema, idempotency template or "gates it may request". | The runtime has nothing to be generated from. |
| G5 | **No rollout path for a worker version** (shadow, canary tenants, general availability). Soft gates have shadow mode; workers do not. | Prompt and model changes would ship to everyone at once. |
| G6 | **No evals.** No golden sets, no CI (the workflow file was removed). | Nothing catches a prompt or model regression. |
| G7 | **Events are not choreography yet.** The only subscriptions are `gate.resolved`. New events (`clock.*`, `employee.hired`) have no consumers. | "Cross-domain coordination is choreography via events" is a sentence, not a mechanism. |
| G8 | **Approvals have columns for deadlines and escalation, and nothing uses them** (verified: `escalated_at` is never set; no timer). The statutory-clock events from Sprint 13 have no inbox. | A pending approval can wait forever; there is no human surface for agent proposals. |
| G9 | **No front door.** The API has typed endpoints; there is no command catalogue an intent agent could target and no validation loop that asks back. | The one place an LLM orchestrates does not exist. |
| G10 | **Integrations are all fakes**, with no circuit breaker, no webhook inbox, no per-vendor budget. | Real vendors fail in ways the queue's retry alone does not handle. |
| G11 | **No cost or token accounting**, per worker or per tenant. | Budgets cannot be enforced or reported. |
| G12 | **Tenants cannot set autonomy** from the product: the table exists, no API or UI. | G1's controls have no hands. |

## 4. The plan

Each phase ends with tests green and a demo. A phase does not start until the previous one's seam is real.

**Phase A: the spine (G1, G2).** Build first because everything else hangs on it.
- `agent_task_run` becomes real: one row per worker job, opened and closed in its own transactions so a failed job still
  leaves a record, idempotent on the job, linked to `audit_log`, `gate_evaluation` and `approval_request`.
- Autonomy becomes behaviour. `approve` raised by a tenant above the worker's default **holds the job** behind a new hard
  gate `g_agent_action` (subject: the run; approver: the worker's owner role) and re-runs it when approved; `review` lets it act
  and leaves the run `review_pending` until a person acknowledges it; `auto` is as today.
- A trace function walks workflow instance, job, run, gate evaluations, approvals and audit rows.
- *Built in this change.*

**Phase B: the LLM runtime (G3, G4). Built Oct 13 (`0041`, `0042`; `docs/agent-harness.md`).**
- Registry contract for `llm` workers: model tier, pinned prompt version, allowed tools (generated from scope), highest data
  class, token, time and cost budgets, typed input and output schemas, idempotency template, gates it may request.
- `ModelClient` interface with a Claude implementation (Messages API, bounded tool use) and a scripted fake for tests; a CI
  suite never calls the network.
- Propose, validate, commit: the model returns a typed proposal; schema and business-rule validation run; the domain service
  commits inside the worker's own role. A bounded tool loop (call cap, timeout, budget). A context builder that reads only
  the declared, class-capped columns. Untrusted content (resumes, receipts, emails) is wrapped as data and anything extracted
  passes typed validation before it can reach a tool.
- Reference worker: `requisition-drafter` end to end on the fake, then on the real client behind a flag.

**Phase C: safety and operations (G5, G6, G11).**
- Worker versions (`shadow`, `canary`, `ga` per tenant) for LLM workers; shadow means the proposal is recorded next to what
  the deterministic path did, never applied.
- Golden sets and an eval runner per LLM worker and decider; CI that runs them on every prompt or model change.
- Token and cost accounting on the run; budget enforcement and per-tenant caps; a circuit breaker per integration.

**Phase D: the human surface and choreography (G7, G8, G12).**
- Approvals with deadlines and escalation timers; a proposals and reviews inbox driven by `agent_task_run`; consumers for
  `clock.*` events; the first real cross-domain subscriptions.
- Tenant autonomy controls in the API and UI.

**Phase E: the front door (G9).** A command catalogue generated from the API's typed endpoints; an intent agent that
produces a typed command, validates it, asks back for what is missing and never executes a step.

**Phase F: real integrations and production (G10).** Vendor adapters (MCP where a vendor ships one), webhook inbox, CI
and deployment, observability, the Laya production pin.

## 5. Decisions to make along the way
1. Which of the 5 `llm` workers ships a model first, and whether any worker outside them should be allowed one (ADR-006 is
   the gate for restricted data; everything else is a per-worker policy call).
2. Model tiers and the cost ceiling per tenant.
3. Whether `review` should require an acknowledgement before the next step of a workflow proceeds (this change does not block).
4. The intent agent's authority: typed command only (recommended) or also able to open gates.

## 6. What Phase A changed (built Oct 13, migration 0040)
G1 and G2 are closed (finding 31). Every job of a real worker opens an `agent_task_run`; a tenant that raised a worker's autonomy above its
default holds the job behind `g_agent_action` (approve) or flags it `review_pending` (review); `app.agent_run_trace` gives the trace.
Platform actors are untracked. `docs/worker-classification.csv` now carries the scope columns the discussion asked for as the registry seed
(`uses_model`, owner, triggers, DB reads and writes, whether it requests approvals, gates, restricted tables). Phase B is next.

## 7. What Phase B changed (built Oct 13, migrations 0041 and 0042)
G3 and G4 are closed for the reference worker. `daydor.agents.harness` is the runtime (model client interface with a Claude implementation
and a scripted fake, bounded tool loop, declared context, untrusted-text fencing, pinned prompts, propose-validate-store-commit);
`requisition-drafter` is the reference worker with a registry `contract`. Decisions taken: the first LLM worker is `requisition-drafter`; a
model never opens gates; `review` blocks the next workflow step until acknowledged (jobs enqueued under review are held, `reject` cancels
them); tiers map to Haiku, Sonnet and Opus by environment, prices are configuration, never assumed; no per-tenant cost cap yet (Phase C).
Not done: running against the real API, wiring a worker into a flow, per-tenant caps, rollout states, evals (Phase C).


## 8. What Phase C changed (built Oct 14, migration 0043)
G5, G6 and G11 are closed for the reference worker. **Rollout:** an LLM worker is `shadow` in every tenant until Daydor promotes it; the database
requires a passing eval on the prompt in force for canary, and a live eval, a canary on the same prompt, 5 committed runs and none rejected for
general availability; a new prompt drops it back to shadow; a tenant can step back, never forward. **Evals:** golden set per worker
(`registry/evals/`), replay in CI (`python -m daydor.agents.evals`, also a stale-set tripwire), live runs on purpose, append-only results.
**Cost:** per-tenant monthly caps (dollars and/or tokens, set by ops), enforced before and during a run; usage view. **Circuit breaker:**
`model_provider`, deferring jobs without spending attempts. Decisions taken: canary needs 5 runs; no cap row means no cap; the first cap values
are Daydor's to set per tenant, none is built in. Not done: a live eval has never been run against the real API (so nothing can reach ga yet),
per-integration breakers for vendor adapters (none is wired), alerts when a circuit opens or a tenant nears its cap (Phase D).

## 9. What Phase D changed (built Oct 14, migration 0044)
G7, G8 and G12 are closed for what exists today. **Deadlines and escalation:** every pending approval gets the gate's response window
(`app.gate_sla`: 48 h by default, 24 h for `g_pay_disburse`, `g_it_deprov`, `g_cobra`); an hourly per-tenant sweep (`daydor.approval_sla`) escalates
a late one once (`approval.escalated`, `escalated_at`). Escalation only *notifies* the founder: it never changes who may resolve a gate and never
expires or decides anything. **Consumers:** `clock.due_soon`, `clock.overdue` and `approval.escalated` go to the `notify` queue and become rows in
`app.notification` for the role that must act (`daydor.notifications`; deduplicated; a role reads only its own, the founder and Daydor staff read all).
**Inbox:** `app.inbox()` and `GET /api/inbox`: approvals the caller's role may decide, agent runs waiting for review by the worker's owner (the founder
sees all), notifications; most urgent first; `acknowledge`/`reject` a review and `dismiss` a notification over HTTP. **Tenant controls:**
`app.tenant_worker_controls()`, `app.set_worker_control()` and `GET/PUT /api/worker-controls` for the founder and HR: more careful, never less, and an off
switch, with the rollout stage of LLM workers shown (only Daydor moves it forward). **Timers:** `daydor.schedules.ensure_platform_schedules` starts the
clock scan and the approval sweep for every active tenant (`app.platform_tenants()`); the API worker runs it at start and every 6 hours.
Decisions taken: the escalation window is 48 h (24 h for the three time-sensitive gates), the escalation target is the founder, one escalation per
request. Not done: a React screen for the inbox and the controls (the endpoints are the contract), e-mail or chat delivery of notifications, and a
second escalation level. The "first real cross-domain subscriptions" are the notification consumers; no flow reacts to another flow's events yet.
