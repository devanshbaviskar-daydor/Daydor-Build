-- Platform foundation: extensions, roles, the app schema and session-context functions.
-- Runs as a superuser (extensions and roles need it). Everything else runs as
-- daydor_schema_owner so that FORCE ROW LEVEL SECURITY applies to the owner too.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

-- ---------------------------------------------------------------------------
-- Roles (cluster-wide, so created idempotently)
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    r text;
BEGIN
    FOREACH r IN ARRAY ARRAY[
        'daydor_schema_owner',                       -- owns every object; not a superuser
        'daydor_admin', 'daydor_ops',                -- platform tier
        'tenant_founder', 'tenant_hr', 'tenant_payroll', 'tenant_it',
        'tenant_manager', 'tenant_employee',
        'external_auditor',
        'agent_runtime',                             -- group role carrying agent grants
        'daydor_worker'                              -- queue dispatcher / relay / scheduler
    ] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('CREATE ROLE %I NOLOGIN', r);
        END IF;
    END LOOP;

    -- One role per domain orchestrator. They inherit agent_runtime today; narrowing each
    -- domain's grants to its own workers is a follow-up (see docs/model-findings.md).
    FOREACH r IN ARRAY ARRAY['ro','priv','ref','hr','ta','ob','it','pay','ben','time','comp',
                             'perf','learn','fin','er'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent_' || r) THEN
            EXECUTE format('CREATE ROLE %I NOLOGIN IN ROLE agent_runtime', 'agent_' || r);
        END IF;
    END LOOP;

    -- The application's login role. It holds no privileges itself; each transaction does
    -- SET LOCAL ROLE to the acting role, so a bug cannot run with a broad identity.
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'daydor_app') THEN
        CREATE ROLE daydor_app LOGIN PASSWORD 'dev' NOINHERIT;
    END IF;
END
$$;

GRANT daydor_admin, daydor_ops, tenant_founder, tenant_hr, tenant_payroll, tenant_it,
      tenant_manager, tenant_employee, external_auditor, daydor_worker
      TO daydor_app WITH INHERIT FALSE, SET TRUE;
GRANT agent_ro, agent_priv, agent_ref, agent_hr, agent_ta, agent_ob, agent_it, agent_pay,
      agent_ben, agent_time, agent_comp, agent_perf, agent_learn, agent_fin, agent_er
      TO daydor_app WITH INHERIT FALSE, SET TRUE;

GRANT CREATE, USAGE ON SCHEMA public TO daydor_schema_owner;
CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION daydor_schema_owner;

SET ROLE daydor_schema_owner;

GRANT USAGE ON SCHEMA app TO daydor_admin, daydor_ops, tenant_founder, tenant_hr, tenant_payroll,
    tenant_it, tenant_manager, tenant_employee, external_auditor, agent_runtime, daydor_worker;
GRANT USAGE ON SCHEMA public TO daydor_admin, daydor_ops, tenant_founder, tenant_hr, tenant_payroll,
    tenant_it, tenant_manager, tenant_employee, external_auditor, agent_runtime, daydor_worker;
-- Functions are opt-in: nothing is executable unless granted below or in later migrations.
ALTER DEFAULT PRIVILEGES IN SCHEMA app REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- Session context. The app sets these with SET LOCAL at the start of every transaction:
--   SET LOCAL ROLE <acting role>;
--   SELECT set_config('app.tenant_id', ..., true), ('app.user_id'), ('app.employee_id'),
--          ('app.purpose'), ('app.agent_task_run_id')
-- The app server is trusted to set tenant and user; the database enforces everything else.
-- ---------------------------------------------------------------------------
CREATE FUNCTION app.setting_uuid(name text) RETURNS uuid
LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting(name, true), '')::uuid $$;

CREATE FUNCTION app.tenant_id() RETURNS uuid
LANGUAGE sql STABLE AS $$ SELECT app.setting_uuid('app.tenant_id') $$;

