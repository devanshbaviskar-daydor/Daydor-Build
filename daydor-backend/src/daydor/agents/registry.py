"""Worker registry: hand-authored classification joined with facts derived from the model.

registry/worker_classification.json   authored judgments (kind, effect, autonomy, owner, ...), plus an
                                      optional reviewed `extra_scope` {reads, writes, why} per worker
registry/platform_actors.json         roles for platform handlers that are not workers
model/daydor_model.json               derived facts (scope, gates, flows, data classes)

`build()` returns one merged record per worker; `validate()` returns rule violations.
Outputs: registry/workers.generated.json, docs/worker-classification.{md,csv}
Run: python -m daydor.agents.registry
"""
from __future__ import annotations

import csv
import io
import json
from collections import Counter, defaultdict
from pathlib import Path

from daydor.gates.registry import GUARDS, SOFT_GATES
from daydor.model import load_model

ROOT = Path(__file__).resolve().parents[3]
AUTHORED = ROOT / "registry" / "worker_classification.json"
ACTORS = ROOT / "registry" / "platform_actors.json"
GENERATED = ROOT / "registry" / "workers.generated.json"
DOC_MD = ROOT / "docs" / "worker-classification.md"
DOC_CSV = ROOT / "docs" / "worker-classification.csv"

KINDS = ("rule", "integration", "monitor", "decider", "llm")
EFFECTS = ("read_only", "internal_write", "external_notify", "external_reversible", "external_irreversible")
AUTONOMY = ("auto", "review", "approve")
TRIGGERS = ("step", "event", "timer")
OWNERS = ("hr", "payroll", "it", "founder", "ops")
# People shown as actors in the artifact's flows and worker map. They are not workers.
HUMAN_ACTORS = {"Employee", "Founder", "HR admin", "HR admin or Daydor ops", "Manager"}
PSEUDO = {"every gated worker", "every worker", "every worker (insert only)", "root orchestrator"}
WAVE_BY_FLOW = {"hire": 1, "payroll": 2, "exit": 2, "erasure": 3, "merit": 3, "threshold": 3}
RESTRICTED = ("C3", "C4")


def norm(name: str) -> str:
    return name.replace(" (aggregate view)", "")


def model_workers() -> set[str]:
    m = load_model()
    names = {norm(x) for t in m.tables for x in t.writers + t.readers}
    names |= {norm(s[2]) for f in m.flows for s in f["steps"]}
    return names - HUMAN_ACTORS - PSEUDO


def authored() -> list[dict]:
    return json.loads(AUTHORED.read_text())


def platform_actors() -> list[dict]:
    return json.loads(ACTORS.read_text())


def derived_facts(extra: dict[str, dict] | None = None) -> dict[str, dict]:
    """Per-worker facts from the model. `extra` maps worker -> reviewed extra_scope, merged into
    reads/writes before anything else is derived, so restricted tables, gates and guards all see it."""
    m = load_model()
    table_gates = defaultdict(set)
    for g in m.gates:
        for t in g["tables"]:
            table_gates[t].add(g["id"])
    restricted_tables = {t.id for t in m.tables
                         if any(c.cls in RESTRICTED or c.encrypted for c in t.columns)}
    guarded = {t for t, _, _ in GUARDS}
    facts: dict[str, dict] = {}
    for name in model_workers():
        facts[name] = {"writes": set(), "reads": set(), "flows": []}
    for t in m.tables:
        for x in t.writers:
            if norm(x) in facts:
                facts[norm(x)]["writes"].add(t.id)
        for x in t.readers:
            if norm(x) in facts:
                facts[norm(x)]["reads"].add(t.id)
    for name, ex in (extra or {}).items():
        facts[name]["writes"] |= set(ex.get("writes", []))
        facts[name]["reads"] |= set(ex.get("reads", []))
    for f in m.flows:
        for s in f["steps"]:
            if norm(s[2]) in facts:
                facts[norm(s[2])]["flows"].append({"flow": f["id"], "table": s[0], "op": s[1],
                                                   "gate": s[4] if len(s) > 4 and s[4] else None})
    out = {}
    for name, f in facts.items():
        scope = f["writes"] | f["reads"]
        flows = sorted({x["flow"] for x in f["flows"]}, key=lambda x: (WAVE_BY_FLOW[x], x))
        out[name] = {
            "writes": sorted(f["writes"]), "reads": sorted(f["reads"]),
            "domains_touched": sorted({m.table(t).domain for t in scope}),
            "restricted_tables": sorted(scope & restricted_tables),
            "gates_on_written_tables": sorted(set().union(*[table_gates[t] for t in f["writes"]])
                                              if f["writes"] else set()),
            "gates_in_flows": sorted({x["gate"] for x in f["flows"] if x["gate"]}),
            "guarded_tables_written": sorted(f["writes"] & guarded),
            "requests_approvals": "approval_request" in f["writes"],
            "flows": flows,
            "wave": min((WAVE_BY_FLOW[x] for x in flows), default=4),
        }
    return out


