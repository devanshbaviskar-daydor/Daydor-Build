"""Golden sets and an eval runner for LLM workers (Phase C).

A golden set is registry data: `registry/evals/<worker>/golden.json`, pinned to the prompt it was written against.

    replay   cases of kind "proposal": a recorded or hand-written model output, with what the worker's guardrails (output schema and
             business rules) must do with it. Deterministic, no model and no network, so CI runs it on every change. It tests the
             guardrails, not the model.
    live     the same cases, plus cases of kind "live": a context and untrusted text, run through the real loop against the real model.
             The model must produce a proposal that passes the guardrails and avoids what the case forbids. Costs money; run on purpose,
             and recorded, because general availability requires a passing live eval on the prompt and model in force.

A result is recorded in app.worker_eval_result with the prompt hash, so a changed prompt has no passing eval until the set is run again.
`check_current` is the CI tripwire: it fails when a prompt was changed and its golden set was not looked at.

    python -m daydor.agents.evals                              # replay every golden set, exit 1 on any failure
    python -m daydor.agents.evals --worker W --record          # also record the result (DAYDOR_DATABASE_URL, as daydor_admin)
    python -m daydor.agents.evals --worker W --live --tenant T # live, against the model in force; needs DAYDOR_MODEL_PROVIDER=claude
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema
from sqlalchemy import Connection, text

from daydor.agents import rollout
from daydor.agents.harness import context as ctx_mod
from daydor.agents.harness.handler import LLMWorkerSpec, default_client
from daydor.agents.harness.client import ModelClient, model_for_tier
from daydor.agents.harness.loop import AgentError, Budgets, run_loop
from daydor.agents.harness.prompts import load_prompt, load_schema
from daydor.agents.registry import ROOT
from daydor.agents.roles import worker_records

EVALS = ROOT / "registry" / "evals"
WORKER_MODULES = {"requisition-drafter": "daydor.agents.workers.requisition_drafter"}


@dataclass
class EvalResult:
    worker: str
    mode: str
    prompt_sha256: str
    golden_sha256: str
    models: dict
    cases: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.cases if c["passed"])

    @property
    def passed(self) -> bool:
        return self.total > 0 and self.passed_count == self.total


def golden_path(worker: str) -> Path:
    return EVALS / worker / "golden.json"


def load_golden(worker: str) -> tuple[dict, str]:
    raw = golden_path(worker).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def spec_for(worker: str) -> LLMWorkerSpec:
    return importlib.import_module(WORKER_MODULES[worker]).SPEC


def llm_workers() -> list[str]:
    return [r["worker"] for r in worker_records() if r["kind"] == "llm" and (r.get("contract") or {}).get("built")]


def check_current(worker: str) -> list[str]:
    """Problems that make a golden set stale: no set, or a set written for a different prompt or output schema than the contract's."""
    if not golden_path(worker).exists():
        return [f"{worker} has no golden set at {golden_path(worker).relative_to(ROOT)}"]
    golden, _ = load_golden(worker)
    contract = next(r for r in worker_records() if r["worker"] == worker)["contract"]
    problems = []
    if golden.get("prompt_sha256") != contract["prompt_sha256"]:
        problems.append(f"{worker}: the prompt changed since the golden set was written; run the evals, review the cases, "
                        f"and update `prompt_sha256` in the golden set")
    if golden.get("output_schema") != contract["output_schema"]:
        problems.append(f"{worker}: the golden set is for output schema {golden.get('output_schema')}, the contract says {contract['output_schema']}")
    if not any(c["kind"] == "proposal" for c in golden.get("cases", [])):
        problems.append(f"{worker}: the golden set has no replay cases")
    return problems


def _guardrails(worker: str, proposal: dict, context: dict) -> list[str]:
    """What the loop itself would send back to the model: schema errors, then the worker's business rules."""
    schema = load_schema(next(r for r in worker_records() if r["worker"] == worker)["contract"]["output_schema"])
    problems = [f"{'/'.join(map(str, e.path)) or 'proposal'}: {e.message}"
                for e in jsonschema.Draft202012Validator(schema).iter_errors(proposal)]
    return problems or spec_for(worker).rules(proposal, context)


