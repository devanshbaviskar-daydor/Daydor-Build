"""Builds valid rows for any model table. Required non-FK columns get type-appropriate dummy
values; required FKs must be passed explicitly. Inserts run as the superuser fixture
connection (bypasses RLS) and are meant for test setup only."""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Connection, text

from daydor.model import load_model

DUMMY = {
    "uuid": lambda: str(uuid.uuid4()), "text": lambda: "x", "enum": lambda: "default",
    "jsonb": lambda: json.dumps({}), "numeric": lambda: 0, "date": lambda: date(2026, 1, 1),
    "ts": lambda: datetime(2026, 1, 1, tzinfo=timezone.utc), "bool": lambda: True,
    "int": lambda: 0, "bytea": lambda: b"\x00", "citext": lambda: f"{uuid.uuid4().hex[:8]}@example.com",
}
SKIP = {"id", "created_at", "updated_at"}


def insert(conn: Connection, table: str, **values) -> uuid.UUID:
    t = load_model().table(table)
    row = {}
    for c in t.columns:
        if c.name in SKIP:
            continue
        if c.name in values:
            row[c.name] = values[c.name]
        elif not c.nullable and c.name != "tenant_id":
            if c.fk:
                raise ValueError(f"{table}.{c.name} is a required FK; pass it explicitly")
            if c.unique and c.type in ("text", "enum"):
                row[c.name] = f"{c.name}-{uuid.uuid4().hex[:12]}"
            else:
                row[c.name] = DUMMY["bytea" if c.encrypted else c.type]()
    if "id" in values:
        row["id"] = values["id"]
    for k in values:
        if k not in row:
            raise KeyError(f"{table} has no column {k}")
    cols = ", ".join(row)
    params = ", ".join(f":{k}" for k in row)
    return conn.execute(text(f'INSERT INTO public."{table}" ({cols}) VALUES ({params}) RETURNING id'),
                        row).scalar_one()
