"""The front-door agent: from what a person typed to a typed command they confirm.

What it can and cannot do, enforced here and in the database rather than asked of the model:
  * It only proposes. The proposal is validated against the reviewed catalogue and the endpoint's own request schema, and the answer
    is a command the person confirms; the app then calls the real endpoint as that person, so every permission and gate still applies.
  * It works in a READ-ONLY transaction (its only tool is a lookup), so it cannot write even if it were tricked. Its one write, the turn
    log, is a separate transaction through app.frontdoor_record.
  * No command in the catalogue decides, pays, files, posts or removes access (catalogue.FORBIDDEN_PATH), and it is only shown the
    commands the person's role may ask for.
  * An id it proposes must come from the person's own words or from a lookup it ran; an invented id is sent back as a problem.
  * What the person typed is untrusted text: fenced, escaped, capped, and never stored (the turn log keeps a hash and a length).
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Mapping

import jsonschema
from sqlalchemy import Connection, text

from daydor.agents.harness import context as ctx_mod
from daydor.agents.harness.client import ModelClient, ModelError, model_for_tier
from daydor.agents.harness.handler import ProviderNotConfigured, _within_tenant_cap, default_client
from daydor.agents.harness.loop import AgentError, Budgets, CallRecord, Spent, run_loop
from daydor.agents.harness.tools import ToolArgError, ToolSpec

from ..identity import Identity
from ..sessions import human_session
from . import catalogue as cat

PROMPT = Path(__file__).with_name("prompt_v1.md")
PROMPT_SHA256 = "d82bf9001706f41aed80225c573071da53312a33c2e0f1e019dcbe771ce6966d"
BUDGETS = Budgets(max_turns=6, max_tool_calls=5, max_input_tokens=14000, max_output_tokens=1500, timeout_s=45)
MAX_HISTORY, MAX_TURN_CHARS, MAX_MESSAGE_CHARS = 6, 1000, 1500
UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
FRONT_DOOR_ROLES = frozenset({"tenant_founder", "tenant_hr", "tenant_payroll", "tenant_it", "tenant_manager", "tenant_employee"})

OUTPUT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "additionalProperties": False, "required": ["status"],
    "properties": {
        "status": {"enum": ["command", "clarify", "unsupported"]},
        "command_id": {"type": "string", "maxLength": 80},
        "arguments": {"type": "object"},
        "question": {"type": "string", "maxLength": 300},
        "reason": {"type": "string", "maxLength": 300},
    },
}


class PromptChanged(RuntimeError):
    pass


def load_prompt() -> str:
    data = PROMPT.read_bytes()
    if hashlib.sha256(data).hexdigest() != PROMPT_SHA256:
        raise PromptChanged("the front-door prompt changed: bump the version, re-run the golden set, then update the pin")
    return data.decode()


# --------------------------------------------------------------------------- validation (deterministic; the model cannot talk its way past it)
def _label(name: str) -> str:
    return name.replace("_id", "").replace("_", " ")


def check(commands: Mapping[str, dict], proposal: Mapping[str, Any], seen_ids: set[str]) -> dict:
    """Judge a proposal. Returns {'problems': [...]} for the model to repair, or the outcome:
       command (ready) | needs_input (a command with fields still missing, or a question) | unsupported."""
    status = proposal["status"]
    if status == "unsupported":
        return {"status": "unsupported", "reason": proposal.get("reason") or "That is not something I can do from here."}
    if status == "clarify":
        if not proposal.get("question"):
            return {"problems": ["status clarify needs a question"]}
        return {"status": "needs_input", "question": proposal["question"], "missing": []}
    command = commands.get(proposal.get("command_id") or "")
    if command is None:
        return {"problems": [f"{proposal.get('command_id')!r} is not a command you may use; choose one from the catalogue"]}
    args = dict(proposal.get("arguments") or {})
    known = cat.fields(command)
    problems = [f"{k} is not a field of {command['id']}" for k in args if k not in known]
    for k, v in args.items():
        if k in known and isinstance(v, str) and UUID_RE.fullmatch(v) and v.lower() not in seen_ids:
            problems.append(f"{k}: that id did not come from the person or from a lookup; look it up or ask")
    body_props = (command["body_schema"] or {}).get("properties", {})
    sub = {"type": "object", "properties": body_props, "additionalProperties": True}
    body_given = {k: v for k, v in args.items() if k in body_props}
    problems += [f"{'/'.join(map(str, e.path)) or 'arguments'}: {e.message}"
                 for e in jsonschema.Draft202012Validator(sub, format_checker=jsonschema.FormatChecker()).iter_errors(body_given)]
    for p in command["path_params"]:
        if p["name"] in args and not (isinstance(args[p["name"]], str) and UUID_RE.fullmatch(args[p["name"]])):
            problems.append(f"{p['name']} must be an id")
    if problems:
        return {"problems": problems}
    missing = [k for k in command["required"] if k not in args or args[k] in (None, "")]
    base = {"command": command, "args": args, "missing": [{"field": k, "label": _label(k), **{a: known[k][a] for a in ("type", "format")}}
                                                          for k in missing]}
    if missing:
        question = proposal.get("question") or "I still need: " + ", ".join(_label(k) for k in missing) + "."
        return {"status": "needs_input", "question": question, **base}
    return {"status": "ready", **base}


def shape_command(command: dict, args: dict) -> dict:
    """What the app shows for confirmation and then sends: the real endpoint, the path filled in, the body."""
    path = command["path"]
    for p in command["path_params"]:
        path = path.replace("{" + p["name"] + "}", str(args[p["name"]]))
    body_props = (command["body_schema"] or {}).get("properties", {})
    body = {k: v for k, v in args.items() if k in body_props}
    query = {k: v for k, v in args.items() if k in {q["name"] for q in command.get("query_params", [])}}
    return {"id": command["id"], "method": command["method"], "path": path, "body": body or None, "query": query or None,
            "summary": command["summary"], "risk": command["risk"], "kind": command["kind"],
            "confirm_required": command["kind"] == "action", "idempotency_key": str(uuid.uuid4())}


# --------------------------------------------------------------------------- the one tool: look an id up by name, as the person
def _like(q: str) -> str:
    return "%" + re.sub(r"([\\%_])", r"\\\1", q.strip()) + "%"


LOOKUPS = {
    "employee": "SELECT id, full_name AS label FROM employee_directory WHERE full_name ILIKE :q ORDER BY full_name LIMIT 8",
    "position": ("SELECT p.id, jp.title || ' (' || d.name || ', ' || p.status || ')' AS label FROM position p "
                 "JOIN job_profile jp ON jp.id = p.job_profile_id JOIN department d ON d.id = p.department_id "
                 "WHERE jp.title ILIKE :q OR d.name ILIKE :q ORDER BY jp.title LIMIT 8"),
    "requisition": ("SELECT jr.id, jp.title || ' requisition (' || jr.status || ')' AS label FROM job_requisition jr "
                    "JOIN position p ON p.id = jr.position_id JOIN job_profile jp ON jp.id = p.job_profile_id "
                    "WHERE jp.title ILIKE :q ORDER BY jr.created_at DESC LIMIT 8"),
    "department": "SELECT id, name AS label FROM department WHERE name ILIKE :q ORDER BY name LIMIT 8",
    "location": "SELECT id, name AS label FROM location WHERE name ILIKE :q ORDER BY name LIMIT 8",
    "legal_entity": "SELECT id, name AS label FROM legal_entity WHERE name ILIKE :q ORDER BY name LIMIT 8",
    "benefit_plan": "SELECT id, plan_type || ' (' || carrier || ', ' || plan_year || ')' AS label FROM benefit_plan WHERE plan_type ILIKE :q OR carrier ILIKE :q LIMIT 8",
    "payroll_run": ("SELECT id, to_char(period_start, 'YYYY-MM-DD') || ' to ' || to_char(period_end, 'YYYY-MM-DD') || ' (' || status || ')' AS label "
                    "FROM payroll_run WHERE to_char(period_start, 'YYYY-MM-DD') ILIKE :q OR status ILIKE :q ORDER BY period_start DESC LIMIT 8"),
    "retention_policy": "SELECT id, retention_class || ' / ' || record_type AS label FROM retention_policy WHERE retention_class ILIKE :q OR record_type ILIKE :q LIMIT 8",
}


def _lookup(conn: Connection, args: Mapping[str, Any], context: Mapping[str, Any]) -> dict:
    sql = LOOKUPS[args["entity"]]
    try:
        with conn.begin_nested():                                           # a refused read must not poison the transaction
            rows = conn.execute(text(sql), {"q": _like(args["query"])}).all()
    except Exception:  # noqa: BLE001 - the person's role may not see this kind of record at all
        return {"matches": [], "note": "you cannot see that kind of record"}
    for r in rows:
        context["_seen"].add(str(r.id).lower())
    return {"matches": [{"id": str(r.id), "label": r.label} for r in rows]}


def _check_lookup(args: Mapping[str, Any], context: Mapping[str, Any]) -> None:
    if len(args["query"].strip()) < 2:
        raise ToolArgError("give at least two letters to search for")


TOOLS = {"lookup": ToolSpec(
    "lookup", "Find the id of a record by name. Returns up to 8 matches with a label. Read-only and limited to what this person may see.",
    {"type": "object", "additionalProperties": False, "required": ["entity", "query"],
     "properties": {"entity": {"enum": sorted(LOOKUPS)}, "query": {"type": "string", "maxLength": 80}}},
    _lookup, _check_lookup)}


# --------------------------------------------------------------------------- the interaction
def _sanitise_history(history: list[dict] | None) -> list[dict]:
    out = []
    for h in (history or [])[-MAX_HISTORY:]:
        who = "assistant" if h.get("role") == "assistant" else "user"
        out.append({"role": who, "text": str(h.get("text") or "")[:MAX_TURN_CHARS]})
    return out


def _gate(ident: Identity) -> Any:
    with human_session(ident) as conn:
        return conn.execute(text("SELECT * FROM app.frontdoor_gate()")).one()


def _record(ident: Identity, *, status: str, command_id: str | None, arg_names: list[str], message: str, model: str | None, spent: Spent | None,
            latency_ms: int, error: str | None, provider_ok: bool | None) -> str:
    with human_session(ident) as conn:
        return str(conn.execute(
            text("SELECT app.frontdoor_record(:s, :c, :a, :h, :n, :m, :t, :i, :o, :u, :l, :e, :p)"),
            {"s": status, "c": command_id, "a": arg_names, "h": hashlib.sha256(message.encode()).hexdigest(), "n": len(message), "m": model,
             "t": spent.turns if spent else 0, "i": spent.input_tokens if spent else 0, "o": spent.output_tokens if spent else 0,
             "u": spent.cost_usd if spent and spent.cost_usd else None, "l": latency_ms, "e": error, "p": provider_ok}).scalar_one())


def interpret(ident: Identity, message: str, history: list[dict] | None = None, partial: Mapping[str, Any] | None = None, *,
              client: ModelClient | None = None) -> dict:
    """Never raises for an agent-side problem: the answer says what happened (ready, needs_input, unsupported, unavailable)."""
    message = (message or "").strip()[:MAX_MESSAGE_CHARS]
    if not message:
        return {"status": "needs_input", "question": "What would you like to do?", "missing": []}
    started = time.monotonic()
    gate = _gate(ident)
    if not gate.allowed:
        _record(ident, status="refused", command_id=None, arg_names=[], message=message, model=None, spent=None, latency_ms=0,
                error=gate.reason, provider_ok=None)
        return {"status": "unavailable", "reason": gate.reason, "retry_after_s": gate.retry_after_s}
    try:
        client = client or default_client()
        system = load_prompt()
    except (ProviderNotConfigured, PromptChanged) as exc:
        _record(ident, status="failed", command_id=None, arg_names=[], message=message, model=None, spent=None, latency_ms=0,
                error=type(exc).__name__, provider_ok=None)
        return {"status": "unavailable", "reason": "not_configured"}

    commands = {c["id"]: c for c in cat.for_role(cat.cached(), ident.role)}
    history = _sanitise_history(history)
    # What an earlier turn already collected comes back from the app (it is the person's own input and our own lookups); the person
    # could equally type it, so its ids count as theirs.
    known_id = (partial or {}).get("id") if (partial or {}).get("id") in commands else None
    known_args = {k: v for k, v in ((partial or {}).get("args") or {}).items() if known_id and isinstance(k, str)} if known_id else {}
    context: dict[str, Any] = {"_seen": {m.lower() for t in [*history, {"text": message}] if t.get("role", "user") == "user"
                                         for m in UUID_RE.findall(t["text"])}
                               | {m.lower() for m in UUID_RE.findall(json.dumps(known_args))}}
    person = f"<person>role: {ident.role}; today: {date.today().isoformat()}</person>"
    earlier = [ctx_mod.Untrusted("person" if h["role"] == "user" else "you_asked", h["text"]) for h in history] if history else []
    carried = ([ctx_mod.Untrusted("already_collected", json.dumps({"command_id": known_id, "arguments": known_args}))] if known_id else [])
    user_message = (f"{person}\n<catalogue>\n{cat.render_for_prompt(list(commands.values()))}\n</catalogue>\n"
                    + ctx_mod.render_untrusted([*carried, *earlier, ctx_mod.Untrusted("latest_message", message)]))

    holder: dict[str, Any] = {}

    def rules(p: Mapping[str, Any]) -> list[str]:
        if p.get("status") == "command" and p.get("command_id") == known_id:          # keep what was already collected
            p = {**p, "arguments": {**known_args, **(p.get("arguments") or {})}}
        result = check(commands, p, context["_seen"])
        holder["result"] = result
        return result.get("problems", [])

    calls: list[CallRecord] = []
    spent = Spent()
    model = model_for_tier("small")
    error: str | None = None
    provider_ok: bool | None = None
    with human_session(ident) as conn:
        conn.execute(text("SET LOCAL transaction_read_only = on"))        # the agent cannot write, whatever it is told
        head = conn.execute(text("SELECT * FROM app.tenant_ai_headroom()")).one()
        try:
            run_loop(client, conn, model=model, system=system, user_message=user_message, tools=TOOLS, output_schema=OUTPUT_SCHEMA,
                     context=context, budgets=_within_tenant_cap(BUDGETS, spent, head), rules=rules, record=calls.append, spent=spent)
            provider_ok = True
        except ModelError as exc:
            error, provider_ok = f"ModelError: {exc}"[:300], False
        except AgentError as exc:
            error, provider_ok = f"{type(exc).__name__}: {exc}"[:300], bool(calls)
        except Exception as exc:  # noqa: BLE001 - a tool that fails (or is refused by the read-only transaction) ends the turn cleanly
            error, provider_ok = f"ToolError: {type(exc).__name__}"[:300], bool(calls)
    latency = int((time.monotonic() - started) * 1000)
    result = holder.get("result") if error is None else None
    if error or not result or "problems" in result:
        _record(ident, status="failed", command_id=None, arg_names=[], message=message, model=model, spent=spent, latency_ms=latency,
                error=error or "no valid proposal", provider_ok=provider_ok)
        return {"status": "unavailable", "reason": "try_again"}

    out: dict[str, Any] = {"status": result["status"]}
    command_id, arg_names = None, []
    if "command" in result:
        command_id, arg_names = result["command"]["id"], sorted(result["args"])
        if result["status"] == "ready":
            out["command"] = shape_command(result["command"], result["args"])
        else:
            out["partial"] = {"id": command_id, "summary": result["command"]["summary"], "have": sorted(result["args"]),
                              "args": result["args"]}                       # send this back with the person's answer
    for k in ("question", "missing", "reason"):
        if k in result:
            out[k] = result[k]
    out["turn_id"] = _record(ident, status=result["status"], command_id=command_id, arg_names=arg_names, message=message, model=model,
                             spent=spent, latency_ms=latency, error=None, provider_ok=provider_ok)
    return out
