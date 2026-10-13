"""Agent runs: one row per worker job, and autonomy that does something (migration 0040).

`Worker` (daydor.queue.worker) calls these around every handler registered with `worker=`:

    begin   open (or find) the run for this job, in its own transaction, as the worker's own role
    decide  a tenant that raised the worker's caution above its default changes what happens next:
              approve -> hold the job behind g_agent_action; the same job runs once a person approves
              review  -> run it, then leave the run `review_pending` for a person to acknowledge
    finish  close the run in its own transaction, so a failed job still leaves a record

Platform actors (the workflow engine, the root orchestrator, the intake actors) are infrastructure, not workers doing
work for a tenant, so they get no runs and no holds.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Connection, text

from daydor.agents.roles import worker_records
from daydor.gates.hard import request_approval
from daydor.queue.worker import Job

AUTONOMY_RANK = {"auto": 0, "review": 1, "approve": 2}
# The person who decides a held run is the worker's owner (the registry's `owner`); ops is Daydor staff.
OWNER_ROLE = {"hr": "tenant_hr", "payroll": "tenant_payroll", "it": "tenant_it", "founder": "tenant_founder",
              "ops": "daydor_ops"}
GATE = "g_agent_action"
SETTLE_KIND = "agent.gate_resolved"
SETTLE_QUEUE = "agent-runs"
TERMINAL = ("succeeded", "review_pending", "rejected", "cancelled")


def is_tracked(worker: str) -> bool:
    """Real workers get runs; platform actors do not."""
    return next((r["kind"] != "platform" for r in worker_records() if r["worker"] == worker), False)


def is_llm(worker: str) -> bool:
    """A worker that runs on the LLM harness: kind llm with a built contract. The other llm-kind workers are deterministic
    placeholders until their harness exists, and behave as before."""
    return next((r["kind"] == "llm" and bool((r.get("contract") or {}).get("built")) for r in worker_records()
                 if r["worker"] == worker), False)


def owner_role(worker: str) -> str:
    owner = next(r["owner"] for r in worker_records() if r["worker"] == worker)
    return OWNER_ROLE[owner]


@dataclass(frozen=True)
class AgentRun:
    id: UUID
    status: str
    created: bool
    released: bool                  # an approved hold, now running
    effective_autonomy: str
    default_autonomy: str

    @property
    def tightened(self) -> str | None:
        """The tenant's autonomy when it is stricter than the worker's default, otherwise None."""
        if AUTONOMY_RANK[self.effective_autonomy] > AUTONOMY_RANK[self.default_autonomy]:
            return self.effective_autonomy
        return None

    def must_hold_before(self, worker: str) -> bool:
        """Hold the job before it starts. An LLM worker is not held up front: it proposes first, so the person approves what the
        model actually wrote (the handler asks to be held once the proposal is stored)."""
        return (self.status == "running" and not self.released and self.tightened == "approve" and not is_llm(worker))

    def needs_review_after(self, worker: str) -> bool:
        """Leave the run for a person to acknowledge: a tenant asked for review, or the worker is an LLM acting at review."""
        return self.tightened == "review" or (is_llm(worker) and self.effective_autonomy == "review")


def idempotency_key(job: Job) -> str:
    """The job's own key, or the original job's when this is an approved hold coming back (same run, new job)."""
    return job.payload.get("agent_run_key") or f"job:{job.id}"


def begin_run(conn: Connection, worker: str, job: Job) -> AgentRun:
    row = conn.execute(text("SELECT * FROM app.begin_agent_run(:w, :k, :i)"),
                       {"w": worker, "k": idempotency_key(job), "i": f"job:{job.id}"}).one()
    return AgentRun(row.run_id, row.status, row.created, row.released, row.effective_autonomy, row.default_autonomy)


def finish_run(conn: Connection, run_id: UUID, status: str, error: str | None = None,
               approval_request_id: UUID | None = None) -> None:
    conn.execute(text("SELECT app.finish_agent_run(:r, :s, :e, :a)"),
                 {"r": run_id, "s": status, "e": error, "a": approval_request_id})


def hold_for_approval(conn: Connection, run: AgentRun, worker: str) -> UUID:
    """Park the run behind g_agent_action, naming the worker's owner as the approver."""
    approval = request_approval(conn, GATE, "agent_task_run", run.id, approver_role=owner_role(worker))
    finish_run(conn, run.id, "awaiting_approval", approval_request_id=approval)
    return approval


def handle_agent_gate_resolved(conn: Connection, job: Job) -> dict:
    """Queue handler for kind 'agent.gate_resolved' (queue 'agent-runs'), run as the workflow-engine platform actor:
    when a g_agent_action request is resolved, put the held job back on its queue (approved) or stop the run (rejected).
    Every other gate, and a duplicate delivery, is a no-op."""
    approval_id = (job.payload.get("data") or {}).get("approval_request_id")      # the relayed event's own payload
    if not approval_id:
        return {"settled": None}
    return {"settled": conn.execute(text("SELECT app.settle_agent_run(:a)"), {"a": approval_id}).scalar_one()}