def build() -> list[dict]:
    facts = derived_facts({a["worker"]: a["extra_scope"] for a in authored() if "extra_scope" in a})
    recs = []
    for a in authored():
        recs.append({**a, **facts[a["worker"]]})
    return sorted(recs, key=lambda r: (r["wave"], r["home_domain"], r["worker"]))


def validate_extra_scope(auth: list[dict] | None = None, actors: list[dict] | None = None) -> list[str]:
    """Reviewed scope additions must name real tables, say why, and not repeat what the model already
    grants. Platform actors must not collide with worker names."""
    m = load_model()
    tables = {t.id for t in m.tables}
    auth = auth if auth is not None else authored()
    actors = actors if actors is not None else platform_actors()
    base = derived_facts()
    errs: list[str] = []
    for a in auth:
        ex = a.get("extra_scope")
        if ex is None:
            continue
        w = a["worker"]
        if not ex.get("why", "").strip():
            errs.append(f"{w}: extra_scope needs a why")
        if not ex.get("reads") and not ex.get("writes"):
            errs.append(f"{w}: extra_scope adds nothing")
        for kind in ("reads", "writes"):
            for t in ex.get(kind, []):
                if t not in tables:
                    errs.append(f"{w}: extra_scope {kind} names unknown table {t}")
                elif w in base and t in base[w][kind]:
                    errs.append(f"{w}: extra_scope {kind} repeats {t}, which the model already grants")
    names = {a["worker"] for a in auth}
    for x in actors:
        if x["actor"] in names:
            errs.append(f"platform actor {x['actor']} collides with a worker name")
        for kind in ("reads", "writes"):
            for t in x.get(kind, []):
                if t not in tables:
                    errs.append(f"platform actor {x['actor']}: unknown table {t} in {kind}")
    if len({x["actor"] for x in actors}) != len(actors):
        errs.append("duplicate platform actors")
    return errs


