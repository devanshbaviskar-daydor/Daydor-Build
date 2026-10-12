"""Requisitions, their candidate pipeline, and application entry.

Everything is read as the caller's own role, table by table, so each role sees exactly the columns
the model grants it (masked roles read the masked views). A table the role cannot read is simply
left out of the answer, with `access` saying so, so the UI can explain instead of guessing."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from daydor.hire.consent import request_consent
from daydor.hire.screening import submit_application
from daydor.workflow.engine import WorkflowEngine, WorkflowError

from .. import access, idempotency
from ..deps import get_identity, idempotency_key
from ..errors import ApiError
from ..identity import WORKFLOW_READER_ROLES, Identity
from ..sessions import agent_session, human_session

router = APIRouter(prefix="/hire", tags=["hire"])
_ENGINE = WorkflowEngine()


def _qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def fetch(conn: Connection, ident: Identity, table: str, where: dict[str, Any] | None = None,
          keep: tuple[str, ...] | None = None) -> list[dict] | None:
    """Rows of one table as this role may read them, or None when the role cannot read the table.
    A list value means "any of"."""
    t = access.table_or_404(table)
    try:
        cols, relation = access.readable(t, ident)
    except ApiError:
        return None
    if keep:
        cols = [c for c in cols if c in keep or c == "id"]
    clauses, binds = [], {}
    for i, (col, val) in enumerate((where or {}).items()):
        if col not in cols and col not in {c.name for c in t.columns}:
            raise ValueError(col)
        if isinstance(val, (list, tuple, set)):
            if not val:
                return []
            clauses.append(f"{_qi(col)}::text = ANY(:w{i})"); binds[f"w{i}"] = [str(v) for v in val]
        else:
            clauses.append(f"{_qi(col)}::text = :w{i}"); binds[f"w{i}"] = str(val)
    sql = f'SELECT {", ".join(_qi(c) for c in cols)} FROM public.{_qi(relation)}'
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    return [dict(r) for r in conn.execute(text(sql), binds).mappings().all()]


def _by_id(rows: list[dict] | None) -> dict[str, dict]:
    return {str(r["id"]): r for r in (rows or [])}


def _approval_brief(a: dict | None) -> dict | None:
    return None if a is None else {"id": str(a["id"]), "status": a["status"], "gate_type": a["gate_type"]}


def derive_stage(approval: dict | None, posting: dict | None) -> str:
    """One plain stage for a requisition, from rows every role with requisition access can read."""
    if approval is None:
        return "drafting"
    if approval["status"] == "pending":
        return "awaiting_budget_approval"
    if approval["status"] in ("rejected", "expired"):
        return "budget_rejected"
    return "posted" if posting and posting.get("posted_at") else "approved"


def _context(conn: Connection, ident: Identity, reqs: list[dict]) -> dict:
    ids = [str(r["id"]) for r in reqs]
    positions = _by_id(fetch(conn, ident, "position", {"id": [r["position_id"] for r in reqs]}))
    depts = _by_id(fetch(conn, ident, "department", {"id": [p["department_id"] for p in positions.values()]}))
    profiles = _by_id(fetch(conn, ident, "job_profile", {"id": [p["job_profile_id"] for p in positions.values()]}))
    managers = _by_id(fetch(conn, ident, "employee", {"id": [r["hiring_manager_id"] for r in reqs]}, keep=("full_name",)))
    postings_raw = fetch(conn, ident, "job_posting", {"requisition_id": ids}) if ids else []
    postings = {str(p["requisition_id"]): p for p in (postings_raw or [])}
    approvals_raw = fetch(conn, ident, "approval_request", {"subject_table": "job_requisition", "subject_id": ids}) if ids else []
    approvals = {str(a["subject_id"]): a for a in sorted(approvals_raw or [], key=lambda a: a["created_at"])}
    apps_raw = fetch(conn, ident, "application", {"requisition_id": ids}) if ids else []
    return {"positions": positions, "departments": depts, "profiles": profiles, "managers": managers,
            "postings": postings, "approvals": approvals, "applications": apps_raw}


def _summary(r: dict, c: dict) -> dict:
    pos = c["positions"].get(str(r["position_id"]))
    dept = c["departments"].get(str(pos["department_id"])) if pos else None
    prof = c["profiles"].get(str(pos["job_profile_id"])) if pos else None
    mgr = c["managers"].get(str(r["hiring_manager_id"]))
    post = c["postings"].get(str(r["id"]))
    appr = c["approvals"].get(str(r["id"]))
    apps = [a for a in (c["applications"] or []) if str(a["requisition_id"]) == str(r["id"])]
    return {
        "id": str(r["id"]), "status": r["status"], "target_start_date": r["target_start_date"],
        "position_id": str(r["position_id"]), "hiring_manager_id": str(r["hiring_manager_id"]),
        "hiring_manager_name": mgr["full_name"] if mgr and "full_name" in mgr else None,
        "job_title": prof["title"] if prof else None, "department_name": dept["name"] if dept else None,
        "stage": derive_stage(appr, post), "approval": _approval_brief(appr),
        "posting": None if post is None else {k: post.get(k) for k in ("channel", "pay_range_min", "pay_range_max", "pay_transparency_checked", "posted_at")},
        "candidate_count": len(apps), "created_at": r.get("created_at"),
    }


@router.get("/requisitions")
def list_requisitions(ident: Identity = Depends(get_identity)):
    with human_session(ident) as conn:
        reqs = fetch(conn, ident, "job_requisition")
        if reqs is None:
            raise ApiError(403, "forbidden", "Your role does not have access to this.")
        ctx = _context(conn, ident, reqs)
    rows = [_summary(r, ctx) for r in reqs]
    rows.sort(key=lambda r: str(r["created_at"]), reverse=True)
    return {"requisitions": jsonable_encoder(rows)}


@router.get("/requisitions/{requisition_id}")
def get_requisition(requisition_id: str, ident: Identity = Depends(get_identity)):
    with human_session(ident) as conn:
        found = fetch(conn, ident, "job_requisition", {"id": requisition_id})
        if found is None:
            raise ApiError(403, "forbidden", "Your role does not have access to this.")
        if not found:
            raise ApiError(404, "not_found", "That requisition was not found.")
        ctx = _context(conn, ident, found)
        summary = _summary(found[0], ctx)
        applications = ctx["applications"]
        pipeline: list[dict] = []
        if applications:
            app_ids = [str(a["id"]) for a in applications]
            cands = _by_id(fetch(conn, ident, "candidate", {"id": [a["candidate_id"] for a in applications]},
                                 keep=("full_name", "email", "source")))
            screens = {str(s["application_id"]): s for s in (fetch(conn, ident, "screening_result", {"application_id": app_ids}) or [])}
            interviews = {str(i["application_id"]): i for i in (fetch(conn, ident, "interview", {"application_id": app_ids}) or [])}
            offers = {str(o["application_id"]): o for o in (fetch(conn, ident, "offer", {"application_id": app_ids}) or [])}
            bands = _by_id(fetch(conn, ident, "comp_band", {"id": [o["comp_band_id"] for o in offers.values()]}))
            interviewers = _by_id(fetch(conn, ident, "employee", {"id": [i["interviewer_employee_id"] for i in interviews.values()]}, keep=("full_name",)))
            # The backend raises every gate approval (budget, AEDT sign-off, offer band) against the
            # requisition, so match them to the screening and offer by gate type, newest first.
            raised = sorted(fetch(conn, ident, "approval_request", {"subject_id": [requisition_id]}) or [],
                            key=lambda a: a["created_at"])
            by_gate = {a["gate_type"]: a for a in raised}
            for a in applications:
                aid = str(a["id"])
                s, i, o = screens.get(aid), interviews.get(aid), offers.get(aid)
                band = bands.get(str(o["comp_band_id"])) if o else None
                pipeline.append({
                    "application": {k: a.get(k) for k in ("id", "stage", "stage_changed_at", "rejection_reason_code")},
                    "candidate": cands.get(str(a["candidate_id"])),
                    "screening": None if s is None else {**{k: s.get(k) for k in ("id", "score", "recommendation", "tool_name", "model_version", "candidate_notified_at", "human_override")}, "approval": _approval_brief(by_gate.get("g_aedt"))},
                    "interview": None if i is None else {**{k: i.get(k) for k in ("id", "scheduled_at", "interviewer_employee_id", "recommendation")},
                                                         "interviewer_name": (interviewers.get(str(i["interviewer_employee_id"])) or {}).get("full_name")},
                    "offer": None if o is None else {**{k: o.get(k) for k in ("id", "proposed_base", "proposed_equity", "within_band", "sent_at", "accepted_at")},
                                                     "band": None if band is None else {k: band.get(k) for k in ("currency", "band_min", "band_mid", "band_max")},
                                                     "approval": _approval_brief(by_gate.get("g_offer_band"))},
                })
        can_apply = access.table_level(access.table_or_404("application"), ident) >= 4
        sees_candidates = access.table_level(access.table_or_404("application"), ident) >= 2
        onboarding = None
        if ident.role in WORKFLOW_READER_ROLES:
            inst = conn.execute(text(
                "SELECT state, status, (context->>'employee_id')::uuid AS employee_id "
                "FROM app.workflow_instance WHERE definition_name = 'hire' "
                "AND subject_table = 'job_requisition' AND subject_id = :r "
                "ORDER BY created_at DESC LIMIT 1"), {"r": requisition_id}).first()
            if inst is not None and inst.employee_id is not None:
                onboarding = {
                    "employee_id": str(inst.employee_id), "instance_state": inst.state,
                    "instance_status": inst.status,
                    "awaiting_consent_request": inst.status == "running" and inst.state == "s12_consent_record",
                }
    return jsonable_encoder({"requisition": summary, "pipeline": pipeline, "onboarding": onboarding,
                             "access": {"can_enter_applications": can_apply, "sees_candidates": sees_candidates}})


class ApplyBody(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str = Field(min_length=3, max_length=40)
    resume_ref: str = "entered-by-hr"
    source: str = "hr_entry"


@router.post("/requisitions/{requisition_id}/applications", status_code=202)
def enter_application(requisition_id: UUID, body: ApplyBody, ident: Identity = Depends(get_identity),
                      key: str | None = Depends(idempotency_key)):
    if access.table_level(access.table_or_404("application"), ident) < 4:
        raise ApiError(403, "forbidden", "Your role cannot enter applications.")

    def run() -> dict:
        # The backend's trigger is a candidate applying; there is no apply page yet, so HR enters it.
        # Runs as agent_ta (workflow instances are agent-driven) with the person's user id attached.
        with agent_session(ident, "agent_ta") as conn:
            inst = conn.execute(text(
                "SELECT id, state, status FROM app.workflow_instance WHERE definition_name = 'hire' "
                "AND subject_table = 'job_requisition' AND subject_id = :r ORDER BY created_at DESC LIMIT 1"),
                {"r": requisition_id}).first()
            if inst is None:
                raise ApiError(404, "not_found", "No hire is in progress for that requisition.")
            # After the posting step the hire waits for an application; entering one is what moves it on.
            live = conn.execute(text("SELECT 1 FROM public.job_posting WHERE requisition_id = :r AND posted_at IS NOT NULL"),
                                {"r": requisition_id}).first()
            if inst.status != "running" or inst.state != "s04_job_posting" or live is None:
                raise ApiError(409, "not_accepting_applications",
                               "This requisition is not taking applications right now. It needs an approved budget and a live posting, and only one candidate can go through each hire.")
            try:
                submit_application(conn, _ENGINE, inst.id, full_name=body.full_name, email=body.email,
                                   phone=body.phone, resume_ref=body.resume_ref, source=body.source)
            except WorkflowError:
                raise ApiError(409, "not_accepting_applications", "This requisition is not taking applications right now.")
        return {"instance_id": str(inst.id), "status": "queued"}

    return idempotency.run(ident, f"POST /hire/requisitions/{requisition_id}/applications", key, run)


@router.post("/requisitions/{requisition_id}/request-consent", status_code=202)
def request_consent_approval(requisition_id: UUID, ident: Identity = Depends(get_identity),
                             key: str | None = Depends(idempotency_key)):
    """`consent_record` has no agent writer by design (daydor.hire.consent's docstring) -- the new
    hire grants it themselves, directly, through POST /tables/consent_record. Nothing in the hire
    flow watches for that, so HR (who is driving onboarding) tells the flow the new hire has done
    their part; this raises the dpdp_consent approval, which the employee then resolves themselves
    through the ordinary approvals flow, same mechanism as every other hard gate."""
    if ident.role != "tenant_hr":
        raise ApiError(403, "forbidden", "Only HR can request the new hire's consent sign-off.")

    def run() -> dict:
        # request_consent only fires a workflow transition; it runs as agent_hr like the backend's
        # own tests do, not an elevated role.
        with agent_session(ident, "agent_hr") as conn:
            inst = conn.execute(text(
                "SELECT id, state, status FROM app.workflow_instance WHERE definition_name = 'hire' "
                "AND subject_table = 'job_requisition' AND subject_id = :r ORDER BY created_at DESC LIMIT 1"),
                {"r": requisition_id}).first()
            if inst is None:
                raise ApiError(404, "not_found", "No hire is in progress for that requisition.")
            if inst.status == "waiting_gate":
                return {"instance_id": str(inst.id), "status": "already_requested"}
            if inst.status != "running" or inst.state != "s12_consent_record":
                raise ApiError(409, "not_ready_for_consent",
                               "This hire has not reached the consent step yet.")
            request_consent(conn, _ENGINE, inst.id)
        return {"instance_id": str(inst.id), "status": "requested"}

    return idempotency.run(ident, f"POST /hire/requisitions/{requisition_id}/request-consent", key, run)
