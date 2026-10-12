from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text

from .. import enums
from ..deps import get_identity
from ..errors import ApiError
from ..gates import catalog
from ..identity import WORKFLOW_READER_ROLES, Identity
from ..sessions import human_session

router = APIRouter(prefix="/meta", tags=["meta"])
WORKFLOW_READERS = WORKFLOW_READER_ROLES


@router.get("/enums")
def get_enums(_: Identity = Depends(get_identity)):
    return enums.load()


@router.get("/gates")
def get_gates(_: Identity = Depends(get_identity)):
    return {"gates": catalog()}


@router.get("/workflows/{name}")
def workflow_definition(name: str, ident: Identity = Depends(get_identity)):
    if ident.role not in WORKFLOW_READERS:
        raise ApiError(403, "workflow_not_visible", "Your role cannot read workflow definitions.")
    with human_session(ident) as conn:
        row = conn.execute(text("SELECT name, version, definition FROM app.workflow_definition "
                                "WHERE name = :n AND active"), {"n": name}).first()
    if row is None:
        raise ApiError(404, "not_found", "No active workflow has that name.")
    return {"name": row.name, "version": row.version, "definition": row.definition}
