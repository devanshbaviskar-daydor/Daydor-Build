"""One list of what needs this person's attention (backend 0044, app.inbox): approvals their role may decide, agent runs waiting for
their review, and notifications. Reading is by the person's own role; acting is the gate's or the run's own endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text

from ..deps import get_identity
from ..errors import ApiError
from ..identity import Identity
from ..sessions import human_session

router = APIRouter(prefix="/inbox", tags=["inbox"])
INBOX_ROLES = frozenset({"tenant_founder", "tenant_hr", "tenant_payroll", "tenant_it", "daydor_ops"})


def _need_inbox(ident: Identity) -> None:
    if ident.role not in INBOX_ROLES:
        raise ApiError(403, "forbidden", "Your role has no inbox.")


@router.get("")
def list_inbox(ident: Identity = Depends(get_identity)):
    _need_inbox(ident)
    with human_session(ident) as conn:
        rows = conn.execute(text("SELECT * FROM app.inbox()")).mappings().all()
    items = jsonable_encoder([dict(r) for r in rows])
    return {"items": items, "counts": {k: sum(1 for i in items if i["kind"] == k) for k in ("approval", "review", "notification")}}


@router.post("/reviews/{run_id}/acknowledge")
def acknowledge(run_id: str, ident: Identity = Depends(get_identity)):
    """The person looked at what the worker did and accepts it: the jobs it held for review are released."""
    _need_inbox(ident)
    with human_session(ident) as conn:
        conn.execute(text("SELECT app.acknowledge_agent_run(:r)"), {"r": run_id})
    return {"id": run_id, "status": "acknowledged"}


@router.post("/reviews/{run_id}/reject")
def reject(run_id: str, ident: Identity = Depends(get_identity)):
    """The person does not accept it: what the run set in motion is cancelled. Undoing its own writes is the person's job."""
    _need_inbox(ident)
    with human_session(ident) as conn:
        cancelled = conn.execute(text("SELECT app.reject_agent_run(:r)"), {"r": run_id}).scalar_one()
    return {"id": run_id, "status": "rejected", "cancelled_jobs": cancelled}


@router.post("/notifications/{notification_id}/dismiss")
def dismiss(notification_id: str, ident: Identity = Depends(get_identity)):
    _need_inbox(ident)
    with human_session(ident) as conn:
        conn.execute(text("SELECT app.dismiss_notification(:n)"), {"n": notification_id})
    return {"id": notification_id, "status": "dismissed"}
