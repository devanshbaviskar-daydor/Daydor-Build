"""Hire flow step 13: new-hire-doc-collector.

storage_ref is a synthetic reference, not a real upload: document storage is data plumbing, not
an external vendor boundary worth an adapter (contrast with daydor.adapters.job_board/
background_check, which stand in for a real vendor this prototype doesn't talk to).
`retention_class` (despite the name, a `retention_policy` id) is admin-entered reference data
(see docs/sprint-plan.md's "Reference & admin-owned data" note) and supplied via context, not
computed here.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, text

from daydor.queue.worker import Job
from daydor.workflow.engine import WorkflowEngine

DOCUMENT_CLASSES = ("id_proof", "offer_letter")


def collect_new_hire_documents(conn: Connection, *, employee_id: UUID, retention_class_id: UUID) -> list[UUID]:
    """Idempotent per (employee_id, document_class): re-running does not duplicate a document."""
    ids = []
    for document_class in DOCUMENT_CLASSES:
        existing = conn.execute(
            text("SELECT id FROM document WHERE subject_type = 'employee' AND subject_id = :e "
                 "AND document_class = :d"), {"e": employee_id, "d": document_class}).scalar_one_or_none()
        if existing is not None:
            ids.append(existing)
            continue
        ids.append(conn.execute(
            text("INSERT INTO document (subject_type, subject_id, document_class, storage_ref, "
                 "retention_class) VALUES ('employee', :e, :d, :s, :r) RETURNING id"),
            {"e": employee_id, "d": document_class, "s": f"mock-storage/employee/{employee_id}/{document_class}",
             "r": retention_class_id}).scalar_one())
    return ids


def handle_new_hire_doc_collector(engine: WorkflowEngine):
    """Queue handler for kind 'new_hire_doc_collector' (hire flow step 13, queue 'privacy' --
    domain 'priv' maps to queue name 'privacy', per daydor.workflow.definitions.DOMAIN_QUEUE)."""
    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        document_ids = collect_new_hire_documents(conn, employee_id=UUID(ctx["employee_id"]),
                                                  retention_class_id=UUID(ctx["retention_class_id"]))
        engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}")
        return {"document_ids": [str(d) for d in document_ids]}
    return handle
