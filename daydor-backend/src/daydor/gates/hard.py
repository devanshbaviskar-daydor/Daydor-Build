"""Hard gates: human approvals. The database enforces who may resolve, maker-checker and
immutability (migrations/sql/0006_gates.sql); these helpers are the application API."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Connection, text

from daydor.queue import emit_event


def request_approval(conn: Connection, gate_id: str, subject_table: str, subject_id: UUID, *,
                     idempotency_key: str | None = None, deadline_at: datetime | None = None,
                     approver_role: str | None = None) -> UUID:
    """Open (or return the existing) pending request for a gate on one row.

    The requester is taken from the session by the database, never from arguments."""
    key = idempotency_key or f"{gate_id}:{subject_table}:{subject_id}"
    existing = conn.execute(text("SELECT id FROM approval_request WHERE idempotency_key = :k"),
                            {"k": key}).scalar_one_or_none()
    if existing:
        return existing
    rid = conn.execute(
        text("INSERT INTO approval_request (gate_type, subject_table, subject_id, required_approver_role, "
             "status, deadline_at, idempotency_key) VALUES (:g, :t, :s, :r, 'pending', :d, :k) RETURNING id"),
        {"g": gate_id, "t": subject_table, "s": subject_id, "r": approver_role, "d": deadline_at, "k": key},
    ).scalar_one()
    emit_event(conn, "gate.requested", subject_table, subject_id,
               {"approval_request_id": str(rid), "gate_id": gate_id})
    return rid


def resolve(conn: Connection, request_id: UUID, decision: str, note: str | None = None) -> str:
    return conn.execute(text("SELECT app.resolve_approval(:r, :d, :n)"),
                        {"r": request_id, "d": decision, "n": note}).scalar_one()


def status(conn: Connection, request_id: UUID) -> str:
    return conn.execute(text("SELECT status FROM approval_request WHERE id = :r"),
                        {"r": request_id}).scalar_one()
