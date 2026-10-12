"""Model-driven access rules. The database enforces them; these helpers only decide which columns
to ask for and which actions to offer, so the API never builds a query the role cannot run."""
from __future__ import annotations

from functools import lru_cache

from daydor.model import load_model
from daydor.model.loader import AGGREGATE, MASKED, READ, WRITE, Table

from .errors import ApiError
from .identity import Identity

NEVER_WRITE = {"id", "tenant_id", "created_at", "updated_at"}
# Tables people may create and edit directly through grants that already exist (reference data,
# employee-owned records). Flow tables are never in this list: they change through flow actions.
DIRECT_WRITE_TABLES = frozenset({
    "position", "job_profile", "comp_band", "access_role_template", "skill", "employee_skill",
    "emergency_contact",
    # Employee self-service and task ticking: the model gives people write access and lists no worker.
    "consent_record", "checklist_task",
    # Employee self-service by design, same shape as consent_record (table grant E: WRITE, no
    # agent writer -- daydor.timekeeping.punch's module docstring).
    "time_punch",
    # Global, admin-entered reference data (daydor_ops writes them; the tenant doesn't maintain
    # its own jurisdiction packs). Payroll's gross-to-net computation reads these, not hardcoded
    # numbers (docs/sprint-plan.md Sprint 7).
    "statutory_rate_rule", "pt_slab_rule",
    # Admin-entered reference data, same pattern as job_profile/comp_band (docs/sprint-plan.md's
    # "Reference & admin-owned data" note) -- tenant_hr writes these directly.
    "leave_policy", "benefit_plan",
    # Direct tenant_hr/tenant_founder write, like job_profile/comp_band -- daydor.exit.legal_hold's
    # module docstring: "no service needed, just a real row to check against."
    "legal_hold",
})
# Workflow context keys that are safe to return. Everything else (candidate name, email, phone,
# resume reference, compensation) stays in the database.
SAFE_CONTEXT_EXACT = {"channel", "pay_range_min", "pay_range_max", "target_start_date", "scheduled_at"}


@lru_cache(maxsize=1)
def model():
    return load_model()


def table_or_404(name: str) -> Table:
    try:
        return model().table(name)
    except KeyError:
        raise ApiError(404, "unknown_table", f"There is no table called {name!r}.")


def table_level(table: Table, ident: Identity) -> int:
    return table.table_acl.get(ident.letter, 0)


def readable(table: Table, ident: Identity) -> tuple[list[str], str]:
    """Columns this role may select and the relation to select them from (base table or masked view)."""
    level = table_level(table, ident)
    if level < MASKED:
        if level == AGGREGATE:
            raise ApiError(403, "aggregate_only", "Your role can only see aggregate figures for this.")
        raise ApiError(403, "forbidden", "Your role does not have access to this.")
    letter = ident.letter
    has_masked = any(c.level(letter) == MASKED and not c.encrypted for c in table.columns)
    floor = MASKED if has_masked else READ
    cols = [c.name for c in table.columns if c.level(letter) >= floor and not c.encrypted]
    return cols, (f"{table.id}_masked" if has_masked else table.id)


def writable(table: Table, ident: Identity) -> list[str]:
    if table.id not in DIRECT_WRITE_TABLES:
        raise ApiError(403, "not_directly_writable", "This record changes through its own flow, not directly.")
    if table_level(table, ident) < WRITE:
        raise ApiError(403, "forbidden", "Your role cannot change this.")
    return [c.name for c in table.columns
            if c.level(ident.letter) >= WRITE and not c.encrypted and c.name not in NEVER_WRITE]


def safe_context(ctx: dict | None) -> tuple[dict, list[str]]:
    kept, hidden = {}, []
    for k, v in (ctx or {}).items():
        if k in SAFE_CONTEXT_EXACT or k.endswith("_id") or k.startswith("requires_"):
            kept[k] = v
        else:
            hidden.append(k)
    return kept, sorted(hidden)
