-- Per-tenant overrides of a worker's autonomy and enabled flag (ADR-004: a tenant may lower a
-- worker's autonomy, never raise it), and the check every worker job runs before it starts.
--
-- Autonomy ladder, safest last:  auto < review < approve.  An override must be at or above the
-- worker's default. Platform actors cannot be overridden at all: disabling the workflow engine
-- for one tenant would strand its instances.

SET ROLE daydor_schema_owner;

CREATE TABLE app.worker_tenant_policy (
    tenant_id   uuid NOT NULL DEFAULT app.tenant_id() REFERENCES public.tenant (id),
    worker      text NOT NULL REFERENCES app.worker_definition (worker),
    autonomy    text CHECK (autonomy IN ('auto', 'review', 'approve')),   -- NULL = keep the default
    enabled     boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, worker)
);
ALTER TABLE app.worker_tenant_policy ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.worker_tenant_policy FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON app.worker_tenant_policy
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE TRIGGER worker_tenant_policy_touch BEFORE UPDATE ON app.worker_tenant_policy
    FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();

CREATE FUNCTION app.autonomy_rank(p_autonomy text) RETURNS integer
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE p_autonomy WHEN 'auto' THEN 0 WHEN 'review' THEN 1 WHEN 'approve' THEN 2 END
$$;

CREATE FUNCTION app.worker_tenant_policy_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS $$
DECLARE
    d app.worker_definition;
BEGIN
    SELECT * INTO d FROM app.worker_definition WHERE worker = NEW.worker;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'unknown worker %', NEW.worker USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF d.platform_actor THEN
        RAISE EXCEPTION '% is a platform actor; tenants cannot override it', NEW.worker
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.autonomy IS NOT NULL AND app.autonomy_rank(NEW.autonomy) < app.autonomy_rank(d.autonomy) THEN
        RAISE EXCEPTION 'tenant policy cannot raise autonomy of % above its default (% -> %)',
            NEW.worker, d.autonomy, NEW.autonomy USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER worker_tenant_policy_guard BEFORE INSERT OR UPDATE ON app.worker_tenant_policy
    FOR EACH ROW EXECUTE FUNCTION app.worker_tenant_policy_guard();

-- Effective autonomy for the session's tenant: the stricter of the default and the override.
CREATE FUNCTION app.worker_effective_autonomy(p_worker text) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, pg_temp AS $$
    SELECT CASE WHEN p.autonomy IS NOT NULL AND app.autonomy_rank(p.autonomy) > app.autonomy_rank(d.autonomy)
                THEN p.autonomy ELSE d.autonomy END
    FROM app.worker_definition d
    LEFT JOIN app.worker_tenant_policy p ON p.worker = d.worker AND p.tenant_id = app.tenant_id()
    WHERE d.worker = p_worker
$$;

-- Fail-closed check, run first in every worker job: raises if the worker is unknown, disabled
-- globally, or disabled by the tenant. Returns the effective autonomy.
CREATE FUNCTION app.assert_worker_enabled(p_worker text) RETURNS text
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = app, pg_temp AS $$
DECLARE
    d app.worker_definition;
    p app.worker_tenant_policy;
BEGIN
    SELECT * INTO d FROM app.worker_definition WHERE worker = p_worker;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'unknown worker %', p_worker USING ERRCODE = 'undefined_object';
    END IF;
    IF NOT d.enabled THEN
        RAISE EXCEPTION 'worker % is disabled', p_worker USING ERRCODE = 'insufficient_privilege';
    END IF;
    SELECT * INTO p FROM app.worker_tenant_policy WHERE worker = p_worker AND tenant_id = app.tenant_id();
    IF FOUND AND NOT p.enabled THEN
        RAISE EXCEPTION 'worker % is disabled for this tenant', p_worker USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN app.worker_effective_autonomy(p_worker);
END $$;

GRANT SELECT ON app.worker_tenant_policy TO worker_platform, daydor_ops, tenant_founder, tenant_hr;
GRANT INSERT (worker, autonomy, enabled), UPDATE (autonomy, enabled)
    ON app.worker_tenant_policy TO tenant_founder, tenant_hr;
GRANT EXECUTE ON FUNCTION app.autonomy_rank(text) TO worker_platform, tenant_founder, tenant_hr;
GRANT EXECUTE ON FUNCTION app.worker_effective_autonomy(text) TO worker_platform, tenant_founder, tenant_hr;
GRANT EXECUTE ON FUNCTION app.assert_worker_enabled(text) TO worker_platform, tenant_founder, tenant_hr;

RESET ROLE;
