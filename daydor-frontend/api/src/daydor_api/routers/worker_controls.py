"""A tenant's controls over its workers (backend 0044): how closely each one is watched, and an off switch.

Autonomy runs auto < review < approve and a tenant can only be more careful than a worker's default, never less; the database refuses
anything else. For an LLM worker the response also shows its rollout stage in this tenant, which only Daydor can move forward."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from daydor.agents import rollout
from daydor.agents.runs import AUTONOMY_RANK, is_llm

from ..deps import get_identity
from ..errors import ApiError
from ..identity import Identity
from ..sessions import human_session

router = APIRouter(prefix="/worker-controls", tags=["worker-controls"])
CONTROL_ROLES = frozenset({"tenant_founder", "tenant_hr"})


class Control(BaseModel):
    autonomy: Literal["auto", "review", "approve"] | None = None      # None: the worker's default
    enabled: bool = True


def _shape(row: dict, stage: str | None) -> dict:
    allowed = [a for a, rank in AUTONOMY_RANK.items() if rank >= AUTONOMY_RANK[row["default_autonomy"]]]
    return {**row, "allowed_autonomy": allowed, "rollout_stage": stage}


@router.get("")
def list_controls(ident: Identity = Depends(get_identity)):
    if ident.role not in CONTROL_ROLES | {"daydor_ops"}:
        raise ApiError(403, "forbidden", "Only the founder or HR see how workers are set.")
    with human_session(ident) as conn:
        rows = [dict(r) for r in conn.execute(text("SELECT * FROM app.tenant_worker_controls()")).mappings().all()]
        out = [_shape(r, rollout.stage_for(conn, r["worker"]) if is_llm(r["worker"]) else None) for r in rows]
    return {"workers": out}


@router.put("/{worker}")
def set_control(worker: str, body: Control, ident: Identity = Depends(get_identity)):
    if ident.role not in CONTROL_ROLES:
        raise ApiError(403, "forbidden", "Only the founder or HR change how workers act.")
    with human_session(ident) as conn:
        known = conn.execute(text("SELECT 1 FROM app.tenant_worker_controls() WHERE worker = :w"), {"w": worker}).scalar_one_or_none()
        if known is None:
            raise ApiError(404, "not_found", "That worker was not found, or it cannot be changed.")
        default = conn.execute(text("SELECT default_autonomy FROM app.tenant_worker_controls() WHERE worker = :w"),
                               {"w": worker}).scalar_one()
        if body.autonomy and AUTONOMY_RANK[body.autonomy] < AUTONOMY_RANK[default]:
            raise ApiError(422, "autonomy_too_low", f"{worker} cannot act more freely than {default} for any tenant.")
        effective = conn.execute(text("SELECT app.set_worker_control(:w, :a, :e)"),
                                 {"w": worker, "a": body.autonomy, "e": body.enabled}).scalar_one()
    return {"worker": worker, "effective_autonomy": effective, "enabled": body.enabled}
