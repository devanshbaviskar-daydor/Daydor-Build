"""Hire flow step 8: offer-letter-generator.

`within_band` only checks proposed_base against comp_band.band_min/band_max (the effective-dated
version active "now"); it does not account for equity, currency conversion across locations, or
which comp_band row applies for effective-dated history -- a real compensation engine's job, not
this prototype's.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Connection, text

from daydor.queue.worker import Job
from daydor.workflow.engine import WorkflowEngine


class CompBandNotFound(RuntimeError):
    pass


def make_offer(conn: Connection, *, application_id: UUID, comp_band_id: UUID, proposed_base: Decimal,
              proposed_equity: Decimal | None = None) -> dict:
    """Idempotent on application_id: one offer per application in this simplified flow."""
    existing = conn.execute(text("SELECT id, within_band FROM offer WHERE application_id = :a"),
                            {"a": application_id}).one_or_none()
    if existing is not None:
        return {"offer_id": existing.id, "within_band": existing.within_band}

    band = conn.execute(text("SELECT band_min, band_max FROM comp_band WHERE id = :c"),
                        {"c": comp_band_id}).one_or_none()
    if band is None:
        raise CompBandNotFound(f"comp_band {comp_band_id} not found")
    within_band = band.band_min <= proposed_base <= band.band_max

    offer_id = conn.execute(
        text("INSERT INTO offer (application_id, comp_band_id, proposed_base, proposed_equity, "
             "within_band) VALUES (:a, :c, :b, :e, :w) RETURNING id"),
        {"a": application_id, "c": comp_band_id, "b": proposed_base, "e": proposed_equity,
         "w": within_band}).scalar_one()
    return {"offer_id": offer_id, "within_band": within_band}


def handle_offer_letter_generator(engine: WorkflowEngine):
    """Queue handler for kind 'offer_letter_generator' (hire flow step 8, queue 'ta')."""
    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        result = make_offer(conn, application_id=UUID(ctx["application_id"]),
                            comp_band_id=UUID(ctx["comp_band_id"]),
                            proposed_base=Decimal(str(ctx["proposed_base"])),
                            proposed_equity=Decimal(str(ctx["proposed_equity"])) if ctx.get("proposed_equity")
                            else None)
        engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}",
                   context_patch={"offer_id": str(result["offer_id"]),
                                  "requires_g_offer_band": not result["within_band"]})
        return {"offer_id": str(result["offer_id"]), "within_band": result["within_band"]}
    return handle
