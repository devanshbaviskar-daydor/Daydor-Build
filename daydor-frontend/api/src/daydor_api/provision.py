"""Platform provisioning helpers for development and tests.

`insert` runs as the connection's own role (the database owner in development), so it bypasses row
security. It models what Daydor ops does when onboarding a tenant. It must never be called from a
request handler."""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Connection, text

from .access import model

DUMMY = {
    "uuid": lambda: str(uuid.uuid4()), "text": lambda: "x", "enum": lambda: "default",
    "jsonb": lambda: json.dumps({}), "numeric": lambda: 0, "date": lambda: date(2026, 1, 1),
    "ts": lambda: datetime(2026, 1, 1, tzinfo=timezone.utc), "bool": lambda: True,
    "int": lambda: 0, "bytea": lambda: b"\x00", "citext": lambda: f"{uuid.uuid4().hex[:8]}@example.com",
}
SKIP = {"id", "created_at", "updated_at"}


def insert(conn: Connection, table: str, **values) -> uuid.UUID:
    t = model().table(table)
    row = {}
    for c in t.columns:
        if c.name in SKIP:
            continue
        if c.name in values:
            row[c.name] = values[c.name]
        elif not c.nullable and c.name != "tenant_id":
            if c.fk:
                raise ValueError(f"{table}.{c.name} is a required reference; pass it explicitly")
            row[c.name] = f"{c.name}-{uuid.uuid4().hex[:12]}" if c.unique and c.type in ("text", "enum") \
                else DUMMY["bytea" if c.encrypted else c.type]()
    for k in values:
        if k not in row:
            raise KeyError(f"{table} has no column {k}")
    cols = ", ".join(row)
    marks = ", ".join(f":{k}" for k in row)
    return conn.execute(text(f'INSERT INTO public."{table}" ({cols}) VALUES ({marks}) RETURNING id'),
                        row).scalar_one()
