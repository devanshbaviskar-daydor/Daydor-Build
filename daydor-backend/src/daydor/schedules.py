"""Starts the recurring platform timers (statutory-clock scan, approval sweep) for every active tenant.

Idempotent (the timers have per-day and per-hour keys), so run it at startup and then daily. Each tenant is handled in its own
transaction as the `root-orchestrator` platform actor; the tenant list comes from app.platform_tenants().
"""
from __future__ import annotations

from sqlalchemy import Engine, text

from daydor import approval_sla, clocks
from daydor.agents.session import worker_session
from daydor.db.session import tenant_session


def ensure_platform_schedules(engine: Engine) -> int:
    with tenant_session(engine, "daydor_worker") as conn:
        tenants = list(conn.execute(text("SELECT app.platform_tenants()")).scalars())
    for tenant in tenants:
        with worker_session(engine, "root-orchestrator", tenant) as conn:
            clocks.start_clock_scan(conn)
            approval_sla.start_sweep(conn)
    return len(tenants)
