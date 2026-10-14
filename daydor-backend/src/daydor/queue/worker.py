"""Job dispatcher.

    worker = Worker(engine, queue="hr", worker_id="hr-1")
    worker.register("employee.hired", role="tenant_hr", fn=handle_hire)     # a people role, or
    worker.register("job_posting_publisher", worker="job-posting-publisher", fn=handle_publish)
    worker.tick()          # relay outbox, fire timers, claim and run a batch

Each handler runs in its own transaction, as the role it was registered with and with the job's
tenant as session context, so row security and grants apply to agent work exactly as they do to
people. A handler registered with `worker=` takes its role from the worker registry
(`daydor.agents.roles`) and first runs `app.assert_worker_enabled`: a worker that is disabled, globally
or for the job's tenant, fails the job closed (it is recorded, retried and dead-lettered like any
other failure) instead of being skipped. Handlers for real workers (not platform actors) are also tracked: each job
opens an `agent_task_run` in its own transaction, and a tenant that raised the worker's autonomy above its default
holds the job behind a person's approval (`approve`) or flags it for review (`review`); see daydor.agents.runs.
Completion is recorded in a separate dispatcher transaction, so delivery is at-least-once:
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


class Deferred(Exception):
    """Raised by a handler that cannot run yet through no fault of the job (an integration's circuit is open): the job goes back on its
    queue for `seconds` later without spending an attempt, and an agent run is left open for it."""
    def __init__(self, seconds: int, reason: str = "deferred") -> None:
        super().__init__(reason)
        self.seconds = seconds


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
        tracked = handler.worker is not None and self._tracked(handler.worker)
        if tracked:
            from daydor.agents import runs
        run = None
        try:
            if tracked:
                run = self._begin(handler, job)
                if run.status == "awaiting_approval":                   # held, still waiting for a person
                    self._complete(job, {"held": str(run.id)})
                    return "held"
                if run.status in runs.TERMINAL:                          # a duplicate delivery of finished work
                    self._complete(job, {"skipped": run.status, "run": str(run.id)})
                    return "skipped"
                if run.must_hold_before(handler.worker):                 # the tenant wants a person's yes first
                    with tenant_session(self.engine, handler.role, job.tenant_id) as conn:
                        runs.hold_for_approval(conn, run, handler.worker)
                    self._complete(job, {"held": str(run.id)})
                    return "held"
            with tenant_session(self.engine, handler.role, job.tenant_id, purpose=handler.purpose,
                                agent_task_run_id=run.id if run else None) as conn:
                if handler.worker is not None and not tracked:
                    conn.execute(text("SELECT app.assert_worker_enabled(:w)"), {"w": handler.worker})
                if run is not None and run.needs_review_after(handler.worker):
                    # Jobs this handler enqueues are held until a person acknowledges the run (0041): review blocks the next step.
                    conn.execute(text("SELECT set_config('app.agent_review_hold', :r, true)"), {"r": str(run.id)})
                result = handler.fn(conn, job)
            if isinstance(result, dict) and run is not None:
                if result.get("_agent_hold"):                              # an LLM worker's proposal is stored; a person decides
                    with tenant_session(self.engine, handler.role, job.tenant_id) as conn:
                        runs.hold_for_approval(conn, run, handler.worker)
                    self._complete(job, {"held": str(run.id), "proposal": result["_agent_hold"]})
                    return "held"
                if result.get("_agent_defer") is not None:                 # a circuit is open: not the job's fault, no attempt spent
                    self._defer(job, int(result["_agent_defer"]), str(result.get("reason", "deferred")))
                    return "deferred"
                if result.get("_agent_fail"):                              # the agent side failed; the records of why are committed
                    self._finish(handler, job, run, "failed", str(result["_agent_fail"]))
                    return self._fail(job, f"{result['_agent_fail']}: {result.get('error', '')}")
        except Deferred as d:
            self._defer(job, d.seconds, str(d))
            return "deferred"
        except Exception as exc:  # noqa: BLE001 - every failure is recorded on the job
            log.warning("job %s (%s) failed: %s", job.id, job.kind, exc)
            if run is not None:
                self._finish(handler, job, run, "failed", type(exc).__name__)
            return self._fail(job, f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=5)}")
        if run is not None:
            self._finish(handler, job, run, "review_pending" if run.needs_review_after(handler.worker) else "succeeded")
        self._complete(job, result)
        return "succeeded"

    def _defer(self, job: Job, seconds: int, reason: str) -> None:
        with self._dispatcher() as conn:
            conn.execute(text("SELECT app.defer_job(:j, :w, now() + make_interval(secs => :s), :r)"),
                         {"j": job.id, "w": self.worker_id, "s": max(seconds, 1), "r": reason})

    @staticmethod
    def _tracked(worker: str) -> bool:
        from daydor.agents import runs
        return runs.is_tracked(worker)

    def _begin(self, handler: Handler, job: Job):
        """Open the run in its own transaction, as the worker's role. Checks the worker is enabled first, so a
        disabled worker fails closed and leaves no run behind."""
        from daydor.agents import runs
        with tenant_session(self.engine, handler.role, job.tenant_id) as conn:
            conn.execute(text("SELECT app.assert_worker_enabled(:w)"), {"w": handler.worker})
            run = runs.begin_run(conn, handler.worker, job)
            if run.status == "running" and runs.is_llm(handler.worker):
                from dataclasses import replace
                from daydor.agents import rollout
                run = replace(run, stage=rollout.stage_for(conn, handler.worker))
            return run

    def _finish(self, handler: Handler, job: Job, run, status: str, error: str | None = None) -> None:
        from daydor.agents import runs
        with tenant_session(self.engine, handler.role, job.tenant_id) as conn:
            runs.finish_run(conn, run.id, status, error)

    def tick(self) -> dict[str, int]:
        relayed = self.relay_outbox()
        fired = self.fire_due_timers()
        outcomes: dict[str, int] = {"relayed": relayed, "timers_fired": fired}
        for job in self.claim():
            status = self.run_job(job)
            outcomes[status] = outcomes.get(status, 0) + 1
        return outcomes
