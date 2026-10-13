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

from daydor.gates.decider import Choice, DeciderClient, DeciderResult, DecisionSchema, LayaClient
from daydor.gates.soft import SoftGate, run_soft_gate
from daydor.queue.worker import Job
from daydor.workflow.engine import WorkflowEngine

SCHEMA = DecisionSchema("access_request", "1", (Choice(
    "request_looks", "Is this app and permission level normal for someone in this job?",
    {"consistent": "the app and permission level are normal for this job title",
     "inconsistent": "the app or permission level is unusual for this job title"}),))


def _grant_state(conn: Connection, grant_id: UUID) -> dict:
    row = conn.execute(
        text("SELECT ag.app_name, ag.permission_level, jp.title AS job_title FROM app_access_grant ag "
             "JOIN identity_account ia ON ia.id = ag.identity_account_id "
             "JOIN employee e ON e.id = ia.employee_id "
             "JOIN position p ON p.id = e.position_id JOIN job_profile jp ON jp.id = p.job_profile_id "
             "WHERE ag.id = :g"), {"g": grant_id}).one()
    return {"app_name": row.app_name, "permission_level": row.permission_level, "title": row.job_title}


def _pass_if_consistent(result: DeciderResult) -> tuple[bool, float]:
    answer = result.answers["request_looks"]
    return answer.value == "consistent", answer.confidence


ACCESS_REQUEST_GATE = SoftGate(
    "sg_access_request_precheck", SCHEMA,
    ("app_access_grant.app_name", "app_access_grant.permission_level", "job_profile.title"),
    _grant_state, _pass_if_consistent)


def grant_app_access(conn: Connection, *, identity_account_id: UUID, job_profile_id: UUID,
                     extra_access: list[dict] | None = None, decider: DeciderClient | None = None) -> dict:
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

    # Each off-template grant is pre-checked by sg_access_request_precheck. The gate is asked not to
    # open IT's approval itself: the hire flow opens g_it_offtemplate on leaving this step, so one
    # escalation stays one approval. While the gate is in shadow mode (or the decider errors) it always
    # escalates, so IT still reviews every off-template grant; once it enforces, a confident
    # "consistent" skips the review.
    escalate = False
    for app in (extra_access or []):
        grant_id = conn.execute(
            text("INSERT INTO app_access_grant (identity_account_id, app_name, permission_level, "
                 "source, granted_at) VALUES (:i, :a, :p, 'manual', now()) RETURNING id"),
            {"i": identity_account_id, "a": app["app_name"], "p": app["permission_level"]}).scalar_one()
        grant_ids.append(grant_id)
        outcome = run_soft_gate(conn, ACCESS_REQUEST_GATE, "app_access_grant", grant_id,
                                decider or LayaClient(), open_approval=False)
        escalate = escalate or outcome.effective_decision == "escalate"

    return {"grant_ids": grant_ids, "requires_g_it_offtemplate": escalate}


def handle_app_access_granter(engine: WorkflowEngine):
    """Queue handler for kind 'app_access_granter' (hire flow step 17, queue 'it')."""
    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        requisition_id = UUID(job.payload["subject_id"])
        job_profile_id = conn.execute(
            text("SELECT p.job_profile_id FROM job_requisition jr JOIN position p ON p.id = jr.position_id "
                 "WHERE jr.id = :r"), {"r": requisition_id}).scalar_one()
        result = grant_app_access(conn, identity_account_id=UUID(ctx["identity_account_id"]),
                                  job_profile_id=job_profile_id, extra_access=ctx.get("extra_access"),
                                  decider=engine.decider)
        engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}",
                   context_patch={"requires_g_it_offtemplate": result["requires_g_it_offtemplate"]})
        return {"grant_ids": [str(g) for g in result["grant_ids"]]}
    return handle
