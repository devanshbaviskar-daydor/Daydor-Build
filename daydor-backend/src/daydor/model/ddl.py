"""Generates Postgres DDL for the business schema from the model.

Output is deterministic so it can be committed (migrations/sql/) and checked for drift.

What it generates, per table:
  * CREATE TABLE with defaults (id, tenant_id from session, timestamps)
  * foreign keys (as a second pass, because the model has cycles such as employee <-> department)
  * per-tenant unique constraints
  * column comments carrying class / encryption / jurisdiction metadata
  * row-level security: tenant isolation, plus person scope (self / reporting subtree)
  * column-level grants for every role, derived from the artifact's access engine
  * a <table>_masked view for roles whose access to some column is "masked"
  * updated_at and append-only triggers

Encrypted columns are stored as bytea and never granted (ADR-002).
DELETE is never granted to any role: removal goes through retention / erasure functions.
"""
from __future__ import annotations

from .loader import (MASKED, READ, ROLE_DB, WRITE, Model, Table, Column, load_model)

SQL_TYPE = {
    "uuid": "uuid", "text": "text", "enum": "text", "jsonb": "jsonb", "numeric": "numeric(14,2)",
    "date": "date", "ts": "timestamptz", "bool": "boolean", "int": "integer", "bytea": "bytea",
    "citext": "citext",
}
SYSTEM_MANAGED = {"id", "tenant_id", "created_at", "updated_at"}
# Order matters for deterministic output.
GRANT_ROLES = ["A", "O", "F", "H", "P", "I", "M", "E", "U", "G"]


def q(name: str) -> str:
    """Quote identifiers that need it (e.g. valuation_409a is fine, but keep it safe)."""
    return f'"{name}"' if not name.replace("_", "").isalnum() or name[0].isdigit() else name


def physical_type(c: Column) -> str:
    return "bytea" if c.encrypted else SQL_TYPE[c.type]


def column_def(t: Table, c: Column) -> str:
    s = f"    {c.name:<32}{physical_type(c)}"
    if c.pk:
        return s + " PRIMARY KEY DEFAULT gen_random_uuid()"
    if c.name == "tenant_id":
        s += " DEFAULT app.tenant_id()"
        return s if t.null_tenant else s + " NOT NULL"
    if c.name in ("created_at", "updated_at"):
        return s + " NOT NULL DEFAULT now()"
    if not c.nullable:
        s += " NOT NULL"
    return s


def create_table(t: Table) -> str:
    cols = ",\n".join(column_def(t, c) for c in t.columns)
    lines = [f"-- {t.id}: {t.description}", f"CREATE TABLE public.{q(t.id)} (\n{cols}\n);"]
    for c in t.columns:
        if not c.unique:
            continue
        if t.global_ or (t.null_tenant and c.name == "email"):
            lines.append(f"ALTER TABLE public.{q(t.id)} ADD CONSTRAINT {t.id}_{c.name}_key UNIQUE ({c.name});")
        else:
            lines.append(f"ALTER TABLE public.{q(t.id)} ADD CONSTRAINT {t.id}_{c.name}_key "
                         f"UNIQUE (tenant_id, {c.name});")
    for c in t.columns:
        meta = [f"class={c.cls}"]
        if c.encrypted:
            meta.append("enc=pgcrypto")
        if c.masked:
            meta.append("masked")
        if c.jurisdiction:
            meta.append(f"pack={c.jurisdiction}")
        if c.derived:
            meta.append("derived")
        if c.extension:
            meta.append("extension")
        lines.append(f"COMMENT ON COLUMN public.{q(t.id)}.{c.name} IS '{';'.join(meta)}';")
    lines.append(f"COMMENT ON TABLE public.{q(t.id)} IS 'domain={t.domain};source={t.source}"
                 f"{';pack=' + t.jurisdiction if t.jurisdiction else ''}';")
    return "\n".join(lines)


def foreign_keys(t: Table) -> list[str]:
    out = []
    for c in t.columns:
        if c.fk:
            out.append(f"ALTER TABLE public.{q(t.id)} ADD CONSTRAINT {t.id}_{c.name}_fkey "
                       f"FOREIGN KEY ({c.name}) REFERENCES public.{q(c.fk)}(id);")
    return out


def indexes(t: Table) -> list[str]:
    out = []
    if not t.global_:
        scope = t.employee_scope_column
        if scope and scope != "id":
            out.append(f"CREATE INDEX {t.id}_tenant_{scope}_idx ON public.{q(t.id)} (tenant_id, {scope});")
        else:
            out.append(f"CREATE INDEX {t.id}_tenant_idx ON public.{q(t.id)} (tenant_id);")
    for c in t.columns:
        if c.fk and c.name not in ("tenant_id", t.employee_scope_column):
            out.append(f"CREATE INDEX {t.id}_{c.name}_idx ON public.{q(t.id)} ({c.name});")
    return out


