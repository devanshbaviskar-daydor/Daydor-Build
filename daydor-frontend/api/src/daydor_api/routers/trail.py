"""Audit trail and automated pre-check results for one subject.

The backend's own audit_log only records data-access events (consent, decrypt), so the trail for a
record is assembled from every source the caller's role may read: approval requests, workflow
transitions and audit_log rows. Nothing here is a new fact; it is the same rows, put in time order."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text

from .. import access
from ..deps import get_identity
from ..errors import ApiError
from ..gates import by_id
from ..identity import NAME_VISIBLE_ROLES, WORKFLOW_READER_ROLES, Identity, display_names
from ..sessions import human_session

router = APIRouter(tags=["trail"])

_STATE = lambda s: (s[4:] if s[:1] == "s" and s[1:3].isdigit() and s[3:4] == "_" else s).replace("_", " ")  # noqa: E731


def _role_label(role: str) -> str:
    from daydor.model.loader import ROLE_DB
    names = {r["id"]: r["name"] for r in access.model().roles}
    letter = {v: k for k, v in ROLE_DB.items()}.get(role)
    return names.get(letter, "Agent") if letter and letter != "G" else "Agent"


def _actor(ident: Identity, user_id, names: dict[str, str], fallback: str) -> str:
    if user_id is not None and ident.user_id is not None and str(user_id) == str(ident.user_id):
        return "You"
    if user_id is not None:
        return names.get(str(user_id)) or "A person"
    return fallback


@router.get("/audit/subject")
def subject_trail(table: str, id: str, ident: Identity = Depends(get_identity)):
    entries: list[dict] = []
    users: list = []
    with human_session(ident) as conn:
        approvals = []
        if access.table_level(access.table_or_404("approval_request"), ident) >= 2:
            approvals = conn.execute(text(
                "SELECT id, gate_type, status, requested_by_user_id, resolved_by_user_id, resolved_at, "
                "decision_note, created_at FROM approval_request WHERE subject_table = :t AND subject_id = :i"),
                {"t": table, "i": id}).mappings().all()
        transitions, instances = [], []
        if ident.role in WORKFLOW_READER_ROLES:
            instances = conn.execute(text("SELECT id FROM app.workflow_instance WHERE subject_table = :t "
                                          "AND subject_id = :i"), {"t": table, "i": id}).scalars().all()
            if instances:
                transitions = conn.execute(text(
                    "SELECT id, instance_id, event, from_state, to_state, outcome, actor_role, actor_user_id, created_at "
                    "FROM app.workflow_transition WHERE instance_id = ANY(CAST(:ids AS uuid[]))"),
                    {"ids": [str(i) for i in instances]}).mappings().all()
        logged = []
        audit_table = access.table_or_404("audit_log")
        if access.table_level(audit_table, ident) >= 2:
            cols, relation = access.readable(audit_table, ident)
            want = [c for c in ("id", "actor_user_id", "actor_kind", "event_type", "occurred_at") if c in cols]
            if "occurred_at" in want and "event_type" in want:
                logged = conn.execute(text(f'SELECT {", ".join(want)} FROM public."{relation}" '
                                           "WHERE subject_table = :t AND subject_id = :i"), {"t": table, "i": id}).mappings().all()

    if ident.role in NAME_VISIBLE_ROLES:
        users = [a["requested_by_user_id"] for a in approvals] + [a["resolved_by_user_id"] for a in approvals] \
            + [t["actor_user_id"] for t in transitions] + [r.get("actor_user_id") for r in logged]
    names = display_names(users) if users else {}

    gates = by_id()
    for a in approvals:
        label = gates.get(a["gate_type"], {}).get("label", a["gate_type"])
        entries.append({"id": f"ap-{a['id']}-req", "at": a["created_at"], "kind": "approval_requested",
                        "actor": _actor(ident, a["requested_by_user_id"], names, "An agent"),
                        "action": f"Asked for approval: {label}"})
        if a["resolved_at"]:
            verb = {"approved": "Approved", "rejected": "Rejected"}.get(a["status"], a["status"].capitalize())
            note = f" Note: {a['decision_note']}" if a["decision_note"] else ""
            entries.append({"id": f"ap-{a['id']}-res", "at": a["resolved_at"], "kind": "approval_resolved",
                            "actor": _actor(ident, a["resolved_by_user_id"], names, "A person"),
                            "action": f"{verb}: {label}.{note}"})
    for t in transitions:
        phrase = {"moved": f"Moved from {_STATE(t['from_state'])} to {_STATE(t['to_state'])}",
                  "waiting_gate": f"Paused at {_STATE(t['from_state'])}, waiting for approval",
                  "rejected": f"Approval rejected at {_STATE(t['from_state'])}"}.get(t["outcome"], t["event"])
        entries.append({"id": f"wf-{t['id']}", "at": t["created_at"], "kind": "workflow",
                        "actor": _actor(ident, t["actor_user_id"], names, _role_label(t["actor_role"])),
                        "action": phrase})
    for r in logged:
        entries.append({"id": f"al-{r['id']}", "at": r["occurred_at"], "kind": "data_access",
                        "actor": _actor(ident, r.get("actor_user_id"), names, "An agent" if r.get("actor_kind") == "agent" else "A person"),
                        "action": f"Data access: {str(r['event_type']).replace('_', ' ')}"})
    entries.sort(key=lambda e: (e["at"], e["id"]))
    return {"table": table, "subject_id": id, "entries": jsonable_encoder(entries),
            "sources": {"approvals": bool(approvals) or access.table_level(access.table_or_404("approval_request"), ident) >= 2,
                        "workflow": ident.role in WORKFLOW_READER_ROLES,
                        "audit_log": access.table_level(access.table_or_404("audit_log"), ident) >= 2}}


@router.get("/evaluations")
def evaluations(approval_id: str | None = None, subject_table: str | None = None, subject_id: str | None = None,
                gate: str | None = None, limit: int = Query(default=50, le=200),
                ident: Identity = Depends(get_identity)):
    if ident.role not in WORKFLOW_READER_ROLES:
        raise ApiError(403, "evaluation_not_visible", "Your role cannot see automated pre-check results.")
    where, binds = [], {"limit": limit}
    for col, val in (("approval_request_id", approval_id), ("subject_table", subject_table),
                     ("subject_id", subject_id), ("gate_id", gate)):
        if val:
            where.append(f"{col} = :{col}"); binds[col] = val
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with human_session(ident) as conn:
        rows = conn.execute(text(
            "SELECT id, gate_id, subject_table, subject_id, engine, engine_version, confidence, threshold, "
            "model_decision, effective_decision, mode, error, approval_request_id, created_at "
            f"FROM app.gate_evaluation{clause} ORDER BY created_at DESC LIMIT :limit"), binds).mappings().all()
    gates = by_id()
    return {"evaluations": [jsonable_encoder({**r, "gate_label": gates.get(r["gate_id"], {}).get("label", r["gate_id"])})
                            for r in rows]}
