"""Run work as a worker: the role comes from the registry, and a disabled worker fails closed.

    with worker_session(engine, "gl-poster", tenant_id, user_id=...) as conn:
        post_journal_entry(conn, ...)

For code that runs outside the queue (API-started actions, payroll and timekeeping services). Queue
handlers get the same treatment through `Worker.register(..., worker=...)`.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
from uuid import UUID

from sqlalchemy import Connection, Engine, text

from daydor.agents.roles import role_for
from daydor.db.session import tenant_session


@contextmanager
def worker_session(engine: Engine, worker: str, tenant_id: UUID | None = None, *,
                   user_id: UUID | None = None, employee_id: UUID | None = None,
                   purpose: str | None = None, agent_task_run_id: UUID | None = None) -> Iterator[Connection]:
    """Switch to the worker's own database role, then ask the database whether it may run.

    Raises KeyError for an unknown worker, and a database error if the worker is disabled globally
    or for this tenant. The whole transaction rolls back, so nothing runs."""
    role = role_for(worker)
    with tenant_session(engine, role, tenant_id, user_id=user_id, employee_id=employee_id,
                        purpose=purpose, agent_task_run_id=agent_task_run_id) as conn:
        conn.execute(text("SELECT app.assert_worker_enabled(:w)"), {"w": worker})
        yield conn