def row_security(t: Table) -> list[str]:
    name = f"public.{q(t.id)}"
    if t.id == "tenant":
        return [f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY;", f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY;",
                f"CREATE POLICY tenant_self ON {name} USING (id = app.tenant_id() OR app.is_daydor_staff());"]
    if t.global_:
        return []  # statutory reference data and retention rules are shared across tenants
    staff = " OR (tenant_id IS NULL AND app.is_daydor_staff())" if t.null_tenant else ""
    out = [
        f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY;",
        f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY;",
        f"CREATE POLICY tenant_isolation ON {name}\n"
        f"    USING (tenant_id = app.tenant_id(){staff})\n"
        f"    WITH CHECK (tenant_id = app.tenant_id(){staff});",
    ]
    scope = t.employee_scope_column
    if scope:
        out.append(
            f"CREATE POLICY person_scope ON {name} AS RESTRICTIVE\n"
            f"    USING (app.can_see_employee({scope}))\n"
            f"    WITH CHECK (app.can_see_employee({scope}));"
        )
    return out


def grants(t: Table) -> list[str]:
    name = f"public.{q(t.id)}"
    out = []
    for r in GRANT_ROLES:
        db = ROLE_DB[r]
        readable = [c.name for c in t.columns if c.level(r) >= READ and not c.encrypted]
        writable = [c.name for c in t.columns if c.level(r) >= WRITE and not c.encrypted
                    and c.name not in SYSTEM_MANAGED and not c.derived]
        if readable:
            out.append(f"GRANT SELECT ({', '.join(readable)}) ON {name} TO {db};")
        if writable:
            out.append(f"GRANT INSERT ({', '.join(writable)}) ON {name} TO {db};")
            if not t.append_only:
                out.append(f"GRANT UPDATE ({', '.join(writable)}) ON {name} TO {db};")
    return out


def mask_expr(c: Column) -> str:
    if c.type in ("text", "citext"):
        return f"CASE WHEN {c.name} IS NULL THEN NULL ELSE '****' || right({c.name}::text, 4) END"
    return "NULL"


def masked_view(t: Table) -> list[str]:
    """One view per table that has any masked column for any role.

    Each column is shown in full to roles with READ or better, masked to roles with MASKED,
    and NULL otherwise. Row security on the base table still applies (the view does not change
    current_user). security_barrier stops predicate push-down from leaking masked values.
    """
    masked_roles = [r for r in GRANT_ROLES if any(c.level(r) == MASKED and not c.encrypted for c in t.columns)]
    if not masked_roles:
        return []
    exprs = []
    for c in t.columns:
        if c.encrypted:
            exprs.append(f"    ({c.name} IS NOT NULL) AS {c.name}_on_file")
            continue
        full = [ROLE_DB[r] for r in GRANT_ROLES if c.level(r) >= READ]
        masked = [ROLE_DB[r] for r in GRANT_ROLES if c.level(r) == MASKED]
        view_roles = {ROLE_DB[r] for r in masked_roles}
        if c.cls == "S" or view_roles <= set(full):
            exprs.append(f"    {c.name}")
            continue
        parts = []
        if full:
            parts.append(f"WHEN app.current_app_role() IN ({', '.join(repr(x) for x in full)}) THEN {c.name}")
        if masked:
            parts.append(f"WHEN app.current_app_role() IN ({', '.join(repr(x) for x in masked)}) "
                         f"THEN {mask_expr(c) if c.type in ('text', 'citext') else 'NULL'}")
        cast = physical_type(c)
        exprs.append(f"    (CASE {' '.join(parts)} ELSE NULL END)::{cast} AS {c.name}")
    view = f"public.{t.id}_masked"
    return [
        f"CREATE VIEW {view} WITH (security_barrier) AS SELECT\n" + ",\n".join(exprs) + f"\nFROM public.{q(t.id)};",
        f"GRANT SELECT ON {view} TO {', '.join(ROLE_DB[r] for r in masked_roles)};",
    ]


def triggers(t: Table) -> list[str]:
    name = f"public.{q(t.id)}"
    if t.append_only:
        return [f"CREATE TRIGGER {t.id}_append_only BEFORE UPDATE OR DELETE ON {name} "
                f"FOR EACH ROW EXECUTE FUNCTION app.reject_mutation();"]
    return [f"CREATE TRIGGER {t.id}_touch BEFORE UPDATE ON {name} "
            f"FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();"]


def generate_tables_sql(model: Model | None = None) -> str:
    model = model or load_model()
    parts = ["-- GENERATED from model/daydor_model.json + model/extensions.json. Do not edit by hand.",
             f"-- tables: {len(model.tables)}", ""]
    parts += [create_table(t) + "\n" for t in model.tables]
    parts.append("-- Foreign keys (second pass; the model has cycles)")
    for t in model.tables:
        parts += foreign_keys(t)
    parts.append("\n-- Indexes")
    for t in model.tables:
        parts += indexes(t)
    parts.append("\n-- Triggers")
    for t in model.tables:
        parts += triggers(t)
    return "\n".join(parts) + "\n"


def generate_security_sql(model: Model | None = None) -> str:
    model = model or load_model()
    parts = ["-- GENERATED from model/daydor_model.json + model/extensions.json. Do not edit by hand.",
             "-- Row-level security, column grants and masked views.", ""]
    for t in model.tables:
        block = [f"-- {t.id}"] + row_security(t) + grants(t) + masked_view(t)
        parts.append("\n".join(block) + "\n")
    return "\n".join(parts)


if __name__ == "__main__":  # pragma: no cover
    import sys
    from pathlib import Path
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "migrations/sql")
    out.mkdir(parents=True, exist_ok=True)
    (out / "0002_model_tables.sql").write_text(generate_tables_sql())
    (out / "0003_model_security.sql").write_text(generate_security_sql())
    print(f"wrote {out}/0002_model_tables.sql and {out}/0003_model_security.sql")
