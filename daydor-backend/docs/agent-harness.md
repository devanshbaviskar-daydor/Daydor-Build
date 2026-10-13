# The LLM harness

How a worker that uses a model is built and run (Phase B of `docs/agentic-infra-plan.md`). Reference implementation:
`daydor.agents.workers.requisition_drafter`.

## The rules it enforces
1. **A model proposes; it never decides or writes.** Its only way to finish is `submit_proposal`, whose input *is* a typed proposal.
   The proposal is validated against a JSON Schema and the worker's own rules, stored (`app.agent_proposal`), and only then committed by
   an ordinary domain function in the worker's own database role. A misled model cannot exceed the worker's grants.
2. **It is given declared context only.** `contract.context` lists `table.column` refs; each must be a real, unencrypted column no more
   sensitive than `contract.max_data_class` (never C3 or C4). A context builder that returns anything else is refused.
3. **Untrusted text is data.** Notes, resumes, receipts, emails go in `<untrusted_input>` blocks, escaped so nothing inside can open or
   close a tag, capped in length, and the prompt says it is never instructions. A tool call for a tool the worker does not have is
   refused, and a model that keeps trying is stopped. Tool arguments are tied to the trusted context (`ToolSpec.check`).
4. **Every run is bounded.** Turns, tool calls, input and output tokens, wall-clock time and (where a price is configured) cost, counted
   *across retries*. Exceeding one ends the run as `BudgetExceeded`.
5. **Nothing is implicit.** The prompt is a file pinned by sha256 in the contract; a changed prompt is a new version. The registry refuses
   an LLM worker without a contract, a contract that allows restricted data, a model that may open gates, or a prompt that no longer
   matches its pin.
6. **Autonomy decides what happens to a valid proposal.** `auto`: commit. `review` (an LLM worker's default): commit, then the run is
   `review_pending` and the jobs it enqueued are *held* until a person acknowledges it (or rejected, which cancels them). `approve`: the run
   is held behind `g_agent_action` with the proposal already stored; the person approves what the model wrote and the same proposal is
   committed on release, with no second model call.
7. **Failures leave evidence.** Every model call (model, prompt version, tokens, cost, latency, tools, error) is recorded in
   `app.agent_model_call`, and an agent-side failure returns `_agent_fail` so the records commit and the run is failed with a code
   (`BudgetExceeded`, `ProtocolError`, `ProposalInvalid`, `ModelError`, `ProviderNotConfigured`).

## Building a new LLM worker
1. In `registry/worker_classification.json` give the worker a `contract` (`built: true`, `prompt_version`, `prompt_sha256`, `context`,
   `max_data_class`, `tools`, `budgets`, `output_schema`, `idempotency`, `gates_may_request: []`) and any reviewed `extra_scope` its
   context needs. Run `python -m daydor.agents.registry` and `python -m daydor.agents.roles`; add an incremental migration for existing
   databases (see `0042`).
2. Add `registry/prompts/<worker>/<version>.md` and `registry/schemas/<name>.v1.json`.
3. Write the spec: `build_context`, `rules`, `tools`, `commit`. Commit only through domain functions the worker's role can run.
4. Test it with `ScriptedClient`; never with the network.

## Running it for real
The default client fails closed. To call Claude: `DAYDOR_MODEL_PROVIDER=claude`, `ANTHROPIC_API_KEY`, optionally
`DAYDOR_MODEL_SMALL|MEDIUM|LARGE` (defaults `claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5`) and `DAYDOR_MODEL_PRICES`
(`{"model-id": [usd_per_million_input, usd_per_million_output]}`: no price is built in, and a cost budget is enforced only where one is
configured). Nothing in the repo has run against the real API yet.
