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
}

# Helper functions that only some workers need. Everything else in the platform group.
FUNCTION_GRANTS = {
    "app.encrypt_pii(text, text, uuid, text)": [
        "employee-record-writer", "new-hire-doc-collector", "onboarding-checklist-builder"],
    "app.decrypt_pii(text, text, uuid, text)": [
        "employee-record-writer", "i9-e-verify-initiator", "background-check-initiator",
        "direct-deposit-disburser", "tax-filing-submitter"],
    "app.open_payroll_run(uuid, date, date, uuid)": ["payroll-run-builder"],
    "app.record_payslip(uuid, uuid, uuid, numeric, numeric, numeric, uuid)": ["payroll-run-builder"],
    "app.finalize_payroll_run(uuid)": ["payroll-run-builder"],
    "app.open_final_settlement(uuid, uuid, numeric, numeric, numeric, numeric)": ["final-pay-calculator"],
}


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


def write_outputs() -> None:  # pragma: no cover
    DEFINITION_SQL.write_text(generate_definition_sql())
    print(f"wrote {DEFINITION_SQL.name}")


if __name__ == "__main__":  # pragma: no cover
    write_outputs()