def _judge(case: dict, problems: list[str], proposal: dict | None) -> tuple[bool, str]:
    expect = case["expect"]
    if expect["outcome"] == "accepted":
        if problems:
            return False, "rejected: " + "; ".join(problems)
        blob = json.dumps(proposal).lower()
        hit = next((w for w in expect.get("forbid", []) if w.lower() in blob), None)
        return (hit is None), (f"the proposal contains {hit!r}" if hit else "ok")
    if not problems:
        return False, "accepted, but it should have been rejected"
    needle = expect.get("contains")
    if needle and not any(needle.lower() in p.lower() for p in problems):
        return False, f"rejected for another reason: {'; '.join(problems)}"
    return True, "ok"


def replay(worker: str) -> EvalResult:
    golden, sha = load_golden(worker)
    result = EvalResult(worker, "replay", rollout.prompt_sha(worker), sha, {})
    for case in golden["cases"]:
        if case["kind"] != "proposal":
            continue
        problems = _guardrails(worker, case["proposal"], case.get("context", {}))
        ok, why = _judge(case, problems, case["proposal"])
        result.cases.append({"id": case["id"], "passed": ok, "why": why})
    return result


def live(worker: str, conn: Connection, client: ModelClient | None = None) -> EvalResult:
    """Replay cases, then the live cases through the real loop. `conn` is a session as the worker in a tenant, for its read-only tools."""
    result = replay(worker)
    result.mode, result.models = "live", rollout.models_in_force(worker)
    golden, _ = load_golden(worker)
    rec = next(r for r in worker_records() if r["worker"] == worker)
    contract, spec = rec["contract"], spec_for(worker)
    system = load_prompt(worker, contract["prompt_version"], contract["prompt_sha256"])
    client = client or default_client()
    for case in golden["cases"]:
        if case["kind"] != "live":
            continue
        context, untrusted = case["context"], [ctx_mod.Untrusted(u["source"], u["text"]) for u in case.get("untrusted", [])]
        ctx_mod.check_context(context, contract["context"])
        try:
            out = run_loop(client, conn, model=model_for_tier(rec["llm_tier"]), system=system,
                           user_message=ctx_mod.render_context(context) + "\n" + ctx_mod.render_untrusted(untrusted),
                           tools=spec.tools, output_schema=load_schema(contract["output_schema"]), context=context,
                           budgets=Budgets.from_contract(contract["budgets"]), rules=lambda p: spec.rules(p, context))
            ok, why = _judge(case, [], out.proposal)
        except AgentError as exc:
            ok, why = False, f"{type(exc).__name__}: {exc}"[:300]
        result.cases.append({"id": case["id"], "passed": ok, "why": why})
    return result


def record(conn: Connection, r: EvalResult) -> str:
    return conn.execute(text("SELECT app.record_worker_eval(:w, :m, :p, :g, CAST(:mo AS jsonb), :t, :n, CAST(:d AS jsonb))"),
                        {"w": r.worker, "m": r.mode, "p": r.prompt_sha256, "g": r.golden_sha256, "mo": json.dumps(r.models),
                         "t": r.total, "n": r.passed_count, "d": json.dumps(r.cases)}).scalar_one()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--worker", action="append", help="default: every built LLM worker")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--tenant", help="a tenant id; live mode reads through the worker's role in this tenant")
    ap.add_argument("--record", action="store_true")
    args = ap.parse_args(argv)
    workers = args.worker or llm_workers()
    failed = False
    engine = None
    if args.live or args.record:
        from daydor.db.session import make_engine
        engine = make_engine()
    for w in workers:
        if (stale := check_current(w)):
            print("\n".join(stale)); failed = True; continue
        if args.live:
            if not args.tenant:
                ap.error("--live needs --tenant")
            from daydor.agents.session import worker_session
            with worker_session(engine, w, args.tenant) as conn:
                r = live(w, conn)
        else:
            r = replay(w)
        for c in r.cases:
            print(f"  {'PASS' if c['passed'] else 'FAIL'}  {w}/{c['id']}: {c['why']}")
        print(f"{w} [{r.mode}]: {r.passed_count}/{r.total}")
        failed |= not r.passed
        if args.record:
            from daydor.db.session import tenant_session
            with tenant_session(engine, "daydor_admin") as conn:
                print("recorded", record(conn, r))
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
