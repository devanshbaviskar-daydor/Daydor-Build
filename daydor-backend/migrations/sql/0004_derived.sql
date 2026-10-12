-- Derived structures: reporting closure maintenance and the employee directory.
-- Runs as superuser for the role creation, then as the owning roles.

DO $$
BEGIN
    -- Owns internal functions that must see a whole tenant regardless of the caller's scope.
    -- BYPASSRLS, so every function it owns must filter by tenant explicitly.
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'daydor_system') THEN
        CREATE ROLE daydor_system NOLOGIN BYPASSRLS;
    END IF;
END $$;

GRANT USAGE ON SCHEMA app, public TO daydor_system;
GRANT SELECT ON public.reporting_line, public.employee TO daydor_system;
GRANT SELECT, INSERT, DELETE ON app.reporting_closure TO daydor_system;
GRANT EXECUTE ON FUNCTION app.tenant_id(), app.setting_uuid(text) TO daydor_system;

SET ROLE daydor_schema_owner;

CREATE FUNCTION app.rebuild_reporting_closure(p_tenant uuid) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
    DELETE FROM app.reporting_closure WHERE tenant_id = p_tenant;
    INSERT INTO app.reporting_closure (tenant_id, ancestor_id, descendant_id, depth)
    WITH RECURSIVE active AS (
        SELECT employee_id, manager_employee_id
        FROM public.reporting_line
        WHERE tenant_id = p_tenant
          AND effective_from <= current_date
          AND (effective_to IS NULL OR effective_to >= current_date)
    ), walk AS (
        SELECT manager_employee_id AS ancestor_id, employee_id AS descendant_id, 1 AS depth
        FROM active
        UNION ALL
        SELECT a.manager_employee_id, w.descendant_id, w.depth + 1
        FROM walk w JOIN active a ON a.employee_id = w.ancestor_id
        WHERE w.depth < 50                       -- guards against cycles in bad data
    )
    SELECT p_tenant, ancestor_id, descendant_id, min(depth)
    FROM walk GROUP BY ancestor_id, descendant_id;
$$;

CREATE FUNCTION app.reporting_line_changed() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    t uuid;
BEGIN
    FOR t IN SELECT DISTINCT tenant_id FROM changed LOOP
        PERFORM app.rebuild_reporting_closure(t);
    END LOOP;
    RETURN NULL;
END $$;

-- Colleague directory: name, work email, department and location for active colleagues.
-- Owned by daydor_system so employees can see colleagues, with tenant filtered explicitly.
CREATE VIEW public.employee_directory WITH (security_barrier) AS
SELECT e.id, e.full_name, e.work_email, e.department_id, e.location_id, e.position_id
FROM public.employee e
WHERE e.tenant_id = app.tenant_id() AND e.is_active;

RESET ROLE;

ALTER FUNCTION app.rebuild_reporting_closure(uuid) OWNER TO daydor_system;
ALTER FUNCTION app.reporting_line_changed() OWNER TO daydor_system;
ALTER VIEW public.employee_directory OWNER TO daydor_system;
GRANT EXECUTE ON FUNCTION app.rebuild_reporting_closure(uuid) TO daydor_system;

SET ROLE daydor_schema_owner;
CREATE TRIGGER reporting_line_closure_ins AFTER INSERT ON public.reporting_line
    REFERENCING NEW TABLE AS changed FOR EACH STATEMENT EXECUTE FUNCTION app.reporting_line_changed();
CREATE TRIGGER reporting_line_closure_upd AFTER UPDATE ON public.reporting_line
    REFERENCING NEW TABLE AS changed FOR EACH STATEMENT EXECUTE FUNCTION app.reporting_line_changed();
RESET ROLE;

GRANT SELECT ON public.employee_directory TO tenant_founder, tenant_hr, tenant_payroll, tenant_it,
    tenant_manager, tenant_employee, daydor_ops, agent_runtime;
