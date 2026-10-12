"""Soft gates: Jev pre-checks in front of hard gates.

Rules (enforced here and, where it matters, again in the database):
  * Inputs are declared as model columns and checked against the gate's max_input_class.
    C3 (restricted PII) and C4 (special category) can never be sent.
  * Only a hash of the input is stored, never the input itself.
  * Fail closed: an error, a timeout or low confidence escalates to the hard gate.
  * Shadow mode logs Jev's view but always escalates (the database forces this).
  * A soft gate never resolves a hard gate; at most it skips opening one.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID

from sqlalchemy import Connection, text

from daydor.gates.hard import request_approval
from daydor.gates.jev import DecisionSchema, JevClient, JevResult
from daydor.model import load_model

CLASS_RANK = {"S": 0, "C0": 1, "C1": 2, "C2": 3, "C3": 4, "C4": 5}


class ForbiddenInput(ValueError):
    pass


@dataclass(frozen=True)
class SoftGate:
    gate_id: str
    schema: DecisionSchema
    inputs: tuple[str, ...]                                   # "table.column" sources
    build_state: Callable[[Connection, UUID], dict[str, Any]]
    pass_rule: Callable[[JevResult], tuple[bool, float]]     # -> (passes, confidence)
    timeout_s: float = 0.5


@dataclass(frozen=True)
class SoftGateOutcome:
    evaluation_id: UUID
    effective_decision: str          # 'pass' | 'escalate'
    model_decision: str              # 'pass' | 'escalate' | 'error'
    confidence: float | None
    approval_request_id: UUID | None


def check_inputs(gate_id: str, inputs: tuple[str, ...], max_class: str) -> None:
    model = load_model()
    for ref in inputs:
        table, column = ref.split(".", 1)
        col = model.table(table).column(column)
        if CLASS_RANK[col.cls] >= CLASS_RANK["C3"] or col.encrypted:
            raise ForbiddenInput(f"{gate_id}: {ref} is {col.cls}; restricted data never goes to Jev")
        if CLASS_RANK[col.cls] > CLASS_RANK[max_class]:
            raise ForbiddenInput(f"{gate_id}: {ref} is {col.cls}, above this gate's limit {max_class}")


def input_hash(state: dict[str, Any]) -> str:
    canonical = json.dumps(state, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _definition(conn: Connection, gate_id: str):
    row = conn.execute(text("SELECT * FROM app.gate_definition WHERE gate_id = :g AND kind = 'soft'"),
                       {"g": gate_id}).one_or_none()
    if row is None:
        raise KeyError(f"{gate_id} is not a registered soft gate")
    return row


def run_soft_gate(conn: Connection, gate: SoftGate, subject_table: str, subject_id: UUID,
                  client: JevClient) -> SoftGateOutcome:
    d = _definition(conn, gate.gate_id)
    check_inputs(gate.gate_id, gate.inputs, d.max_input_class)
    if subject_table not in d.tables:
        raise ValueError(f"{gate.gate_id} does not cover {subject_table}")

    state = gate.build_state(conn, subject_id)
    unknown = set(state) - {ref.split(".", 1)[1] for ref in gate.inputs}
    if unknown:
        raise ForbiddenInput(f"{gate.gate_id}: state has undeclared fields {sorted(unknown)}")

    started = time.monotonic()
    output, confidence, engine_version, error = None, None, None, None
    try:
        result = client.decide(gate.schema, state, gate.timeout_s)
        latency_ms = int((time.monotonic() - started) * 1000)
        if latency_ms > gate.timeout_s * 1000:
            raise TimeoutError(f"Jev answered in {latency_ms} ms, over {gate.timeout_s}s budget")
        passes, confidence = gate.pass_rule(result)
        model_decision = "pass" if passes else "escalate"
        engine_version = result.engine_version
        output = {k: {"value": a.value, "probabilities": a.probabilities} for k, a in result.answers.items()}
    except Exception as exc:  # noqa: BLE001 - any failure fails closed
        latency_ms = int((time.monotonic() - started) * 1000)
        model_decision, error = "error", f"{type(exc).__name__}: {exc}"

    eval_id = conn.execute(
        text("SELECT app.record_gate_evaluation(CAST(:g AS text), CAST(:st AS text), CAST(:sid AS uuid), "
             "'jev', CAST(:ev AS text), CAST(:sv AS text), CAST(:ih AS text), CAST(:cols AS text[]), "
             "CAST(:out AS jsonb), CAST(:conf AS numeric), CAST(:md AS text), CAST(:lat AS integer), "
             "CAST(:err AS text))"),
        {"g": gate.gate_id, "st": subject_table, "sid": subject_id, "ev": engine_version,
         "sv": f"{gate.schema.name}@{gate.schema.version}", "ih": input_hash(state),
         "cols": list(gate.inputs), "out": json.dumps(output), "conf": confidence, "md": model_decision,
         "lat": latency_ms, "err": error},
    ).scalar_one()
    effective = conn.execute(text("SELECT effective_decision FROM app.gate_evaluation WHERE id = :i"),
                             {"i": eval_id}).scalar_one()

    approval_id = None
    if effective == "escalate":
        approval_id = request_approval(conn, d.escalate_to, subject_table, subject_id)
    return SoftGateOutcome(eval_id, effective, model_decision, confidence, approval_id)
