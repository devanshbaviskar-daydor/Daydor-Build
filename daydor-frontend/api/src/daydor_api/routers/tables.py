"""Model-driven reads and writes. Which columns come back, and which can change, follows the
model's per-role access levels; the database enforces the same rules underneath."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text

from .. import access, idempotency
from ..deps import get_identity, idempotency_key
from ..errors import ApiError
from ..identity import Identity
from ..sessions import human_session

router = APIRouter(prefix="/tables", tags=["tables"])
RESERVED = {"limit", "offset", "order"}


def _qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _placeholder(t, col: str) -> str:
    """jsonb columns need an explicit cast: psycopg can't adapt a Python dict/list on its own,
    and a form (ModelForm) sends one, not a pre-serialized string."""
    return f"CAST(:{col} AS jsonb)" if t.column(col).type == "jsonb" else f":{col}"


def _bind(t, data: dict) -> dict:
    return {c: (json.dumps(v) if t.column(c).type == "jsonb" and not isinstance(v, str) else v)
            for c, v in data.items()}


@router.get("/{table}")
def list_rows(table: str, request: Request, ident: Identity = Depends(get_identity)):
    t = access.table_or_404(table)
    cols, relation = access.readable(t, ident)
    params = request.query_params
    limit = max(1, min(int(params.get("limit", 50)), 200))
    offset = max(0, int(params.get("offset", 0)))
    where, binds = [], {}
    for key, value in params.items():
        if key in RESERVED:
            continue
        if key.endswith("__in"):          # ?id__in=a,b,c  (at most 200 values)
            col = key[:-4]
            if col not in cols:
                raise ApiError(422, "invalid_filter", f"You cannot filter {table} by {col!r}.")
            where.append(f"{_qi(col)}::text = ANY(:f_{col}_in)")
            binds[f"f_{col}_in"] = [v for v in value.split(",") if v][:200]
            continue
        if key not in cols:
            raise ApiError(422, "invalid_filter", f"You cannot filter {table} by {key!r}.")
        where.append(f"{_qi(key)} = :f_{key}")
        binds[f"f_{key}"] = value
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    order = "created_at DESC, id" if "created_at" in cols else "id"
    select = ", ".join(_qi(c) for c in cols)
    with human_session(ident) as conn:
        rows = conn.execute(text(f"SELECT {select} FROM public.{_qi(relation)}{clause} "
                                 f"ORDER BY {order} LIMIT :limit OFFSET :offset"),
                            {**binds, "limit": limit, "offset": offset}).mappings().all()
        total = conn.execute(text(f"SELECT count(*) FROM public.{_qi(relation)}{clause}"), binds).scalar_one()
    return {"table": table, "columns": cols, "rows": jsonable_encoder([dict(r) for r in rows]),
            "total": total, "limit": limit, "offset": offset}


def _check_payload(payload: dict, allowed: list[str]) -> dict:
    unknown = sorted(set(payload) - set(allowed))
    if unknown:
        raise ApiError(422, "invalid_fields", "You cannot set: " + ", ".join(unknown))
    return payload


@router.post("/{table}", status_code=201)
def create_row(table: str, payload: dict, ident: Identity = Depends(get_identity),
               key: str | None = Depends(idempotency_key)):
    t = access.table_or_404(table)
    allowed = access.writable(t, ident)
    data = _check_payload(payload, allowed)
    if not data:
        raise ApiError(422, "invalid_request", "Send at least one field.")

    def run() -> dict:
        cols = ", ".join(_qi(c) for c in data)
        marks = ", ".join(_placeholder(t, c) for c in data)
        with human_session(ident) as conn:
            new_id = conn.execute(text(f"INSERT INTO public.{_qi(table)} ({cols}) VALUES ({marks}) RETURNING id"),
                                  _bind(t, data)).scalar_one()
        return {"table": table, "id": str(new_id)}

    return idempotency.run(ident, f"POST /tables/{table}", key, run)


@router.patch("/{table}/{row_id}")
def update_row(table: str, row_id: str, payload: dict, ident: Identity = Depends(get_identity)):
    t = access.table_or_404(table)
    allowed = access.writable(t, ident)
    data = _check_payload(payload, allowed)
    if not data:
        raise ApiError(422, "invalid_request", "Send at least one field.")
    sets = ", ".join(f"{_qi(c)} = {_placeholder(t, c)}" for c in data)
    with human_session(ident) as conn:
        found = conn.execute(text(f"UPDATE public.{_qi(table)} SET {sets} WHERE id = :_id RETURNING id"),
                             {**_bind(t, data), "_id": row_id}).first()
    if found is None:
        raise ApiError(404, "not_found", "That record was not found.")
    return {"table": table, "id": str(found[0])}
