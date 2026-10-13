"""Worker roles: the database definition of what each worker may do, generated from the registry.

registry/workers.generated.json   one record per worker (already merged with the model and the
                                  reviewed extra_scope)
registry/platform_actors.json     roles for platform handlers that are not workers
model/daydor_model.json           column access for the agent role ("G"), classes, guards

Outputs (committed, drift-tested, applied by forward-only migrations):
    migrations/sql/0025_worker_definition.sql   app.worker_definition and its seed rows
    migrations/sql/0028_worker_roles.sql        one NOLOGIN role per worker and derived grants
Run: python -m daydor.agents.roles

Rules the generator enforces (it raises, it never silently skips):
  * a worker role gets SELECT on tables in its reads and writes, INSERT/UPDATE on tables in its
    writes, at column level, capped by the model's access for the agent role ("G")
  * never an encrypted column, never a derived column, never DELETE
  * a guarded column (GUARDS) goes only to its named owner
  * helper functions are granted per worker (FUNCTION_GRANTS), not to everyone
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from daydor.gates.registry import GUARDS, SOFT_GATES
from daydor.model import load_model
from daydor.model.ddl import SYSTEM_MANAGED, q
from daydor.model.loader import READ, WRITE

ROOT = Path(__file__).resolve().parents[3]
GENERATED = ROOT / "registry" / "workers.generated.json"
ACTORS = ROOT / "registry" / "platform_actors.json"
SQL_DIR = ROOT / "migrations" / "sql"
DEFINITION_SQL = SQL_DIR / "0025_worker_definition.sql"
ROLES_SQL = SQL_DIR / "0028_worker_roles.sql"
DEFAULTS_SQL = SQL_DIR / "0032_worker_defaults.sql"

PLATFORM_GROUP = "worker_platform"     # carries the grants every worker needs (queue, workflow, gates)
ROLE_PREFIX = "worker_"
AUTONOMY_RANK = {"auto": 0, "review": 1, "approve": 2}

# Who may set each guarded column (the database still requires an approved gate for the row).
# Reviewed defaults; change here, regenerate, and add a migration.
GUARD_OWNERS = {
    ("payroll_run", "disbursed_at"): ["direct-deposit-disburser"],
    ("final_settlement", "disbursed_at"): ["direct-deposit-disburser"],
    ("contractor_invoice", "paid_at"): ["multi-currency-payment-router"],
    ("gl_journal_entry", "posted_at"): ["gl-poster"],
    ("identity_account", "deprovisioned_at"): ["deprovisioning-agent"],
    ("cobra_event", "notice_sent_at"): ["cobra-notice-generator"],
    ("er_case", "outcome"): ["investigation-tracker"],
    # Nobody reimburses yet (no worker pays an expense), so no worker holds this until one is built and
    # added here, with review.
    ("expense", "reimbursed_at"): [],
    # The model gives agents no write on this column: HR decides, and a person sets it after g_fmla.
    ("leave_request", "fmla_designation"): [],
}

# Encrypted PII (ADR-002): who may collect a column and who may decrypt it for a purpose. These seed the
# worker roles into app.pii_column.collect_roles and app.pii_purpose.allowed_roles (0028). Deciders and
# LLM workers never appear here (validated).
PII_COLLECTORS = {
    ("employee", "aadhaar_ekyc_ref"): ["employee-record-writer", "new-hire-doc-collector"],
    ("employee", "pan_encrypted"): ["employee-record-writer", "new-hire-doc-collector"],
    ("employee", "ssn_encrypted"): ["employee-record-writer", "new-hire-doc-collector"],
    ("employee", "bank_account_encrypted"): ["employee-record-writer"],
}
PII_PURPOSES = {
    "identity_verification": ["employee-record-writer", "new-hire-doc-collector", "i9-e-verify-initiator"],
    "background_check": ["background-check-initiator"],
    "payroll_disbursal": ["direct-deposit-disburser"],
    "tax_filing": ["tax-filing-submitter"],
}

# Helper functions that only some workers need. Everything else is in the platform group (0027).
FUNCTION_GRANTS = {
    "app.encrypt_pii(text, text, uuid, text)": sorted({w for ws in PII_COLLECTORS.values() for w in ws}),
    "app.decrypt_pii(text, text, uuid, text)": sorted({w for ws in PII_PURPOSES.values() for w in ws}),
    "app.open_payroll_run(uuid, date, date, uuid)": ["payroll-run-builder"],
    "app.record_payslip(uuid, uuid, uuid, numeric, numeric, numeric, uuid)": ["payroll-run-builder"],
    "app.finalize_payroll_run(uuid)": ["payroll-run-builder"],
    "app.open_final_settlement(uuid, uuid, numeric, numeric, numeric, numeric)": ["final-pay-calculator"],
}

# Tables a worker lists as read but only through an aggregate view (k >= 5, finding 7), so no column
# grant exists or should. The role gets nothing on them until that view is built.
AGGREGATE_ONLY = frozenset({"self_identification"})

# Model tables every worker needs through the platform group: the engine opens approvals when a
# gated transition fires, inside whichever worker's job is running. Insert and read, never update.
PLATFORM_TABLES = ("approval_request",)
# The model names "every worker (insert only)" as the writer of these, so every worker may insert and none may
# read or change them (the table is append-only).
PLATFORM_INSERT_ONLY = ("audit_log",)


def role_name(worker: str) -> str:
    return ROLE_PREFIX + worker.replace("-", "_")


@lru_cache(maxsize=1)
def worker_records() -> tuple[dict, ...]:
    """Workers and platform actors in one shape. Platform actors have kind 'platform'."""
    recs = [dict(r, platform_actor=False) for r in json.loads(GENERATED.read_text())]
    for a in json.loads(ACTORS.read_text()):
        recs.append({
            "worker": a["actor"], "home_domain": "ro", "kind": "platform", "effect": "internal_write",
            "autonomy": "auto", "triggers": ["event"], "owner": a["owner"], "note": a["description"],
            "flags": [], "reads": sorted(a.get("reads", [])), "writes": sorted(a.get("writes", [])),
            "wave": 1, "platform_actor": True})
    return tuple(sorted(recs, key=lambda r: r["worker"]))


def worker_role_names() -> frozenset[str]:
    """Role names a session may switch to for a worker (cheap: reads the generated JSON only)."""
    return frozenset(role_name(r["worker"]) for r in worker_records())


def role_for(worker: str) -> str:
    for r in worker_records():
        if r["worker"] == worker:
            return role_name(worker)
    raise KeyError(f"unknown worker {worker!r}")


# ---------------------------------------------------------------------------- sql helpers
def _lit(s: str | None) -> str:
    return "NULL" if s is None else "'" + s.replace("'", "''") + "'"


def _arr(items) -> str:
    items = sorted(items)
    return "ARRAY[" + ", ".join(_lit(i) for i in items) + "]::text[]" if items else "'{}'::text[]"


def _json(v) -> str:
    return "NULL" if v is None else "CAST(" + _lit(json.dumps(v, sort_keys=True)) + " AS jsonb)"


# ---------------------------------------------------------------------------- 0025
def generate_definition_sql() -> str:
    recs = worker_records()
    gate_ids = {g.gate_id for g in SOFT_GATES}
    L = ["-- GENERATED by daydor.agents.roles from registry/ (python -m daydor.agents.roles). Do not edit by hand.",
         "-- One row per worker: what it is, what it may do by default, and what it may touch.",
         "-- Changes go through registry/worker_classification.json, then a forward-only migration.",
         "",
         "DO $$ BEGIN",
         f"    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{PLATFORM_GROUP}') THEN",
         f"        CREATE ROLE {PLATFORM_GROUP} NOLOGIN;",
         "    END IF;",
         "END $$;",
         "",
         "SET ROLE daydor_schema_owner;",
         "",
         "CREATE TABLE app.worker_definition (",
         "    worker              text PRIMARY KEY,",
         "    role_name           text NOT NULL UNIQUE,",
         "    home_domain         text NOT NULL,",
         "    kind                text NOT NULL CHECK (kind IN ('rule', 'integration', 'monitor', 'decider', 'llm', 'platform')),",
         "    effect              text NOT NULL CHECK (effect IN ('read_only', 'internal_write', 'external_notify',",
         "                                                       'external_reversible', 'external_irreversible')),",
         "    autonomy            text NOT NULL CHECK (autonomy IN ('auto', 'review', 'approve')),",
         "    owner               text NOT NULL,",
         "    triggers            text[] NOT NULL,",
         "    llm_tier            text CHECK (llm_tier IN ('small', 'medium', 'large')),",
         "    assist              jsonb NOT NULL DEFAULT '[]',",
         "    flags               text[] NOT NULL DEFAULT '{}',",
         "    decision            jsonb,",
         "    soft_gate           text REFERENCES app.gate_definition (gate_id),",
         "    soft_gate_proposed  text,",
         "    wave                integer NOT NULL,",
         "    writes              text[] NOT NULL DEFAULT '{}',",
         "    reads               text[] NOT NULL DEFAULT '{}',",
         "    extra_scope         jsonb,",
         "    platform_actor      boolean NOT NULL DEFAULT false,",
         "    note                text,",
         "    enabled             boolean NOT NULL DEFAULT true",
         ");",
         "COMMENT ON TABLE app.worker_definition IS 'Worker registry. Only enabled can change at runtime (daydor_ops).';",
         "",
         "-- Everything except `enabled` is fixed by the registry and changes only through a migration.",
         "CREATE FUNCTION app.worker_definition_guard() RETURNS trigger",
         "LANGUAGE plpgsql AS $$",
         "BEGIN",
         "    IF TG_OP = 'DELETE' THEN",
         "        RAISE EXCEPTION 'worker_definition rows are never deleted' USING ERRCODE = 'check_violation';",
         "    END IF;",
         "    IF (to_jsonb(NEW) - 'enabled') IS DISTINCT FROM (to_jsonb(OLD) - 'enabled') THEN",
         "        RAISE EXCEPTION 'only worker_definition.enabled may change at runtime; change the registry and add a migration'",
         "            USING ERRCODE = 'check_violation';",
         "    END IF;",
         "    RETURN NEW;",
         "END $$;",
         "CREATE TRIGGER worker_definition_guard BEFORE UPDATE OR DELETE ON app.worker_definition",
         "    FOR EACH ROW EXECUTE FUNCTION app.worker_definition_guard();",
         "",
         "GRANT USAGE ON SCHEMA app TO " + PLATFORM_GROUP + ";",
         f"GRANT SELECT ON app.worker_definition TO {PLATFORM_GROUP}, daydor_worker, daydor_ops, daydor_admin;",
         "GRANT UPDATE (enabled) ON app.worker_definition TO daydor_ops, daydor_admin;",
         ""]
    cols = ("worker, role_name, home_domain, kind, effect, autonomy, owner, triggers, llm_tier, assist, flags, "
            "decision, soft_gate, soft_gate_proposed, wave, writes, reads, extra_scope, platform_actor, note")
    for r in recs:
        sg = r.get("soft_gate")
        registered = sg if sg in gate_ids else None
        proposed = sg if sg and registered is None else None
        L.append(
            f"INSERT INTO app.worker_definition ({cols}) VALUES ({_lit(r['worker'])}, {_lit(role_name(r['worker']))}, "
            f"{_lit(r['home_domain'])}, {_lit(r['kind'])}, {_lit(r['effect'])}, {_lit(r['autonomy'])}, "
            f"{_lit(r['owner'])}, {_arr(r['triggers'])}, {_lit(r.get('llm_tier'))}, {_json(r.get('assist', []))}, "
            f"{_arr(r.get('flags', []))}, {_json(r.get('decision'))}, {_lit(registered)}, {_lit(proposed)}, "
            f"{r['wave']}, {_arr(r['writes'])}, {_arr(r['reads'])}, {_json(r.get('extra_scope'))}, "
            f"{'true' if r['platform_actor'] else 'false'}, {_lit(r.get('note'))});")
    L += ["", "RESET ROLE;", ""]
    return "\n".join(L)


# ---------------------------------------------------------------------------- 0028
def _columns(table, level: int, *, guarded_ok: set[str] | None = None, write: bool = False) -> list[str]:
    """Columns of `table` the agent role ("G") has at least `level` on, as grants would list them."""
    guarded = {c for t, c, _ in GUARDS if t == table.id}
    out = []
    for c in table.columns:
        if c.encrypted or c.level("G") < level:
            continue
        if write and (c.name in SYSTEM_MANAGED or c.derived):
            continue
        if write and c.name in guarded and c.name not in (guarded_ok or set()):
            continue
        out.append(c.name)
    return out


def table_grants(rec: dict, model=None) -> dict[str, dict[str, list[str]]]:
    """{table: {"select": [cols], "insert": [cols], "update": [cols]}} for one worker record."""
    model = model or load_model()
    out: dict[str, dict[str, list[str]]] = {}
    for tid in sorted(set(rec["reads"]) | set(rec["writes"])):
        t = model.table(tid)
        g = {"select": _columns(t, READ)}
        if tid in rec["writes"]:
            ok = {c for (tt, c), ws in GUARD_OWNERS.items() if tt == tid and rec["worker"] in ws}
            cols = _columns(t, WRITE, guarded_ok=ok, write=True)
            g["insert"] = cols
            if not t.append_only:
                g["update"] = cols
        out[tid] = {k: v for k, v in g.items() if v}
    return {k: v for k, v in out.items() if v}


def validate_roles(recs=None, model=None) -> list[str]:
    """Problems that would silently shrink or widen a role. Empty means the generator's inputs are sound."""
    recs = list(recs if recs is not None else worker_records())
    model = model or load_model()
    by = {r["worker"]: r for r in recs}
    errs: list[str] = []
    names = [role_name(r["worker"]) for r in recs]
    if len(set(names)) != len(names):
        errs.append("role name collision")
    for n in names:
        if len(n) > 63:
            errs.append(f"role name {n} longer than 63 bytes")
    guards = {(t, c) for t, c, _ in GUARDS}
    if set(GUARD_OWNERS) != guards:
        errs.append(f"GUARD_OWNERS {sorted(set(GUARD_OWNERS) ^ guards)} do not match gates.registry.GUARDS")
    for (t, c), owners in GUARD_OWNERS.items():
        for w in owners:
            if w not in by:
                errs.append(f"guard owner {w} of {t}.{c} is not a worker")
            elif t not in by[w]["writes"]:
                errs.append(f"guard owner {w} of {t}.{c} does not write {t}")
    for r in recs:
        if r["worker"] not in by:
            continue
        for tid in set(r["reads"]) | set(r["writes"]):
            t = model.table(tid)
            if not _columns(t, READ) and tid not in AGGREGATE_ONLY:
                errs.append(f"{r['worker']}: scope has {tid} but the agent role cannot read any column of it")
        for tid in r["writes"]:
            t = model.table(tid)
            ok = {c for (tt, c), ws in GUARD_OWNERS.items() if tt == tid and r["worker"] in ws}
            if not _columns(t, WRITE, guarded_ok=ok, write=True) and not t.append_only:
                errs.append(f"{r['worker']}: writes {tid} but the agent role has no writable column on it")
    pii = {w for ws in PII_COLLECTORS.values() for w in ws} | {w for ws in PII_PURPOSES.values() for w in ws}
    for w in pii | {w for ws in FUNCTION_GRANTS.values() for w in ws}:
        if w not in by:
            errs.append(f"{w} is granted a function or PII role but is not a worker")
    for w in pii:
        r = by.get(w)
        if r and (r["kind"] in ("decider", "llm") or r.get("assist")):
            errs.append(f"{w}: a model-using worker may never be a PII collector or reader")
    return errs