def validate(recs: list[dict] | None = None) -> list[str]:
    m = load_model()
    domains = set(m.domains)
    soft_ids = {s.gate_id for s in SOFT_GATES}
    recs = recs if recs is not None else build()
    errs: list[str] = []
    names = [r["worker"] for r in recs]
    if len(names) != len(set(names)):
        errs.append(f"duplicate workers: {[n for n, c in Counter(names).items() if c > 1]}")
    expected = model_workers()
    if set(names) != expected:
        errs.append(f"coverage: missing {sorted(expected - set(names))}, unknown {sorted(set(names) - expected)}")
    for r in recs:
        w, flags = r["worker"], set(r.get("flags", []))
        assists = [x["type"] for x in r.get("assist", [])]
        uses_model = r["kind"] in ("decider", "llm") or bool(assists)
        for field, vocab in (("kind", KINDS), ("effect", EFFECTS), ("autonomy", AUTONOMY), ("owner", OWNERS)):
            if r[field] not in vocab:
                errs.append(f"{w}: {field}={r[field]!r} not in {vocab}")
        if r["home_domain"] not in domains:
            errs.append(f"{w}: unknown domain {r['home_domain']}")
        elif r["domains_touched"] and r["home_domain"] not in r["domains_touched"]:
            errs.append(f"{w}: home domain {r['home_domain']} not among tables touched {r['domains_touched']}")
        if not set(r["triggers"]) <= set(TRIGGERS) or not r["triggers"]:
            errs.append(f"{w}: bad triggers {r['triggers']}")
        # Data-class rules: restricted data never reaches a model.
        if uses_model and r["restricted_tables"] and "needs-policy-decision" not in flags:
            errs.append(f"{w}: uses a model but scope has restricted tables {r['restricted_tables']}")
        if flags & {"C3-no-models", "C4-no-models"}:
            if uses_model:
                errs.append(f"{w}: flagged no-models but uses a model")
            if not r["restricted_tables"]:
                errs.append(f"{w}: flagged no-models but touches no restricted tables")
        # Autonomy ladder.
        if r["effect"] == "external_irreversible" and r["autonomy"] != "approve":
            errs.append(f"{w}: irreversible external effect needs autonomy=approve")
        if r["kind"] == "llm":
            if r["effect"] not in ("read_only", "internal_write", "external_notify"):
                errs.append(f"{w}: LLM workers cannot have effect {r['effect']}")
            if r["effect"] == "external_notify" and r["autonomy"] == "auto":
                errs.append(f"{w}: LLM external messages cannot be autonomy=auto")
            if r.get("llm_tier") not in ("small", "medium", "large"):
                errs.append(f"{w}: LLM worker needs llm_tier")
        if r["kind"] == "decider" and not r.get("decision"):
            errs.append(f"{w}: decider worker needs a typed decision")
        for q, opts in (r.get("decision") or {}).items():
            if not 2 <= len(opts) <= 255:
                errs.append(f"{w}: decision {q} needs 2..255 options")
        sg = r.get("soft_gate")
        if sg and "(proposed)" not in sg and sg not in soft_ids:
            errs.append(f"{w}: soft gate {sg} is not registered")
        # Every irreversible worker is covered by a hard gate, or says plainly that it is not.
        if r["effect"] == "external_irreversible":
            covered = bool(r["gates_on_written_tables"])
            if covered and "no-gate-on-irreversible" in flags:
                errs.append(f"{w}: flagged no-gate but tables are covered by {r['gates_on_written_tables']}")
            if not covered and "no-gate-on-irreversible" not in flags:
                errs.append(f"{w}: irreversible and no hard gate covers its tables; add a gate or flag it")
        if "guarded-write" in flags and not r["guarded_tables_written"]:
            errs.append(f"{w}: flagged guarded-write but writes no guarded table")
    return errs


# ---------------------------------------------------------------------------- outputs
def _row(r: dict) -> list[str]:
    assist = ",".join(x["type"] for x in r.get("assist", []))
    return [r["worker"], r["home_domain"], r["kind"], assist, r["effect"], r["autonomy"],
            str(r["wave"]), ",".join(r.get("flags", [])), ",".join(r["gates_on_written_tables"]),
            ",".join(r["restricted_tables"])]


COLS = ["worker", "domain", "kind", "model_assist", "effect", "autonomy", "wave", "flags",
        "hard_gates_on_tables", "restricted_tables_in_scope"]


def to_csv(recs: list[dict]) -> str:
    buf = io.StringIO()
    wr = csv.writer(buf, lineterminator="\n")
    wr.writerow(COLS)
    for r in recs:
        wr.writerow(_row(r))
    return buf.getvalue()


