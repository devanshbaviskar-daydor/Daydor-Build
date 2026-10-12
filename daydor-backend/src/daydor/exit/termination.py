"""Exit flow step 1: `termination`. HR-admin-initiated direct write -- the model names no agent
worker for creating this row (its two writers, `rehire-eligibility-flagger` and
`exit-interview-scheduler`, both update an existing row), so `initiate_termination` is a plain
function an HR session calls, not a queue handler.

Also covers the flow's final two steps that write back onto `termination`/`employee`:
`flag_rehire_eligibility` (rehire-eligibility-flagger) and `close_employee_record`
(employee-record-writer's close-out, step 14: `is_active = false`, `date_of_exit` set -- the
Gratuity Act retention anchor).
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import Connection, text


def initiate_termination(conn: Connection, *, employee_id: UUID, termination_type: str,
                         reason_code: str, notice_date: date, last_working_day: date,
                         initiated_by_user_id: UUID) -> UUID:
    """Idempotent on employee_id: one open termination per employee."""
    existing = conn.execute(text("SELECT id FROM termination WHERE employee_id = :e"),
                            {"e": employee_id}).scalar_one_or_none()
    if existing is not None:
        return existing
    return conn.execute(
        text("INSERT INTO termination (employee_id, termination_type, reason_code, notice_date, "
             "last_working_day, initiated_by_user_id) VALUES (:e, :tt, :rc, :nd, :lwd, :u) "
             "RETURNING id"),
        {"e": employee_id, "tt": termination_type, "rc": reason_code, "nd": notice_date,
         "lwd": last_working_day, "u": initiated_by_user_id}).scalar_one()


def flag_rehire_eligibility(conn: Connection, *, termination_id: UUID, rehire_eligible: str) -> None:
    conn.execute(text("UPDATE termination SET rehire_eligible = :r WHERE id = :t"),
                {"r": rehire_eligible, "t": termination_id})


def close_employee_record(conn: Connection, *, employee_id: UUID, date_of_exit: date) -> None:
    conn.execute(text("UPDATE employee SET is_active = false, date_of_exit = :d WHERE id = :e"),
                {"d": date_of_exit, "e": employee_id})
