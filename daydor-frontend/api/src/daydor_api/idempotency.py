"""Every command carries an Idempotency-Key. A replay returns the first response."""
from __future__ import annotations

import json
from typing import Callable

from fastapi.encoders import jsonable_encoder
from sqlalchemy import text

from .identity import Identity
from .state import get_engine


def run(ident: Identity, route: str, key: str | None, fn: Callable[[], dict]) -> dict:
    if not key:
        return fn()
    with get_engine().begin() as conn:
        row = conn.execute(text("SELECT response FROM api.idempotency WHERE identity_id = :i AND route = :r "
                                "AND key = :k"), {"i": ident.id, "r": route, "k": key}).first()
    if row:
        return {**row[0], "replayed": True}
    result = jsonable_encoder(fn())
    with get_engine().begin() as conn:
        conn.execute(text("INSERT INTO api.idempotency (identity_id, route, key, response) "
                          "VALUES (:i, :r, :k, CAST(:v AS jsonb)) ON CONFLICT DO NOTHING"),
                     {"i": ident.id, "r": route, "k": key, "v": json.dumps(result)})
    return result
