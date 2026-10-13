"""The bounded tool loop: a model, a few read-only tools, a typed way to finish, and hard limits on all of it."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import jsonschema
from sqlalchemy import Connection

from daydor.agents.harness.client import ModelClient, ModelError, ModelTurn, ToolDef, cost_usd
from daydor.agents.harness.tools import MAX_RESULT_CHARS, SUBMIT, ToolArgError, ToolSpec, submit_tool

MAX_REFUSALS = 2          # calls to tools the worker does not have; a model that keeps trying is not behaving
MAX_NUDGES = 1            # a turn with no tool call at all


class AgentError(RuntimeError):
    """The run cannot produce a trustworthy proposal. `code` is what the run records."""
    code = "AgentError"


class BudgetExceeded(AgentError):
    code = "BudgetExceeded"


class ProtocolError(AgentError):
    code = "ProtocolError"


class ProposalInvalid(AgentError):
    code = "ProposalInvalid"


@dataclass(frozen=True)
class Budgets:
    max_turns: int
    max_tool_calls: int
    max_input_tokens: int
    max_output_tokens: int
    timeout_s: float
    max_cost_usd: float | None = None

    @classmethod
    def from_contract(cls, b: Mapping[str, Any]) -> "Budgets":
        return cls(int(b["max_turns"]), int(b["max_tool_calls"]), int(b["max_input_tokens"]), int(b["max_output_tokens"]),
                   float(b["timeout_s"]), float(b["max_cost_usd"]) if b.get("max_cost_usd") is not None else None)


@dataclass
class Spent:
    """What a run has used, across every attempt (the database's own count seeds it, so retries do not reset a budget)."""
    turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    tool_calls: int = 0


@dataclass(frozen=True)
class CallRecord:
    turn: int
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    latency_ms: int
    stop_reason: str
    tool_names: tuple[str, ...]
    error: str | None = None


@dataclass
class LoopResult:
    proposal: dict[str, Any] | None
    errors: list[str] = field(default_factory=list)
    spent: Spent = field(default_factory=Spent)


def _check_budgets(b: Budgets, spent: Spent, started: float) -> None:
    if spent.turns >= b.max_turns:
        raise BudgetExceeded(f"turn limit {b.max_turns} reached")
    if spent.input_tokens >= b.max_input_tokens:
        raise BudgetExceeded(f"input token limit {b.max_input_tokens} reached")
    if spent.output_tokens >= b.max_output_tokens:
        raise BudgetExceeded(f"output token limit {b.max_output_tokens} reached")
    if time.monotonic() - started >= b.timeout_s:
        raise BudgetExceeded(f"time limit {b.timeout_s}s reached")
    if b.max_cost_usd is not None and spent.cost_usd >= b.max_cost_usd:
        raise BudgetExceeded(f"cost limit ${b.max_cost_usd} reached")


def run_loop(client: ModelClient, conn: Connection, *, model: str, system: str, user_message: str,
             tools: Mapping[str, ToolSpec], output_schema: Mapping[str, Any], context: Mapping[str, Any],
             budgets: Budgets, rules: Callable[[Mapping[str, Any]], list[str]] | None = None,
             record: Callable[[CallRecord], None] | None = None, spent: Spent | None = None) -> LoopResult:
    """Run until the model submits a valid proposal, or a limit is hit. Raises BudgetExceeded or ProtocolError; a proposal
    that stays invalid after the model's chances to repair it raises ProposalInvalid with the problems."""
    spent = spent or Spent()
    started = time.monotonic()
    defs: list[ToolDef] = [t.definition() for t in tools.values()] + [submit_tool(dict(output_schema))]
    validator = jsonschema.Draft202012Validator(dict(output_schema))
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
    refusals = nudges = 0
    last_errors: list[str] = []

    while True:
        _check_budgets(budgets, spent, started)
        remaining_out = max(1, budgets.max_output_tokens - spent.output_tokens)
        try:
            t: ModelTurn = client.complete(model=model, system=system, messages=messages, tools=defs,
                                           max_tokens=remaining_out, timeout_s=max(1.0, budgets.timeout_s - (time.monotonic() - started)))
        except ModelError as exc:
            spent.turns += 1
            if record:
                record(CallRecord(spent.turns, model, 0, 0, None, 0, "error", (), str(exc)))
            raise
        spent.turns += 1
        spent.input_tokens += t.input_tokens
        spent.output_tokens += t.output_tokens
        cost = cost_usd(t.model, t.input_tokens, t.output_tokens)
        spent.cost_usd += cost or 0.0
        if record:
            record(CallRecord(spent.turns, t.model, t.input_tokens, t.output_tokens, cost, t.latency_ms, t.stop_reason,
                              tuple(b.name or "" for b in t.tool_uses)))
        if t.stop_reason == "max_tokens":
            raise BudgetExceeded("the model ran out of output tokens mid-answer")

        uses = t.tool_uses
        if not uses:                                                          # talked instead of calling a tool
            nudges += 1
            if nudges > MAX_NUDGES:
                raise ProtocolError("the model did not call submit_proposal")
            messages.append({"role": "assistant", "content": [b.as_message() for b in t.blocks] or [{"type": "text", "text": "..."}]})
            messages.append({"role": "user", "content": "Finish by calling submit_proposal with your draft. Do not reply in plain text."})
            continue

        messages.append({"role": "assistant", "content": [b.as_message() for b in t.blocks]})
        results: list[dict[str, Any]] = []
        for use in uses:
            args = use.input or {}
            if use.name == SUBMIT:
                problems = [f"{'/'.join(map(str, e.path)) or 'proposal'}: {e.message}" for e in validator.iter_errors(args)]
                if not problems and rules:
                    problems = rules(args)
                if not problems:
                    return LoopResult(dict(args), [], spent)
                last_errors = problems
                results.append({"type": "tool_result", "tool_use_id": use.id, "is_error": True,
                                "content": "The proposal has problems. Fix them and call submit_proposal again:\n- " + "\n- ".join(problems)})
                continue
            spec = tools.get(use.name)
            if spec is None:                                                  # not one of this worker's tools
                refusals += 1
                if refusals > MAX_REFUSALS:
                    raise ProtocolError(f"the model kept calling a tool it does not have ({use.name})")
                results.append({"type": "tool_result", "tool_use_id": use.id, "is_error": True,
                                "content": f"There is no tool named {use.name}. Your tools are: {', '.join(tools) or 'none'}, and submit_proposal."})
                continue
            if spent.tool_calls >= budgets.max_tool_calls:
                raise BudgetExceeded(f"tool call limit {budgets.max_tool_calls} reached")
            spent.tool_calls += 1
            try:
                jsonschema.validate(args, spec.input_schema)
                if spec.check:
                    spec.check(args, context)
                out = json.dumps(spec.run(conn, args, context), default=str)[:MAX_RESULT_CHARS]
                results.append({"type": "tool_result", "tool_use_id": use.id, "content": out})
            except (jsonschema.ValidationError, ToolArgError) as exc:
                results.append({"type": "tool_result", "tool_use_id": use.id, "is_error": True,
                                "content": f"Those arguments are not allowed: {getattr(exc, 'message', None) or exc}"})
        messages.append({"role": "user", "content": results})
        # A model that cannot fix its proposal within its turns ends as ProposalInvalid, not as a silent budget stop.
        if spent.turns >= budgets.max_turns and last_errors:
            raise ProposalInvalid("; ".join(last_errors))
