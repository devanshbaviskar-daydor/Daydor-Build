-- Finding 6: "Daydor ops sees assigned tenants only" is enforced in the database.
--
-- Until now the app server set the tenant for a daydor_ops session and nothing checked that this person was
-- assigned to it. app.tenant_id() is what every row-security policy, column default and tenant-filtered function
-- reads, so the check lives there: for a daydor_ops session it returns the session's tenant only if the signed-in
-- user holds an active assignment to it, and NULL otherwise (so every tenant policy sees nothing and every insert
-- default fails). Other roles are unaffected. A daydor_ops session with no tenant is a platform-level session and is
-- unaffected too; with a tenant but no user, it sees nothing.
--
-- daydor_admin assigns and revokes. Assignments are never deleted: revoking sets revoked_at.

SET ROLE daydor_schema_owner;

CREATE TABLE app.ops_tenant_assignment (
    user_id     uuid NOT NULL REFERENCES public.app_user (id),
    tenant_id   uuid NOT NULL REFERENCES public.tenant (id),
    granted_by  uuid REFERENCES public.app_user (id),
    granted_at  timestamptz NOT NULL DEFAULT now(),
    revoked_at  timestamptz,
    PRIMARY KEY (user_id, tenant_id)
);
GRANT SELECT ON app.ops_tenant_assignment TO daydor_admin, daydor_ops;
GRANT INSERT (user_id, tenant_id, granted_by), UPDATE (revoked_at) ON app.ops_tenant_assignment TO daydor_admin;

-- SECURITY DEFINER so the check does not depend on the caller's own grants on the table.
CREATE FUNCTION app.ops_assigned(p_tenant uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, pg_temp AS $$
    SELECT EXISTS (SELECT 1 FROM app.ops_tenant_assignment a
                   WHERE a.user_id = app.user_id() AND a.tenant_id = p_tenant AND a.revoked_at IS NULL)
$$;

CREATE OR REPLACE FUNCTION app.tenant_id() RETURNS uuid
LANGUAGE sql STABLE AS $$
    SELECT CASE WHEN t IS NOT NULL AND app.current_app_role() = 'daydor_ops' AND NOT app.ops_assigned(t)
                THEN NULL ELSE t END
    FROM (SELECT app.setting_uuid('app.tenant_id') AS t) s
$$;

-- Everyone who can call app.tenant_id() reaches ops_assigned through it.
GRANT EXECUTE ON FUNCTION app.ops_assigned(uuid)
    TO daydor_admin, daydor_ops, tenant_founder, tenant_hr, tenant_payroll, tenant_it, tenant_manager,
       tenant_employee, external_auditor, agent_runtime, daydor_worker, daydor_system, worker_platform;

RESET ROLE;