def generate_roles_sql() -> str:
    model = load_model()
    errs = validate_roles(model=model)
    if errs:
        raise ValueError("worker roles invalid:\n" + "\n".join(errs))
    recs = worker_records()
    L = ["-- GENERATED by daydor.agents.roles from registry/ and the model (python -m daydor.agents.roles).",
         "-- Do not edit by hand. One NOLOGIN role per worker, each a member of worker_platform (0027).",
         "-- Grants are column-level, derived from the worker's scope and the model's agent access (G):",
         "-- never encrypted or derived columns, never DELETE, guarded columns only to their named owner.",
         "",
         "DO $$",
         "DECLARE r text;",
         "BEGIN",
         "    FOREACH r IN ARRAY ARRAY[" + ", ".join(_lit(role_name(x["worker"])) for x in recs) + "] LOOP",
         "        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN",
         f"            EXECUTE format('CREATE ROLE %I NOLOGIN IN ROLE {PLATFORM_GROUP}', r);",
         "        END IF;",
         "    END LOOP;",
         "END $$;",
         ""]
    L += [f"GRANT {role_name(x['worker'])} TO daydor_app WITH INHERIT FALSE, SET TRUE;" for x in recs]
    L += ["", "SET ROLE daydor_schema_owner;", ""]

    pm = {t: model.table(t) for t in PLATFORM_TABLES}
    L.append(f"-- {PLATFORM_GROUP}: approvals can be opened by the engine inside any worker's job")
    for tid, t in pm.items():
        sel, ins = _columns(t, READ), _columns(t, WRITE, write=True)
        L.append(f"GRANT SELECT ({', '.join(sel)}) ON public.{q(tid)} TO {PLATFORM_GROUP};")
        L.append(f"GRANT INSERT ({', '.join(ins)}) ON public.{q(tid)} TO {PLATFORM_GROUP};")
    for tid in PLATFORM_INSERT_ONLY:
        ins = _columns(model.table(tid), WRITE, write=True)
        L.append(f"GRANT INSERT ({', '.join(ins)}) ON public.{q(tid)} TO {PLATFORM_GROUP};")
    L.append("")
    for x in recs:
        role = role_name(x["worker"])
        L.append(f"-- {x['worker']} ({x['kind']}, default autonomy {x['autonomy']})")
        for tid, g in table_grants(x, model).items():
            for verb in ("select", "insert", "update"):
                if verb in g:
                    L.append(f"GRANT {verb.upper()} ({', '.join(g[verb])}) ON public.{q(tid)} TO {role};")
        for fn, ws in sorted(FUNCTION_GRANTS.items()):
            if x["worker"] in ws:
                L.append(f"GRANT EXECUTE ON FUNCTION {fn} TO {role};")
        L.append("")
    L += ["-- PII registries: worker roles, matched by app.current_actor_role() (0027)."]
    for (tbl, col), ws in sorted(PII_COLLECTORS.items()):
        L.append(f"UPDATE app.pii_column SET collect_roles = collect_roles || {_arr(role_name(w) for w in ws)} "
                 f"WHERE table_name = {_lit(tbl)} AND column_name = {_lit(col)};")
    for purpose, ws in sorted(PII_PURPOSES.items()):
        L.append(f"UPDATE app.pii_purpose SET allowed_roles = allowed_roles || {_arr(role_name(w) for w in ws)} "
                 f"WHERE purpose = {_lit(purpose)};")
    L += ["", "RESET ROLE;", ""]
    return "\n".join(L)


