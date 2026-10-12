from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy import text

from daydor.gates import hard

from .. import access
from ..deps import get_identity
from ..errors import ApiError
from ..gates import by_id
from ..identity import WORKFLOW_READER_ROLES, Identity
from ..sessions import human_session

router = APIRouter(prefix="/approvals", tags=["approvals"])

_COLS = ("id, gate_type, subject_table, subject_id, required_approver_role, status, requested_by_user_id, "
         "resolved_by_user_id, resolved_at, deadline_at, decision_note, created_at")


class Resolve(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = None


def _shape(row: dict, ident: Identity) -> dict:
    gate = by_id().get(row["gate_type"], {})
    allowed = gate.get("approver_roles") or ([row["required_approver_role"]] if row["required_approver_role"] else [])
    mine = ident.user_id is not None and row.get("requested_by_user_id") == ident.user_id
    row = jsonable_encoder(row)
    return {
        **row, "gate_label": gate.get("label", row["gate_type"]), "allowed_roles": allowed,
        "requested_by_me": mine,
        "can_resolve": row["status"] == "pending" and ident.role in allowed and not mine,
    }


@router.get("")
def list_approvals(status: str | None = Query(default=None), gate: str | None = None,
                   subject_table: str | None = None, subject_id: str | None = None,
                   limit: int = Query(default=50, le=200), offset: int = 0,
                   ident: Identity = Depends(get_identity)):
    access.readable(access.table_or_404("approval_request"), ident)
    where, binds = [], {"limit": limit, "offset": offset}
    if status:
        where.append("status = :status"); binds["status"] = status
    if gate:
        where.append("gate_type = :gate"); binds["gate"] = gate
    if subject_table:
        where.append("subject_table = :subject_table"); binds["subject_table"] = subject_table
    if subject_id:
        where.append("subject_id = :subject_id"); binds["subject_id"] = subject_id
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with human_session(ident) as conn:
        rows = conn.execute(text(f"SELECT {_COLS} FROM approval_request{clause} "
                                 "ORDER BY created_at DESC, id LIMIT :limit OFFSET :offset"), binds).mappings().all()
    return {"approvals": [_shape(dict(r), ident) for r in rows]}


@router.get("/{approval_id}")
def get_approval(approval_id: str, ident: Identity = Depends(get_identity)):
    with human_session(ident) as conn:
        row = conn.execute(text(f"SELECT {_COLS} FROM approval_request WHERE id = :i"),
                           {"i": approval_id}).mappings().first()
        if row is None:
            raise ApiError(404, "not_found", "That request was not found.")
        # Only the roles that may read workflow tables are told which workflow this belongs to.
        wf = None
        if ident.role in WORKFLOW_READER_ROLES:
            wf = conn.execute(text("SELECT id FROM app.workflow_instance WHERE waiting_on_approval = :a "
                                   "OR (subject_table = :t AND subject_id = :s) ORDER BY created_at DESC LIMIT 1"),
                              {"a": approval_id, "t": row["subject_table"], "s": row["subject_id"]}).scalar_one_or_none()
    return {**_shape(dict(row), ident), "workflow_instance_id": str(wf) if wf else None}


@router.post("/{approval_id}/resolve")
def resolve(approval_id: str, body: Resolve, ident: Identity = Depends(get_identity)):
    with human_session(ident) as conn:
        status = hard.resolve(conn, approval_id, body.decision, body.note)
    return {"id": approval_id, "status": status}
