"""A circuit breaker per integration, kept in the database (migration 0043) so every worker process shares one view.

    allowed, retry_after_s = circuit.allow(conn, "model_provider")
    ...call the vendor...
    circuit.record(conn, "model_provider", ok=True)

Closed lets calls through. After `threshold` failures in a row it opens and refuses calls for `cooldown_s`; then calls are let
through again as probes and the first result decides. An integration must be registered in app.integration_circuit.
"""
from __future__ import annotations

from typing import NamedTuple

from sqlalchemy import Connection, text

MODEL_PROVIDER = "model_provider"


class Allowance(NamedTuple):
    allowed: bool
    retry_after_s: int


def allow(conn: Connection, integration: str) -> Allowance:
    row = conn.execute(text("SELECT * FROM app.circuit_allow(:i)"), {"i": integration}).one()
    return Allowance(row.allowed, row.retry_after_s)


def record(conn: Connection, integration: str, ok: bool, error: str | None = None) -> str:
    """Returns the circuit's state afterwards ('closed' or 'open')."""
    return conn.execute(text("SELECT app.circuit_record(:i, :o, :e)"), {"i": integration, "o": ok, "e": error}).scalar_one()
