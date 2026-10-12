"""Loads model/daydor_model.json (exported from the artifact) plus model/extensions.json."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
MODEL_PATH = REPO_ROOT / "model" / "daydor_model.json"
EXTENSIONS_PATH = REPO_ROOT / "model" / "extensions.json"

# Access levels used by the artifact.
NO_ACCESS, AGGREGATE, MASKED, READ, WRITE = 0, 1, 2, 3, 4

# Model role letter -> database role. "G" (domain agents) is a group role; one login-less
# role per domain inherits it (see ddl.agent_domain_roles).
ROLE_DB = {
    "A": "daydor_admin",
    "O": "daydor_ops",
    "F": "tenant_founder",
    "H": "tenant_hr",
    "P": "tenant_payroll",
    "I": "tenant_it",
    "M": "tenant_manager",
    "E": "tenant_employee",
    "U": "external_auditor",
    "G": "agent_runtime",
}
TENANT_WIDE_ROLES = {"daydor_admin", "daydor_ops", "tenant_founder", "tenant_hr", "tenant_payroll",
                     "tenant_it", "external_auditor", "agent_runtime"}


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    cls: str
    fk: str | None
    nullable: bool
    pk: bool
    unique: bool
    encrypted: bool
    masked: bool
    derived: bool
    jurisdiction: str | None
    access: dict[str, int]
    extension: bool = False

    def level(self, role_letter: str) -> int:
        return self.access.get(role_letter, NO_ACCESS)


@dataclass
class Table:
    id: str
    domain: str
    source: str
    jurisdiction: str | None
    description: str
    global_: bool
    null_tenant: bool
    append_only: bool
    table_acl: dict[str, int]
    columns: list[Column]
    writers: list[str] = field(default_factory=list)
    readers: list[str] = field(default_factory=list)

    def column(self, name: str) -> Column:
        for c in self.columns:
            if c.name == name:
                return c
        raise KeyError(f"{self.id}.{name}")

    @property
    def employee_scope_column(self) -> str | None:
        """Column used for person-level scoping (self / reporting subtree), as in the artifact."""
        if self.id == "employee":
            return "id"
        for c in self.columns:
            if c.fk == "employee" and c.name not in ("current_employee_id", "head_employee_id"):
                return c.name
        return None


@dataclass
class Model:
    tables: list[Table]
    roles: list[dict]
    gates: list[dict]
    flows: list[dict]
    classes: dict
    domains: dict
    meta: dict

    def table(self, tid: str) -> Table:
        for t in self.tables:
            if t.id == tid:
                return t
        raise KeyError(tid)

    @property
    def by_id(self) -> dict[str, Table]:
        return {t.id: t for t in self.tables}


def _column(d: dict, extension: bool = False) -> Column:
    return Column(
        name=d["name"], type=d["type"], cls=d["cls"], fk=d.get("fk"), nullable=d.get("nullable", False),
        pk=d.get("pk", False), unique=d.get("unique", False), encrypted=d.get("encrypted", False),
        masked=d.get("masked", False), derived=d.get("derived", False), jurisdiction=d.get("jurisdiction"),
        access=d["access"], extension=extension,
    )


def _apply_extensions(tables: dict[str, Table], ext: dict) -> None:
    for e in ext.get("columns", []):
        t = tables[e["table"]]
        # Extension columns inherit the table-level grant, capped like any other column of
        # their class: take the access of an existing column of the same class if present.
        same_cls = next((c for c in t.columns if c.cls == e["cls"]), None)
        access = dict(same_cls.access) if same_cls else dict(t.table_acl)
        col = _column({**e, "access": access}, extension=True)
        # keep created_at / updated_at last
        idx = next((i for i, c in enumerate(t.columns) if c.name == "created_at"), len(t.columns))
        t.columns.insert(idx, col)


@lru_cache(maxsize=1)
def load_model(path: str | None = None, extensions_path: str | None = None) -> Model:
    raw = json.loads(Path(path or MODEL_PATH).read_text())
    tables = {}
    for t in raw["tables"]:
        tables[t["id"]] = Table(
            id=t["id"], domain=t["domain"], source=t["source"], jurisdiction=t["jurisdiction"],
            description=t["description"], global_=t["global"], null_tenant=t["null_tenant"],
            append_only=t["append_only"], table_acl=t["table_acl"],
            columns=[_column(c) for c in t["columns"]], writers=t["writers"], readers=t["readers"],
        )
    ext_file = Path(extensions_path or EXTENSIONS_PATH)
    if ext_file.exists():
        _apply_extensions(tables, json.loads(ext_file.read_text()))
    return Model(tables=list(tables.values()), roles=raw["roles"], gates=raw["gates"], flows=raw["flows"],
                 classes=raw["classes"], domains=raw["domains"], meta=raw["meta"])
