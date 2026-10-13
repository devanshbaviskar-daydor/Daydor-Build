"""Per-transaction session context.

Every unit of work runs in one transaction that first switches to the acting role and sets the
context the database uses for row security, person scope, PII purpose checks and audit:

    with tenant_session(engine, role="tenant_hr", tenant_id=..., user_id=...) as conn:
        conn.execute(...)

Everything is SET LOCAL, so it ends with the transaction and is safe with transaction-mode pooling.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator
from uuid import UUID

from sqlalchemy import Connection, Engine, create_engine, text

from daydor.config import database_url

APP_ROLES = frozenset({
    "daydor_admin", "daydor_ops", "tenant_founder", "tenant_hr", "tenant_payroll", "tenant_it",
    "tenant_manager", "tenant_employee", "external_auditor", "daydor_worker",
})
# Agent work runs as per-worker roles (`worker_<name>`, from the registry; see daydor.agents.roles). The
# domain roles `agent_<domain>` that used to run it were dropped in 0034.


def _is_worker_role(role: str) -> bool:
    """Per-worker roles (worker_<name>) come from the registry. Imported lazily: the registry reads
    JSON from the repo, which plain people-role sessions should not need."""
    if not role.startswith("worker_"):
        return False
    from daydor.agents.roles import worker_role_names
    return role in worker_role_names()


@dataclass(frozen=True)
class SessionContext:
    role: str
    tenant_id: UUID | None = None
    user_id: UUID | None = None
    employee_id: UUID | None = None
    purpose: str | None = None
    agent_task_run_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.role not in APP_ROLES and not _is_worker_role(self.role):
            raise ValueError(f"unknown role {self.role!r}")


def make_engine(url: str | None = None) -> Engine:
    return create_engine(url or database_url(), pool_pre_ping=True)


def apply_context(conn: Connection, ctx: SessionContext) -> None:
    # Role names cannot be bound parameters; they are validated against APP_ROLES or the registry above.
    conn.exec_driver_sql(f'SET LOCAL ROLE "{ctx.role}"')
    conn.execute(
        text("SELECT set_config('app.tenant_id', :t, true), set_config('app.user_id', :u, true), "
             "set_config('app.employee_id', :e, true), set_config('app.purpose', :p, true), "
             "set_config('app.agent_task_run_id', :r, true)"),
        {"t": str(ctx.tenant_id or ""), "u": str(ctx.user_id or ""), "e": str(ctx.employee_id or ""),
         "p": ctx.purpose or "", "r": str(ctx.agent_task_run_id or "")},
    )


@contextmanager
def tenant_session(engine: Engine, role: str, tenant_id: UUID | None = None, *,
                   user_id: UUID | None = None, employee_id: UUID | None = None,
                   purpose: str | None = None, agent_task_run_id: UUID | None = None) -> Iterator[Connection]:
    ctx = SessionContext(role, tenant_id, user_id, employee_id, purpose, agent_task_run_id)
    with engine.begin() as conn:
        apply_context(conn, ctx)
        yield conn
