"""Platform health for Daydor's own operators (backend 0046): aggregate numbers and alerts across tenants, no row content.
Daydor admin only; `/ops/metrics` is the same numbers in Prometheus text format for a scraper that holds an admin token."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import PlainTextResponse
from sqlalchemy import text

from ..deps import get_identity
from ..errors import ApiError
from ..identity import Identity
from ..sessions import human_session

router = APIRouter(prefix="/ops", tags=["ops"])


def _admin(ident: Identity) -> None:
    if ident.role != "daydor_admin":
        raise ApiError(403, "forbidden", "Platform health is for Daydor administrators.")


def _snapshot(ident: Identity) -> tuple[list[dict], list[dict]]:
    with human_session(ident) as conn:
        health = [dict(r) for r in conn.execute(text("SELECT * FROM app.ops_health()")).mappings().all()]
        alerts = [dict(r) for r in conn.execute(text("SELECT * FROM app.ops_alerts()")).mappings().all()]
    return jsonable_encoder(health), jsonable_encoder(alerts)


@router.get("/health")
def health(ident: Identity = Depends(get_identity)):
    _admin(ident)
    metrics, alerts = _snapshot(ident)
    return {"status": "alert" if any(a["severity"] == "critical" for a in alerts) else "ok", "alerts": alerts, "metrics": metrics}


def _label(v: object) -> str:
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


@router.get("/metrics", response_class=PlainTextResponse)
def metrics(ident: Identity = Depends(get_identity)):
    _admin(ident)
    rows, _ = _snapshot(ident)
    lines = []
    for r in rows:
        name = "daydor_" + re.sub(r"[^a-z0-9_]", "_", r["metric"])
        labels = ",".join(f'{k}="{_label(v)}"' for k, v in sorted((r["labels"] or {}).items()))
        lines.append(f"{name}{{{labels}}} {r['value']}" if labels else f"{name} {r['value']}")
    return "\n".join(lines) + "\n"
