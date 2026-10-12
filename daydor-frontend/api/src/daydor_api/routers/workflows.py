from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text

from .. import access
from ..deps import get_identity
from ..errors import ApiError
from ..identity import Identity
from ..routers.meta import WORKFLOW_READERS
from ..sessions import human_session

router = APIRouter(prefix="/workflows", tags=["workflows"])

_INSTANCE = ("id, definition_name, definition_version, subject_table, subject_id, state, status, "
             "waiting_on_approval, context, version, created_at, updated_at")


def _require_reader(ident: Identity) -> None:
    if ident.role not in WORKFLOW_READERS:
        raise ApiError(403, "workflow_not_visible",
                       "Your role cannot see workflow timelines. Open the approval to see its status.")


def _shape(row: dict) -> dict:
    ctx, hidden = access.safe_context(row.get("context"))
    return jsonable_encoder({**row, "context": ctx, "context_hidden_keys": hidden})


@router.get("/instances")
def list_instances(status: str | None = None, subject_table: str | None = None, subject_id: str | None = None,
                   limit: int = Query(default=50, le=200), offset: int = 0,
                   ident: Identity = Depends(get_identity)):
    _require_reader(ident)
    where, binds = [], {"limit": limit, "offset": offset}
    for col, val in (("status", status), ("subject_table", subject_table), ("subject_id", subject_id)):
        if val:
            where.append(f"{col} = :{col}"); binds[col] = val
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with human_session(ident) as conn:
        rows = conn.execute(text(f"SELECT {_INSTANCE} FROM app.workflow_instance{clause} "
                                 "ORDER BY updated_at DESC, id LIMIT :limit OFFSET :offset"), binds).mappings().all()
    return {"instances": [_shape(dict(r)) for r in rows]}


@router.get("/instances/{instance_id}")
def get_instance(instance_id: str, ident: Identity = Depends(get_identity)):
    _require_reader(ident)
    with human_session(ident) as conn:
        inst = conn.execute(text(f"SELECT {_INSTANCE} FROM app.workflow_instance WHERE id = :i"),
                            {"i": instance_id}).mappings().first()
        if inst is None:
            raise ApiError(404, "not_found", "That workflow was not found.")
        transitions = conn.execute(text(
            "SELECT id, event, from_state, to_state, outcome, approval_request_id, actor_role, actor_user_id, "
            "agent_task_run_id, created_at FROM app.workflow_transition WHERE instance_id = :i ORDER BY id"),
            {"i": instance_id}).mappings().all()
        definition = conn.execute(text("SELECT definition FROM app.workflow_definition WHERE name = :n AND version = :v"),
                                  {"n": inst["definition_name"], "v": inst["definition_version"]}).scalar_one_or_none()
    return {"instance": _shape(dict(inst)), "transitions": jsonable_encoder([dict(t) for t in transitions]),
            "definition": definition}
