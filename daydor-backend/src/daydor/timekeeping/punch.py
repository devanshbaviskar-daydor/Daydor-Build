"""time_punch: employee self-service, by design (table grant `E: WRITE`, no agent writer in the
model -- same pattern as consent_record). This is a thin wrapper, not a queue handler: there is
nothing for an agent to do here, only a direct write the employee's own session makes."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Connection, text


def record_punch(conn: Connection, *, employee_id: UUID, punched_at: datetime, kind: str,
                 source: str = "web") -> UUID:
    return conn.execute(
        text("INSERT INTO time_punch (employee_id, punched_at, kind, source) "
             "VALUES (:e, :p, :k, :s) RETURNING id"),
        {"e": employee_id, "p": punched_at, "k": kind, "s": source}).scalar_one()
