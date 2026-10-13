"""State-machine runner over app.workflow_definition / app.workflow_instance.

    engine = WorkflowEngine(soft_gates={...}, decider=client)
    wid = engine.start(conn, "hire", "job_requisition", req_id, {"requires_g_offer_band": False})
    engine.fire(conn, wid, "advance", event_id="evt-123")

fire() either moves the instance, or parks it in waiting_gate behind a hard gate. When the gate is
resolved, app.resolve_approval emits gate.resolved; the queue delivers it to
`gate_resolved_handler`, which completes the parked transition (or follows on_reject).

Runs inside the caller's transaction (normally an agent role session). event_id makes repeated
delivery of the same event a no-op; the version column turns concurrent transitions into a
ConcurrentTransition error so the job retries.

Every job a state's enter_jobs enqueues gets the instance's full `context` dict in its payload
(`job.payload["context"]`), alongside `workflow_instance_id`/`subject_table`/`subject_id`. A
worker reads whatever an earlier step put there with `context_patch`, does its own work, and
(normally) calls `fire(conn, instance_id, "advance", context_patch={...})` in the same transaction
to both record its own output for the next step and move the instance on.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, text

from daydor.gates.decider import DeciderClient
from daydor.gates.hard import request_approval
from daydor.gates.soft import SoftGate, run_soft_gate
from daydor.queue import enqueue


class WorkflowError(RuntimeError):
    pass


class ConcurrentTransition(WorkflowError):
    pass


@dataclass(frozen=True)
class TransitionResult:
    instance_id: UUID
    state: str
    status: str
    outcome: str                                # moved | waiting_gate | rejected | duplicate
    approval_request_id: UUID | None = None


class WorkflowEngine:
    def __init__(self, soft_gates: dict[str, SoftGate] | None = None, decider: DeciderClient | None = None) -> None:
        self.soft_gates = soft_gates or {}
        self.decider = decider

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _definition(conn: Connection, name: str, version: int | None = None) -> tuple[int, dict]:
        if version is None:
            row = conn.execute(text("SELECT version, definition FROM app.workflow_definition "
                                    "WHERE name = :n AND active"), {"n": name}).one_or_none()
        else:
            row = conn.execute(text("SELECT version, definition FROM app.workflow_definition "
                                    "WHERE name = :n AND version = :v"), {"n": name, "v": version}).one_or_none()
        if row is None:
            raise WorkflowError(f"no workflow definition {name!r} (version {version or 'active'})")
        return row.version, row.definition

    @staticmethod
    def _instance(conn: Connection, instance_id: UUID):
        row = conn.execute(text("SELECT * FROM app.workflow_instance WHERE id = :i"),
                           {"i": instance_id}).one_or_none()
        if row is None:
            raise WorkflowError(f"workflow instance {instance_id} not found")
        return row

    @staticmethod
    def _log(conn, inst, event, event_id, to_state, outcome, approval_id=None) -> bool:
        """Record a transition. Returns False if this event_id was already applied."""
        inserted = conn.execute(
            text("INSERT INTO app.workflow_transition (instance_id, event, event_id, from_state, to_state, "
                 "outcome, approval_request_id) VALUES (:i, :e, :eid, :f, :t, :o, :a) "
                 "ON CONFLICT (instance_id, event_id) DO NOTHING RETURNING id"),
            {"i": inst.id, "e": event, "eid": event_id, "f": inst.state, "t": to_state, "o": outcome,
             "a": approval_id},
        ).scalar_one_or_none()
        return inserted is not None

    @staticmethod
    def _update(conn, inst, **fields) -> None:
        sets = ", ".join(f"{k} = :{k}" for k in fields)
        params = {**fields, "id": inst.id, "v": inst.version}
        if "context" in params:
            params["context"] = json.dumps(params["context"])
            sets = sets.replace("context = :context", "context = CAST(:context AS jsonb)")
        n = conn.execute(text(f"UPDATE app.workflow_instance SET {sets}, version = version + 1 "
                              f"WHERE id = :id AND version = :v"), params).rowcount
        if n != 1:
            raise ConcurrentTransition(f"instance {inst.id} changed concurrently; retry")

    def _enter(self, conn, inst, state: str, definition: dict, context: dict | None = None) -> str:
        """context defaults to inst.context (used by start(), where it's already current); every
        other caller is advancing the instance in the same call and must pass the just-merged
        context explicitly, since inst itself is a snapshot from before that merge."""
        spec = definition["states"][state]
        for job in spec.get("enter_jobs", []):
            enqueue(conn, job["queue"], job["kind"],
                    {"workflow_instance_id": str(inst.id), "state": state,
                     "subject_table": inst.subject_table, "subject_id": str(inst.subject_id),
                     "context": context if context is not None else inst.context},
                    idempotency_key=f"wf:{inst.id}:{state}:{job['kind']}")
        return "completed" if spec.get("terminal") else "running"

    # ------------------------------------------------------------------ API
    def start(self, conn: Connection, name: str, subject_table: str, subject_id: UUID,
              context: dict[str, Any] | None = None) -> UUID:
        version, definition = self._definition(conn, name)
        initial = definition["initial"]
        row = conn.execute(
            text("INSERT INTO app.workflow_instance (definition_name, definition_version, subject_table, "
                 "subject_id, state, context) VALUES (:n, :v, :t, :s, :st, CAST(:c AS jsonb)) "
                 "ON CONFLICT (tenant_id, definition_name, subject_table, subject_id) DO NOTHING RETURNING id"),
            {"n": name, "v": version, "t": subject_table, "s": subject_id, "st": initial,
             "c": json.dumps(context or {})},
        ).scalar_one_or_none()
        if row is None:   # already started for this subject: idempotent
            return conn.execute(text("SELECT id FROM app.workflow_instance WHERE definition_name = :n "
                                     "AND subject_table = :t AND subject_id = :s"),
                                {"n": name, "t": subject_table, "s": subject_id}).scalar_one()
        inst = self._instance(conn, row)
        status = self._enter(conn, inst, initial, definition)
        if status != "running":
            self._update(conn, inst, status=status)
        return row

    def fire(self, conn: Connection, instance_id: UUID, event: str, *, event_id: str | None = None,
             context_patch: dict[str, Any] | None = None) -> TransitionResult:
        inst = self._instance(conn, instance_id)
        if event_id and conn.execute(text("SELECT 1 FROM app.workflow_transition WHERE instance_id = :i "
                                          "AND event_id = :e"), {"i": inst.id, "e": event_id}).first():
            return TransitionResult(inst.id, inst.state, inst.status, "duplicate", inst.waiting_on_approval)
        if inst.status != "running":
            raise WorkflowError(f"instance {inst.id} is {inst.status}; cannot accept {event!r}")
        _, definition = self._definition(conn, inst.definition_name, inst.definition_version)
        transition = definition["states"][inst.state].get("on", {}).get(event)
        if transition is None:
            raise WorkflowError(f"no transition for {event!r} from state {inst.state!r}")

        context = {**inst.context, **(context_patch or {})}
        approval_id = None
        gate = transition.get("gate")
        if gate and transition.get("gate_if") and not context.get(transition["gate_if"]):
            gate = None   # conditional gate not required for this instance
        if transition.get("soft_gate"):
            sg = self.soft_gates.get(transition["soft_gate"])
            if sg is None or self.decider is None:
                raise WorkflowError(f"soft gate {transition['soft_gate']} is not configured")
            outcome = run_soft_gate(conn, sg, inst.subject_table, inst.subject_id, self.decider)
            approval_id = outcome.approval_request_id     # None when the soft gate passed
        elif gate:
            approval_id = request_approval(conn, gate, inst.subject_table, inst.subject_id,
                                           idempotency_key=f"wf:{inst.id}:{inst.state}:{event}:{gate}")
            approved = conn.execute(text("SELECT status = 'approved' FROM approval_request WHERE id = :a"),
                                    {"a": approval_id}).scalar_one()
            if approved:   # already approved (e.g. re-fired after approval): move straight on
                return self._move(conn, inst, event, event_id, transition["to"], definition, context,
                                  approval_id)

        if approval_id is not None:
            self._log(conn, inst, event, event_id, inst.state, "waiting_gate", approval_id)
            self._update(conn, inst, status="waiting_gate", pending_event=event,
                         waiting_on_approval=approval_id, context=context)
            return TransitionResult(inst.id, inst.state, "waiting_gate", "waiting_gate", approval_id)
        return self._move(conn, inst, event, event_id, transition["to"], definition, context, None)

    def _move(self, conn, inst, event, event_id, to_state, definition, context, approval_id) -> TransitionResult:
        if not self._log(conn, inst, event, event_id, to_state, "moved", approval_id):
            return TransitionResult(inst.id, inst.state, inst.status, "duplicate")
        status = self._enter(conn, inst, to_state, definition, context)
        self._update(conn, inst, state=to_state, status=status, pending_event=None,
                     waiting_on_approval=None, context=context)
        return TransitionResult(inst.id, to_state, status, "moved", approval_id)

    def on_gate_resolved(self, conn: Connection, approval_request_id: UUID) -> list[TransitionResult]:
        results = []
        decision = conn.execute(text("SELECT status FROM approval_request WHERE id = :a"),
                                {"a": approval_request_id}).scalar_one()
        waiting = conn.execute(text("SELECT id FROM app.workflow_instance WHERE waiting_on_approval = :a "
                                    "AND status = 'waiting_gate'"), {"a": approval_request_id}).scalars().all()
        for wid in waiting:
            inst = self._instance(conn, wid)
            _, definition = self._definition(conn, inst.definition_name, inst.definition_version)
            transition = definition["states"][inst.state]["on"][inst.pending_event]
            event_id = f"gate:{approval_request_id}"
            if decision == "approved":
                results.append(self._move(conn, inst, inst.pending_event, event_id, transition["to"],
                                          definition, inst.context, approval_request_id))
            elif transition.get("on_reject"):
                target, status = transition["on_reject"], inst.status
                if self._log(conn, inst, inst.pending_event, event_id, target, "rejected", approval_request_id):
                    status = self._enter(conn, inst, target, definition)
                    self._update(conn, inst, state=target, status=status, pending_event=None,
                                 waiting_on_approval=None)
                results.append(TransitionResult(inst.id, target, status, "rejected", approval_request_id))
            else:   # rejected with no on_reject path: stop the workflow for a human to restart
                self._log(conn, inst, inst.pending_event, event_id, inst.state, "rejected", approval_request_id)
                self._update(conn, inst, status="cancelled", pending_event=None, waiting_on_approval=None)
                results.append(TransitionResult(inst.id, inst.state, "cancelled", "rejected", approval_request_id))
        return results


def gate_resolved_handler(engine: WorkflowEngine):
    """Queue handler for topic gate.resolved (subscription seeded in migration 0009)."""
    def handle(conn: Connection, job) -> dict:
        approval = UUID(job.payload["data"]["approval_request_id"])
        results = engine.on_gate_resolved(conn, approval)
        return {"resumed": [str(r.instance_id) for r in results]}
    return handle
