"""Hire flow step 16: sso-identity-provisioner."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, text

from daydor.adapters.idp import FakeIdPAdapter, IdentityProvisionRequest, IdPAdapter
from daydor.queue.worker import Job
from daydor.workflow.engine import WorkflowEngine


def provision_identity(conn: Connection, adapter: IdPAdapter, *, employee_id: UUID) -> UUID:
    """Idempotent on employee_id: one directory identity per employee in this simplified flow."""
    existing = conn.execute(text("SELECT id FROM identity_account WHERE employee_id = :e"),
                            {"e": employee_id}).scalar_one_or_none()
    if existing is not None:
        return existing

    work_email = conn.execute(text("SELECT work_email FROM employee WHERE id = :e"),
                              {"e": employee_id}).scalar_one()
    result = adapter.provision(IdentityProvisionRequest(work_email=work_email))
    return conn.execute(
        text("INSERT INTO identity_account (employee_id, directory_provider, external_id, status, "
             "provisioned_at) VALUES (:e, :p, :x, 'active', now()) RETURNING id"),
        {"e": employee_id, "p": result.directory_provider, "x": result.external_id}).scalar_one()


def handle_sso_identity_provisioner(engine: WorkflowEngine, adapter: IdPAdapter | None = None):
    """Queue handler for kind 'sso_identity_provisioner' (hire flow step 16, queue 'it')."""
    adapter = adapter or FakeIdPAdapter()

    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        identity_account_id = provision_identity(conn, adapter, employee_id=UUID(ctx["employee_id"]))
        engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}",
                   context_patch={"identity_account_id": str(identity_account_id)})
        return {"identity_account_id": str(identity_account_id)}
    return handle