CREATE FUNCTION app.user_id() RETURNS uuid
LANGUAGE sql STABLE AS $$ SELECT app.setting_uuid('app.user_id') $$;

CREATE FUNCTION app.employee_id() RETURNS uuid
LANGUAGE sql STABLE AS $$ SELECT app.setting_uuid('app.employee_id') $$;

CREATE FUNCTION app.agent_task_run_id() RETURNS uuid
LANGUAGE sql STABLE AS $$ SELECT app.setting_uuid('app.agent_task_run_id') $$;

CREATE FUNCTION app.purpose() RETURNS text
LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('app.purpose', true), '') $$;

-- The role the caller switched into with SET ROLE. Works inside SECURITY DEFINER functions
-- (where current_user is the definer) because the "role" setting is not changed by them.
-- Per-domain agent roles collapse to agent_runtime, which carries their grants.
CREATE FUNCTION app.current_app_role() RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT CASE WHEN r LIKE 'agent\_%' THEN 'agent_runtime' ELSE r END
    FROM (SELECT coalesce(nullif(current_setting('role', true), 'none'), session_user::text) AS r) s
$$;

CREATE FUNCTION app.current_agent_role() RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT CASE WHEN r LIKE 'agent\_%' THEN r END
    FROM (SELECT coalesce(nullif(current_setting('role', true), 'none'), session_user::text) AS r) s
$$;

CREATE FUNCTION app.is_daydor_staff() RETURNS boolean
LANGUAGE sql STABLE AS $$ SELECT app.current_app_role() IN ('daydor_admin', 'daydor_ops') $$;

-- ---------------------------------------------------------------------------
-- Reporting closure: every (ancestor, descendant) pair in the reporting tree, so a manager's
-- visibility is one indexed lookup. Rebuilt by trigger when reporting_line changes (0004).
-- ---------------------------------------------------------------------------
CREATE TABLE app.reporting_closure (
    tenant_id      uuid NOT NULL,
    ancestor_id    uuid NOT NULL,
    descendant_id  uuid NOT NULL,
    depth          integer NOT NULL CHECK (depth >= 1),
    PRIMARY KEY (tenant_id, ancestor_id, descendant_id)
);
CREATE INDEX reporting_closure_descendant_idx ON app.reporting_closure (tenant_id, descendant_id);

-- Person scope used by RLS on every employee-linked table:
--   tenant-wide roles see everyone in the tenant (column grants still apply),
--   managers see themselves and their reporting subtree, employees see only themselves.
CREATE FUNCTION app.can_see_employee(target uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, pg_temp AS $$
    SELECT CASE app.current_app_role()
        WHEN 'tenant_employee' THEN target = app.employee_id()
        WHEN 'tenant_manager' THEN
            target = app.employee_id()
            OR EXISTS (SELECT 1 FROM app.reporting_closure rc
                       WHERE rc.tenant_id = app.tenant_id()
                         AND rc.ancestor_id = app.employee_id()
                         AND rc.descendant_id = target)
        ELSE app.current_app_role() IN ('daydor_admin', 'daydor_ops', 'tenant_founder', 'tenant_hr',
                                        'tenant_payroll', 'tenant_it', 'external_auditor',
                                        'agent_runtime', 'daydor_schema_owner')
    END
$$;

-- ---------------------------------------------------------------------------
-- Shared trigger functions
-- ---------------------------------------------------------------------------
CREATE FUNCTION app.touch_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END $$;

CREATE FUNCTION app.reject_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: % is not allowed', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END $$;

GRANT EXECUTE ON FUNCTION app.setting_uuid(text), app.tenant_id(), app.user_id(), app.employee_id(),
    app.agent_task_run_id(), app.purpose(), app.current_app_role(), app.current_agent_role(),
    app.is_daydor_staff(), app.can_see_employee(uuid)
    TO daydor_admin, daydor_ops, tenant_founder, tenant_hr, tenant_payroll, tenant_it,
       tenant_manager, tenant_employee, external_auditor, agent_runtime, daydor_worker;

RESET ROLE;
