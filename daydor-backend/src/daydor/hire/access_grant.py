"""Hire flow step 17: app-access-granter.

`access_role_template` is admin-entered reference data (IT admin writes it directly; see
docs/sprint-plan.md's "Reference & admin-owned data" note) -- this module only reads it.

`g_it_offtemplate` gates *leaving* s17_app_access_grant, not entering it (see
daydor.hire.workflow's module docstring): whether any requested access is off-template is only
known once this step's own work runs. The row for an off-template grant is still created
immediately, same as every other `requires_*` gate in this flow (g_aedt, g_offer_band,
g_bg_adverse) -- the gate blocks the *hire flow* from continuing, not the write itself; nothing
in `app.gate_guard` (migrations/sql/0006_gates.sql) guards `app_access_grant`, confirming that's
the model's own intent, not a gap this sprint papers over.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, text

from daydor.queue.worker import Job
from daydor.workflow.engine import WorkflowEngine


def grant_app_access(conn: Connection, *, identity_account_id: UUID, job_profile_id: UUID,
                     extra_access: list[dict] | None = None) -> dict:
    """Idempotent on identity_account_id: re-running does not duplicate grants already made.
    `extra_access` is a list of {"app_name", "permission_level"} not covered by the employee's
    access_role_template; each one is granted anyway (see module docstring) but flags
    requires_g_it_offtemplate so the hire flow pauses for IT to review."""
    existing = conn.execute(text("SELECT id FROM app_access_grant WHERE identity_account_id = :i"),
                            {"i": identity_account_id}).scalars().all()
    if existing:
        return {"grant_ids": existing, "requires_g_it_offtemplate": False}

    template = conn.execute(text("SELECT id, app_bundle FROM access_role_template "
                                 "WHERE job_profile_id = :j LIMIT 1"),
                            {"j": job_profile_id}).one_or_none()
    grant_ids = []
    if template is not None:
        for app in template.app_bundle:
            grant_ids.append(conn.execute(
                text("INSERT INTO app_access_grant (identity_account_id, app_name, permission_level, "
                     "source, template_id, granted_at) VALUES (:i, :a, :p, 'template', :t, now()) "
                     "RETURNING id"),
                {"i": identity_account_id, "a": app["app_name"], "p": app["permission_level"],
                 "t": template.id}).scalar_one())

    for app in (extra_access or []):
        grant_ids.append(conn.execute(
            text("INSERT INTO app_access_grant (identity_account_id, app_name, permission_level, "
                 "source, granted_at) VALUES (:i, :a, :p, 'manual', now()) RETURNING id"),
            {"i": identity_account_id, "a": app["app_name"], "p": app["permission_level"]}).scalar_one())

    return {"grant_ids": grant_ids, "requires_g_it_offtemplate": bool(extra_access)}


def handle_app_access_granter(engine: WorkflowEngine):
    """Queue handler for kind 'app_access_granter' (hire flow step 17, queue 'it')."""
    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        requisition_id = UUID(job.payload["subject_id"])
        job_profile_id = conn.execute(
            text("SELECT p.job_profile_id FROM job_requisition jr JOIN position p ON p.id = jr.position_id "
                 "WHERE jr.id = :r"), {"r": requisition_id}).scalar_one()
        result = grant_app_access(conn, identity_account_id=UUID(ctx["identity_account_id"]),
                                  job_profile_id=job_profile_id, extra_access=ctx.get("extra_access"))
        engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}",
                   context_patch={"requires_g_it_offtemplate": result["requires_g_it_offtemplate"]})
        return {"grant_ids": [str(g) for g in result["grant_ids"]]}
    return handle
