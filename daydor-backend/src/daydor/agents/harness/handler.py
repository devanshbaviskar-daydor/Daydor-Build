"""Turns an LLM worker's spec into a queue handler: propose, validate, store, then commit or hold.

    0. the worker's rollout stage in this tenant (shadow, canary, ga; see daydor.agents.rollout), the model provider's circuit
       (open: defer the job, it is not the job's fault) and the tenant's monthly AI budget are checked before any model call
    1. reuse a stored, valid proposal for this run if there is one (a retry, or a job released after approval, does not ask the
       model again); otherwise build the context, run the bounded loop, validate, and store the result with every model call
    2. autonomy decides what happens to a valid proposal:
         auto    commit it
         review  commit it; the Worker leaves the run for a person to acknowledge and holds the jobs it enqueued
         approve hold the run behind g_agent_action *with the proposal already stored*, so the person approves what the model
                 actually wrote, and the same proposal is committed on release
       shadow  stops after the proposal is stored: recorded, never applied
       canary  commits like any other stage, but the Worker treats the run as `review` (see daydor.agents.runs)
    3. committing is the worker's own domain function, run in the worker's own session: a misled model cannot do more than the
       worker's grants allow

The handler never raises for an agent-side failure (budget, protocol, invalid proposal, model error): it returns `_agent_fail`,
so the transaction that holds the model-call records commits and the Worker fails the run and the job with the right code.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping
from uuid import UUID

from sqlalchemy import Connection, text

from daydor import circuit
from daydor.agents import rollout
from daydor.agents.harness import context as ctx_mod
from daydor.agents.harness.client import ClaudeClient, ModelClient, ModelError, model_for_tier
from daydor.agents.harness.loop import AgentError, Budgets, CallRecord, Spent, run_loop
from daydor.agents.harness.prompts import load_prompt, load_schema
from daydor.agents.harness.tools import ToolSpec
from daydor.agents.roles import worker_records
from daydor.queue.worker import Job

Context = dict[str, Any]


class ProviderNotConfigured(AgentError):
    code = "ProviderNotConfigured"


class TenantBudgetExceeded(AgentError):
    code = "TenantBudgetExceeded"


def default_client() -> ModelClient:
    """DAYDOR_MODEL_PROVIDER=claude turns the real client on. Anything else fails closed: no worker calls a model by accident."""
    if os.environ.get("DAYDOR_MODEL_PROVIDER", "").lower() == "claude":
        return ClaudeClient()
    raise ProviderNotConfigured("DAYDOR_MODEL_PROVIDER is not set to 'claude'")


@dataclass(frozen=True)
class LLMWorkerSpec:
    worker: str
    tools: Mapping[str, ToolSpec]
    build_context: Callable[[Connection, Job], tuple[Context, list[ctx_mod.Untrusted]]]
    rules: Callable[[Mapping[str, Any], Mapping[str, Any]], list[str]]               # (proposal, context) -> problems
    commit: Callable[[Connection, Job, Mapping[str, Any], Mapping[str, Any]], dict]   # runs in the worker's own session


def _within_tenant_cap(b: Budgets, spent: Spent, head) -> Budgets:
    """The run's limits, tightened so this run cannot spend more than the tenant has left this month. The caps are totals, the run's
    limits are totals too, so what the run has already spent counts on both sides."""
    changes: dict[str, Any] = {}
    if head.cap_tokens is not None:
        changes["max_total_tokens"] = spent.input_tokens + spent.output_tokens + max(head.cap_tokens - head.used_tokens, 0)
    if head.cap_usd is not None:
        cap = spent.cost_usd + max(float(head.cap_usd - head.used_usd), 0.0)
        changes["max_cost_usd"] = cap if b.max_cost_usd is None else min(b.max_cost_usd, cap)
    return replace(b, **changes) if changes else b


def _record(conn: Connection, run_id: UUID, prompt_version: str, r: CallRecord) -> None:
    conn.execute(text("SELECT app.record_agent_model_call(CAST(:r AS uuid), CAST(:t AS integer), CAST(:m AS text), CAST(:v AS text), "
                      "CAST(:i AS integer), CAST(:o AS integer), CAST(:c AS numeric), CAST(:l AS integer), CAST(:s AS text), "
                      "CAST(:n AS text[]), CAST(:e AS text))"),
                 {"r": run_id, "t": r.turn, "m": r.model, "v": prompt_version, "i": r.input_tokens, "o": r.output_tokens,
                  "c": r.cost_usd, "l": r.latency_ms, "s": r.stop_reason,
                  "n": "{" + ",".join(f'"{x}"' for x in r.tool_names) + "}", "e": r.error})


def make_handler(spec: LLMWorkerSpec, client_factory: Callable[[], ModelClient] = default_client):
    rec = next(r for r in worker_records() if r["worker"] == spec.worker)
    contract = rec["contract"]
    if rec["kind"] != "llm" or not contract.get("built"):
        raise ValueError(f"{spec.worker} has no built llm contract")
    unknown = set(contract["tools"]) ^ set(spec.tools)
    if unknown:
        raise ValueError(f"{spec.worker}: tools in the contract and in the spec differ: {sorted(unknown)}")
    ctx_mod.check_refs(contract["context"], contract["max_data_class"])
    schema = load_schema(contract["output_schema"])
    budgets = Budgets.from_contract(contract["budgets"])

    def handle(conn: Connection, job: Job) -> dict:
        run_id = conn.execute(text("SELECT app.agent_task_run_id()")).scalar_one()
        if run_id is None:
            raise RuntimeError("an LLM worker must run under an agent run (register it with worker=)")
        existing = conn.execute(text("SELECT * FROM app.agent_proposal_for(:r)"), {"r": run_id}).one_or_none()
        if existing is not None and existing.status == "committed":
            return {"committed": True, "proposal": str(existing.id)}
        if existing is not None and existing.status == "shadow":
            return {"shadow": True, "proposal": str(existing.id)}
        stage = rollout.stage_for(conn, spec.worker)

        context, untrusted = spec.build_context(conn, job)
        ctx_mod.check_context(context, contract["context"])

        if existing is not None and existing.valid:
            proposal, proposal_id = existing.proposal, existing.id
        else:
            gate = circuit.allow(conn, circuit.MODEL_PROVIDER)
            if not gate.allowed:                      # nothing is wrong with the job: try again when the circuit may have closed
                return {"_agent_defer": gate.retry_after_s, "reason": "the model provider's circuit is open"}
            head = conn.execute(text("SELECT * FROM app.tenant_ai_headroom()")).one()
            if ((head.cap_tokens is not None and head.used_tokens >= head.cap_tokens)
                    or (head.cap_usd is not None and head.used_usd >= head.cap_usd)):
                return {"_agent_fail": TenantBudgetExceeded.code, "error": "this tenant's AI budget for the month is used up"}
            usage = conn.execute(text("SELECT * FROM app.agent_run_usage(:r)"), {"r": run_id}).one()
            spent = Spent(turns=usage.turns, input_tokens=int(usage.input_tokens), output_tokens=int(usage.output_tokens),
                          cost_usd=float(usage.cost_usd))
            calls: list[CallRecord] = []
            failure: AgentError | ModelError | None = None
            proposal = None
            try:
                system = load_prompt(spec.worker, contract["prompt_version"], contract["prompt_sha256"])
                user = ctx_mod.render_context(context) + "\n" + ctx_mod.render_untrusted(untrusted)
                result = run_loop(client_factory(), conn, model=model_for_tier(rec["llm_tier"]), system=system,
                                  user_message=user, tools=spec.tools, output_schema=schema, context=context, budgets=_within_tenant_cap(budgets, spent, head),
                                  rules=lambda p: spec.rules(p, context), record=calls.append, spent=spent)
                proposal = result.proposal
            except (AgentError, ModelError) as exc:
                failure = exc
            for c in calls:
                _record(conn, run_id, contract["prompt_version"], c)
            if isinstance(failure, ModelError):
                circuit.record(conn, circuit.MODEL_PROVIDER, False, str(failure))
            elif calls:                                # the provider answered, whatever the answer was worth
                circuit.record(conn, circuit.MODEL_PROVIDER, True)
            if failure is not None:
                from daydor.agents.harness.loop import ProposalInvalid
                if isinstance(failure, ProposalInvalid):
                    conn.execute(text("SELECT app.store_agent_proposal(:r, :v, :s, CAST('{}' AS jsonb), false, CAST(:e AS jsonb))"),
                                 {"r": run_id, "v": contract["prompt_version"], "s": contract["output_schema"],
                                  "e": __import__("json").dumps(str(failure).split("; "))})
                return {"_agent_fail": getattr(failure, "code", type(failure).__name__), "error": str(failure)[:300]}
            proposal_id = conn.execute(
                text("SELECT app.store_agent_proposal(:r, :v, :s, CAST(:p AS jsonb), true)"),
                {"r": run_id, "v": contract["prompt_version"], "s": contract["output_schema"],
                 "p": __import__("json").dumps(proposal)}).scalar_one()

        if stage == "shadow":                                           # recorded, never applied
            conn.execute(text("SELECT app.mark_agent_proposal(:r, 'shadow')"), {"r": run_id})
            return {"shadow": True, "proposal": str(proposal_id)}
        effective = conn.execute(text("SELECT app.worker_effective_autonomy(:w)"), {"w": spec.worker}).scalar_one()
        decision = conn.execute(text("SELECT app.agent_run_decision(:r)"), {"r": run_id}).scalar_one()
        if effective == "approve" and decision != "approved":
            return {"_agent_hold": str(proposal_id)}                    # the person approves what the model actually wrote
        outcome = spec.commit(conn, job, proposal, context)
        conn.execute(text("SELECT app.mark_agent_proposal(:r, 'committed')"), {"r": run_id})
        return {**outcome, "proposal": str(proposal_id)}

    return handle