# ---------------------------------------------------------------------------- 0032
def generate_defaults_sql() -> str:
    """Incremental, for databases that already ran 0025 and 0028: workers that start disabled
    (`enabled_by_default: false` in the registry, ADR-006), and the guarded columns reconciled against
    GUARD_OWNERS (a REVOKE of a privilege a role never held is a no-op, so a fresh install is unaffected)."""
    model = load_model()
    recs = worker_records()
    off = sorted(r["worker"] for r in recs if r.get("enabled_by_default") is False)
    L = ["-- GENERATED by daydor.agents.roles (python -m daydor.agents.roles). Do not edit by hand.",
         "-- Incremental on 0025 and 0028; safe to replay on a fresh install, where both already say this.",
         "",
         "SET ROLE daydor_schema_owner;",
         ""]
    if off:
        L.append("-- Irreversible external effect, no hard gate, no flow yet: disabled until reviewed (ADR-006).")
        L.append("UPDATE app.worker_definition SET enabled = false WHERE worker IN ("
                 + ", ".join(_lit(w) for w in off) + ");")
        L.append("")
    L.append("-- Insert-only platform tables (the model's \"every worker (insert only)\"): safe to replay.")
    for tid in PLATFORM_INSERT_ONLY:
        ins = _columns(model.table(tid), WRITE, write=True)
        L.append(f"GRANT INSERT ({', '.join(ins)}) ON public.{q(tid)} TO {PLATFORM_GROUP};")
    L.append("")
    L.append("-- Guarded columns: only the named owners hold them.")
    for (tid, col), owners in sorted(GUARD_OWNERS.items()):
        t = model.table(tid)
        c = t.column(col)
        for r in recs:
            if tid not in r["writes"]:
                continue                  # never held a privilege on this table's columns
            role = role_name(r["worker"])
            if r["worker"] in owners and tid in r["writes"] and c.level("G") >= WRITE and not c.encrypted:
                L.append(f"GRANT INSERT ({col}) ON public.{q(tid)} TO {role};")
                if not t.append_only:
                    L.append(f"GRANT UPDATE ({col}) ON public.{q(tid)} TO {role};")
            else:
                L.append(f"REVOKE INSERT ({col}) ON public.{q(tid)} FROM {role};")
                if not t.append_only:
                    L.append(f"REVOKE UPDATE ({col}) ON public.{q(tid)} FROM {role};")
    L += ["", "RESET ROLE;", ""]
    return "\n".join(L)


def write_outputs() -> None:  # pragma: no cover
    DEFINITION_SQL.write_text(generate_definition_sql())
    ROLES_SQL.write_text(generate_roles_sql())
    DEFAULTS_SQL.write_text(generate_defaults_sql())
    print(f"wrote {DEFINITION_SQL.name}, {ROLES_SQL.name} and {DEFAULTS_SQL.name}")


if __name__ == "__main__":  # pragma: no cover
    write_outputs()
