"""Provisions a new hire's own sign-in once their `employee` row exists (hire flow step 10).

Not a backend concern: `app_user`/`api.identity` are how a person signs in to this API, not
anything the hire flow itself needs. But the flow's own step 12 (consent) can only be resolved by
the employee themselves (the model's `dpdp_consent` gate names `E` as the sole approver), and the
flow's own identity-provisioning step (16, SSO) runs *after* consent -- so if sign-in waited for
that step, the new hire could never clear their own consent gate. Provisioning it here, at account
creation, is the API's own design choice to make step 12's self-resolution actually reachable; it
does not touch the backend's own `identity_account`/SSO step.

No role can write `app_user` from within a job (agents only ever get read access to it -- finding
3 in docs/model-findings.md, "all agents share one grant set"). `tenant_it` looks like the natural
human role (table_acl I: 4, same as real IT provisioning), but its actual column grant is
`INSERT (role, employee_id, is_active, mfa_enrolled, last_login_at)` -- no `email` -- so IT can
set someone's role and link but not choose their sign-in address. `tenant_founder` is the only
tenant-side role granted `INSERT (email, role, employee_id, ...)`; this runs as that role rather
than IT, a (column-grant-driven, not business-logic) choice worth another look once this is more
than a prototype. Switches role on the job's own connection and transaction (`SET LOCAL ROLE`,
scoped to the transaction, same mechanism `tenant_session` itself uses) rather than opening a
second one: the employee row the job just inserted is still uncommitted at this point, so a
separate transaction would not see it yet.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, text

from . import identity as idn


def provision_employee_signin(conn: Connection, *, tenant_id: UUID, employee_id: UUID) -> None:
    conn.exec_driver_sql('SET LOCAL ROLE "tenant_founder"')
    full_name, work_email = conn.execute(
        text("SELECT full_name, work_email FROM employee WHERE id = :e"), {"e": employee_id}).one()
    user_id = conn.execute(text(
        "INSERT INTO app_user (role, employee_id, email, is_active, mfa_enrolled) "
        "VALUES ('employee', :e, :em, true, false) "
        "ON CONFLICT (email) DO UPDATE SET employee_id = EXCLUDED.employee_id RETURNING id"),
        {"e": employee_id, "em": work_email}).scalar_one()
    tenant_name = conn.execute(text("SELECT legal_name FROM tenant WHERE id = app.tenant_id()")).scalar_one()
    idn.create(email=work_email, display_name=full_name, role="tenant_employee", tenant_id=tenant_id,
              tenant_name=tenant_name, user_id=user_id, employee_id=employee_id)
