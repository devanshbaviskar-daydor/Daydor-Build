"""Hire flow steps 5-6: candidate-screener. Covers both `application` (step 5) and
`screening_result` (step 6) -- the model names the same worker for both.

`score_application` is a deterministic placeholder, not a real screening tool: there is no model/
prompt/eval story yet (see `daydor.agents` for where that would plug in). It always reports
`requires_g_aedt=True` because it *is* an automated tool making a hiring recommendation, which is
exactly what g_aedt (notice + bias-audit currency) exists to catch -- a real tool would need the
same flag, for the same reason, whether or not its score method ever changes.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, text

from daydor.queue.worker import Job
from daydor.workflow.engine import WorkflowEngine

SCREENER_TOOL_NAME = "daydor-screener"
SCREENER_MODEL_VERSION = "v0"


def intake_application(conn: Connection, *, requisition_id: UUID, full_name: str, email: str,
                       phone: str, resume_ref: str, source: str) -> dict[str, UUID]:
    """Record the candidate and their application. Idempotent on (requisition_id, email): a
    candidate applying twice to the same requisition returns the existing application."""
    existing = conn.execute(
        text("SELECT a.id, a.candidate_id FROM application a JOIN candidate c ON c.id = a.candidate_id "
             "WHERE a.requisition_id = :r AND c.email = :e"),
        {"r": requisition_id, "e": email}).one_or_none()
    if existing is not None:
        return {"application_id": existing.id, "candidate_id": existing.candidate_id}

    candidate_id = conn.execute(
        text("INSERT INTO candidate (full_name, email, phone, resume_ref, source, retain_until) "
             "VALUES (:n, :e, :p, :r, :s, now()::date + interval '1 year') RETURNING id"),
        {"n": full_name, "e": email, "p": phone, "r": resume_ref, "s": source}).scalar_one()
    application_id = conn.execute(
        text("INSERT INTO application (candidate_id, requisition_id, stage, stage_changed_at) "
             "VALUES (:c, :r, 'applied', now()) RETURNING id"),
        {"c": candidate_id, "r": requisition_id}).scalar_one()
    return {"application_id": application_id, "candidate_id": candidate_id}


def score_application(conn: Connection, *, application_id: UUID) -> dict:
    """Idempotent on application_id: an application is screened once."""
    existing = conn.execute(text("SELECT id FROM screening_result WHERE application_id = :a"),
                            {"a": application_id}).scalar_one_or_none()
    if existing is not None:
        return {"screening_result_id": existing, "requires_g_aedt": True}
    screening_result_id = conn.execute(
        text("INSERT INTO screening_result (application_id, tool_name, model_version, score, "
             "recommendation, human_override) VALUES (:a, :t, :v, :s, 'advance', false) RETURNING id"),
        {"a": application_id, "t": SCREENER_TOOL_NAME, "v": SCREENER_MODEL_VERSION, "s": 0.75},
    ).scalar_one()
    return {"screening_result_id": screening_result_id, "requires_g_aedt": True}


def submit_application(conn: Connection, engine: WorkflowEngine, instance_id: UUID, *, full_name: str,
                       email: str, phone: str, resume_ref: str, source: str) -> None:
    """The real-world event that moves a hire instance out of s04_job_posting: a candidate
    applies. Patches the candidate's details into context and fires "advance", which enters
    s05_application and enqueues handle_candidate_screener_intake to actually write the rows."""
    engine.fire(conn, instance_id, "advance", context_patch={
        "full_name": full_name, "email": email, "phone": phone, "resume_ref": resume_ref,
        "source": source})


def handle_candidate_screener_intake(engine: WorkflowEngine):
    """Queue handler for kind 'candidate_screener_intake' (hire flow step 5, queue 'ta')."""
    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        requisition_id = UUID(job.payload["subject_id"])
        result = intake_application(conn, requisition_id=requisition_id, full_name=ctx["full_name"],
                                    email=ctx["email"], phone=ctx["phone"], resume_ref=ctx["resume_ref"],
                                    source=ctx["source"])
        engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}",
                   context_patch={"candidate_id": str(result["candidate_id"]),
                                  "application_id": str(result["application_id"])})
        return {k: str(v) for k, v in result.items()}
    return handle


def handle_candidate_screener_assess(engine: WorkflowEngine):
    """Queue handler for kind 'candidate_screener_assess' (hire flow step 6, queue 'ta')."""
    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        result = score_application(conn, application_id=UUID(ctx["application_id"]))
        engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}",
                   context_patch={"screening_result_id": str(result["screening_result_id"]),
                                  "requires_g_aedt": result["requires_g_aedt"]})
        return {"screening_result_id": str(result["screening_result_id"])}
    return handle
