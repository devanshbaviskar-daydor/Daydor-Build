"""Hire flow step 9: background-check-initiator.

Gate placement (see daydor.hire.workflow's module docstring for the general rule): g_bg_adverse
guards *leaving* s09_background_check, not entering it -- whether it's needed depends on the
check's own result, which doesn't exist until this step's worker runs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import Connection, text

from daydor.adapters.background_check import BackgroundCheckAdapter, BackgroundCheckRequest, \
    FakeBackgroundCheckAdapter
from daydor.queue.worker import Job
from daydor.workflow.engine import WorkflowEngine


def order_background_check(conn: Connection, adapter: BackgroundCheckAdapter, *, candidate_id: UUID,
                           full_name: str, email: str, vendor: str = "fake-vendor") -> dict:
    """Idempotent on candidate_id: one check per candidate in this simplified flow."""
    existing = conn.execute(text("SELECT id, status FROM background_check WHERE candidate_id = :c"),
                            {"c": candidate_id}).one_or_none()
    if existing is not None:
        return {"background_check_id": existing.id, "requires_g_bg_adverse": existing.status == "adverse"}

    result = adapter.order(BackgroundCheckRequest(full_name=full_name, email=email))
    adverse = result.outcome == "adverse"
    now = datetime.now(timezone.utc)
    background_check_id = conn.execute(
        text("INSERT INTO background_check (candidate_id, vendor, ordered_at, status, "
             "adverse_action_stage, pre_adverse_notice_at) "
             "VALUES (:c, :v, :now, :s, :a, :n) RETURNING id"),
        {"c": candidate_id, "v": vendor, "now": now, "s": result.outcome,
         "a": "pre_adverse" if adverse else None, "n": now if adverse else None},
    ).scalar_one()
    return {"background_check_id": background_check_id, "requires_g_bg_adverse": adverse}


def handle_background_check_initiator(engine: WorkflowEngine, adapter: BackgroundCheckAdapter | None = None):
    """Queue handler for kind 'background_check_initiator' (hire flow step 9, queue 'ta')."""
    adapter = adapter or FakeBackgroundCheckAdapter()

    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        result = order_background_check(conn, adapter, candidate_id=UUID(ctx["candidate_id"]),
                                        full_name=ctx["full_name"], email=ctx["email"])
        engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}",
                   context_patch={"background_check_id": str(result["background_check_id"]),
                                  "requires_g_bg_adverse": result["requires_g_bg_adverse"]})
        return {k: str(v) for k, v in result.items()}
    return handle
