"""Encrypted-column access (ADR-002). The database does the actual work -
app.encrypt_pii / app.decrypt_pii (migrations/sql/0011_privacy.sql) check the purpose and
consent registries and write audit_log; these are thin wrappers over that call."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, text


def encrypt_pii(conn: Connection, table: str, column: str, row_id: UUID, plaintext: str) -> None:
    """Encrypt and store a value in a registered PII column. Raises if the caller's role is not
    a collector for that column, or (when the column requires it) there is no active consent."""
    conn.execute(text("SELECT app.encrypt_pii(:t, :c, :r, :p)"),
                {"t": table, "c": column, "r": row_id, "p": plaintext})


def decrypt_pii(conn: Connection, table: str, column: str, row_id: UUID, purpose: str) -> str | None:
    """Decrypt a PII column for a named purpose. Raises if the purpose is unknown, the caller's
    role may not use it, it does not cover this column's data category, or consent is missing."""
    return conn.execute(text("SELECT app.decrypt_pii(:t, :c, :r, :p)"),
                        {"t": table, "c": column, "r": row_id, "p": purpose}).scalar_one()
