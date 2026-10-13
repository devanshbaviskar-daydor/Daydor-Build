"""Job dispatcher.

    worker = Worker(engine, queue="hr", worker_id="hr-1")
    worker.register("employee.hired", role="agent_hr", fn=handle_hire)      # a domain role, or
    worker.register("job_posting_publisher", worker="job-posting-publisher", fn=handle_publish)
    worker.tick()          # relay outbox, fire timers, claim and run a batch

Each handler runs in its own transaction, as the role it was registered with and with the job's
tenant as session context, so row security and grants apply to agent work exactly as they do to
people. A handler registered with `worker=` takes its role from the worker registry
(`daydor.agents.roles`) and first runs `app.assert_worker_enabled`: a worker that is disabled, globally
or for the job's tenant, fails the job closed (it is recorded, retried and dead-lettered like any
other failure) instead of being skipped. Completion is recorded in a separate dispatcher transaction, so delivery is at-least-once:
handlers must be idempotent (use the job id or an idempotency key for any write).
"""
from __future__ import annotations

import json
import logging
import traceback
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable
from uuid import UUID

from sqlalchemy import Connection, Engine, text

from daydor.db.session import tenant_session

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Job:
    id: UUID
    tenant_id: UUID | None
    queue: str
    kind: str
    payload: dict
    attempts: int
    max_attempts: int


@dataclass(frozen=True)
class Handler:
    kind: str
    role: str
    fn: Callable[[Connection, Job], Any]
    purpose: str | None = None
    worker: str | None = None


class Worker:
    def __init__(self, engine: Engine, queue: str, worker_id: str, *, batch: int = 10,
                 lease: timedelta = timedelta(minutes=5)) -> None:
        self.engine, self.queue, self.worker_id = engine, queue, worker_id
        self.batch, self.lease = batch, lease
        self.handlers: dict[str, Handler] = {}

    def register(self, kind: str, role: str | None = None, fn: Callable[[Connection, Job], Any] | None = None,
                 purpose: str | None = None, *, worker: str | None = None) -> None:
        """Give `role` (a domain or people role) or `worker` (a registry worker or platform actor),
        never both. A worker's role comes from the registry, and the database refuses the job if it is
        disabled."""
        if fn is None:
            raise TypeError("register() needs fn")
        if (role is None) == (worker is None):
            raise TypeError("register() needs exactly one of role= or worker=")
        if worker is not None:
            from daydor.agents.roles import role_for
            role = role_for(worker)
        self.handlers[kind] = Handler(kind, role, fn, purpose, worker)

    # -- dispatcher-side operations (daydor_worker role) ---------------------------------------
    def _dispatcher(self):
        return tenant_session(self.engine, "daydor_worker")

    def relay_outbox(self, limit: int = 100) -> int:
        with self._dispatcher() as conn:
            return conn.execute(text("SELECT app.relay_outbox(:n)"), {"n": limit}).scalar_one()

    def fire_due_timers(self, limit: int = 100) -> int:
        with self._dispatcher() as conn:
            return conn.execute(text("SELECT app.fire_due_timers(:n)"), {"n": limit}).scalar_one()

    def claim(self) -> list[Job]:
        with self._dispatcher() as conn:
            rows = conn.execute(
                text("SELECT id, tenant_id, queue, kind, payload, attempts, max_attempts "
                     "FROM app.claim_jobs(:q, :w, :n, :lease)"),
                {"q": self.queue, "w": self.worker_id, "n": self.batch, "lease": self.lease},
            ).all()
        return [Job(r.id, r.tenant_id, r.queue, r.kind, r.payload, r.attempts, r.max_attempts) for r in rows]

    def _complete(self, job: Job, result: Any) -> None:
        with self._dispatcher() as conn:
            conn.execute(text("SELECT app.complete_job(:j, :w, CAST(:r AS jsonb))"),
                         {"j": job.id, "w": self.worker_id, "r": json.dumps(result, default=str)})

    def _fail(self, job: Job, error: str) -> str:
        with self._dispatcher() as conn:
            return conn.execute(text("SELECT app.fail_job(:j, :w, :e)"),
                                {"j": job.id, "w": self.worker_id, "e": error[:4000]}).scalar_one()

    # -- execution ------------------------------------------------------------------------------
    def run_job(self, job: Job) -> str:
        handler = self.handlers.get(job.kind)
        if handler is None:
            return self._fail(job, f"no handler registered for kind {job.kind!r}")
        try:
            with tenant_session(self.engine, handler.role, job.tenant_id, purpose=handler.purpose) as conn:
                if handler.worker is not None:
                    conn.execute(text("SELECT app.assert_worker_enabled(:w)"), {"w": handler.worker})
                result = handler.fn(conn, job)
        except Exception as exc:  # noqa: BLE001 - every failure is recorded on the job
            log.warning("job %s (%s) failed: %s", job.id, job.kind, exc)
            return self._fail(job, f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=5)}")
        self._complete(job, result)
        return "succeeded"

    def tick(self) -> dict[str, int]:
        relayed = self.relay_outbox()
        fired = self.fire_due_timers()
        outcomes: dict[str, int] = {"relayed": relayed, "timers_fired": fired}
        for job in self.claim():
            status = self.run_job(job)
            outcomes[status] = outcomes.get(status, 0) + 1
        return outcomes