def to_markdown(recs: list[dict]) -> str:
    by_kind = Counter(r["kind"] for r in recs)
    by_auto = Counter(r["autonomy"] for r in recs)
    by_wave = Counter(r["wave"] for r in recs)
    flag_count = Counter(f for r in recs for f in r.get("flags", []))
    llm = [r for r in recs if r["kind"] == "llm"]
    decider = [r for r in recs if r["kind"] == "decider"]
    L = ["# Worker classification", "",
         "GENERATED by `python -m daydor.agents.registry` from `registry/worker_classification.json` "
         "and the model. Edit the JSON, not this file.", "",
         f"{len(recs)} workers. Five people-actors in the artifact (Employee, Founder, HR admin, "
         "HR admin or Daydor ops, Manager) are not workers and are excluded.", "",
         "## Summary", "",
         "| Kind | Count | Meaning |", "|---|---|---|",
         f"| rule | {by_kind['rule']} | Deterministic code. No model. |",
         f"| integration | {by_kind['integration']} | Calls an external system; retries and idempotency come from the queue. |",
         f"| monitor | {by_kind['monitor']} | Detects conditions on a schedule or event and raises tasks or gates. |",
         f"| decider | {by_kind['decider']} | A typed soft decision (Laya). Feeds a hard gate; never resolves one. |",
         f"| llm | {by_kind['llm']} | Generation or extraction from unstructured input, with typed output validation. |", "",
         f"Autonomy defaults: auto {by_auto['auto']}, review {by_auto['review']}, approve {by_auto['approve']}. "
         f"Build waves: 1 (hire) {by_wave[1]}, 2 (payroll, exit) {by_wave[2]}, "
         f"3 (merit, threshold, erasure) {by_wave[3]}, 4 (not in a modelled flow) {by_wave[4]}.", "",
         "## Rules enforced by tests", "",
         "1. **Restricted data never reaches a model.** A decider or LLM worker (or model assist) whose scope includes a table "
         "with C3, C4 or encrypted columns fails validation, unless it carries `needs-policy-decision`.",
         "2. **No-model flags are checked both ways.** `C3-no-models` / `C4-no-models` must be true: the worker really touches "
         "restricted tables and really uses no model.",
         "3. **Irreversible external effects need a human.** `external_irreversible` requires `autonomy=approve`, and a hard "
         "gate must cover a table the worker writes, otherwise it must carry `no-gate-on-irreversible`.",
         "4. **LLM workers are boxed in.** They may only read, write internally, or send messages that are never `auto`; "
         "they need a model tier.",
         "5. **decider workers declare a typed decision** (2 to 255 options per question) and name a registered soft gate.",
         "6. **Coverage is exact.** Every worker in the model is classified, and nothing else is.", "",
         "## Autonomy levels", "",
         "- `auto`: acts without a human step. Reversible or read-only.",
         "- `review`: acts, and the result lands in a human review queue where it can be reversed.",
         "- `approve`: a human approval comes first (a hard gate, or tenant policy).",
         "A tenant can lower a worker's autonomy (for example, force `approve`) but never raise it above this default.", "",
         "## Model-using workers", "",
         "| Worker | Kind | Detail |", "|---|---|---|"]
    for r in llm:
        L.append(f"| {r['worker']} | llm ({r['llm_tier']}) | {r['note']} |")
    for r in decider:
        q = "; ".join(f"{k}: {'/'.join(v)}" for k, v in r["decision"].items())
        L.append(f"| {r['worker']} | decider | {q}. Gate: {r.get('soft_gate', 'none yet')} |")
    L += ["", "Model assists on rule workers: " + "; ".join(
        f"{r['worker']} ({x['type']}: {x['use']})" for r in recs if r["kind"] not in ("decider", "llm")
        for x in r.get("assist", [])) + ".", "",
        "## Flag counts", "", "| Flag | Workers |", "|---|---|"]
    for f, n in sorted(flag_count.items(), key=lambda x: (-x[1], x[0])):
        L.append(f"| {f} | {n} |")
    L += ["", "## All workers", "", "Sorted by build wave, then domain. `hard_gates_on_tables` are the model's gates covering "
          "tables the worker writes.", "", "| " + " | ".join(COLS) + " |", "|" + "---|" * len(COLS)]
    for r in recs:
        L.append("| " + " | ".join(c if c else "-" for c in _row(r)) + " |")
    L.append("")
    return "\n".join(L)


def write_outputs() -> None:
    recs = build()
    errs = validate(recs) + validate_extra_scope()
    if errs:
        raise SystemExit("registry invalid:\n" + "\n".join(errs))
    GENERATED.write_text(json.dumps(recs, indent=1) + "\n")
    DOC_MD.write_text(to_markdown(recs))
    DOC_CSV.write_text(to_csv(recs))
    print(f"wrote {GENERATED.name}, {DOC_MD.name}, {DOC_CSV.name} ({len(recs)} workers)")


if __name__ == "__main__":  # pragma: no cover
    write_outputs()
