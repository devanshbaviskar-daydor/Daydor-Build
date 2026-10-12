"""Hire flow step 4: job-posting-publisher.

Publishes through a `daydor.adapters.job_board.JobBoardAdapter` (a fake today; see
docs/sprint-plan.md's adapter convention) and records the posting. "Pay-range check" in the
model's own step description is pay_range_min <= pay_range_max plus pay_transparency_checked --
anything more jurisdiction-specific is future work, not guessed at here.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Connection, text

from daydor.adapters.job_board import FakeJobBoardAdapter, JobBoardAdapter, JobPostingRequest
from daydor.queue.worker import Job


def publish_posting(conn: Connection, adapter: JobBoardAdapter, *, requisition_id: UUID, channel: str,
                    pay_range_min: Decimal, pay_range_max: Decimal) -> UUID:
    """Idempotent on requisition_id: a requisition is posted on one channel at a time here."""
    existing = conn.execute(text("SELECT id FROM job_posting WHERE requisition_id = :r"),
                            {"r": requisition_id}).scalar_one_or_none()
    if existing is not None:
        return existing
    if pay_range_min > pay_range_max:
        raise ValueError(f"invalid pay range: {pay_range_min} > {pay_range_max}")
    adapter.publish(JobPostingRequest(channel=channel, pay_range_min=float(pay_range_min),
                                      pay_range_max=float(pay_range_max)))
    return conn.execute(
        text("INSERT INTO job_posting (requisition_id, channel, pay_range_min, pay_range_max, "
             "pay_transparency_checked, posted_at) VALUES (:r, :c, :lo, :hi, true, now()) RETURNING id"),
        {"r": requisition_id, "c": channel, "lo": pay_range_min, "hi": pay_range_max},
    ).scalar_one()


def handle_job_posting_publisher(adapter: JobBoardAdapter | None = None):
    """Queue handler for kind 'job_posting_publisher' (hire flow step 4, queue 'ta').

    Takes no `engine`, unlike every other handler in this package: it does not fire "advance"
    itself. s04_job_posting is a genuine parked state (posting live, waiting for a candidate to
    apply), not a gate or an administrative step that completes on its own.
    daydor.hire.screening.submit_application is what moves the instance on, whenever that
    real-world event actually happens. (Sprint 1 had this handler auto-advance, since "done" was
    the very next state and nothing else needed to happen -- that stopped being correct the
    moment Sprint 2 extended the graph past it.)
    """
    adapter = adapter or FakeJobBoardAdapter()

    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        requisition_id = UUID(job.payload["subject_id"])
        posting_id = publish_posting(conn, adapter, requisition_id=requisition_id,
                                     channel=ctx["channel"], pay_range_min=Decimal(str(ctx["pay_range_min"])),
                                     pay_range_max=Decimal(str(ctx["pay_range_max"])))
        return {"job_posting_id": str(posting_id)}
    return handle
