-- Phase F of the agentic infrastructure (docs/agentic-infra-plan.md), the part that needs no vendor credentials:
--
--   1. A circuit breaker for every vendor adapter (the model provider has had one since 0043), usable from the dispatcher role so it can
--      run in its own transaction around an adapter call.
--   2. A webhook inbox: a vendor posts an event to a per-tenant secret URL; the API checks its signature and stores it here, once
--      (idempotent on the vendor's event id); a queue job hands it to whatever handler is registered for that integration. Nothing is
--      lost when no handler exists yet: the event waits, and ops can replay it.
--   3. Platform health for operations: aggregate counts only, across tenants, readable by daydor_admin, and the alerts derived from them.

SET ROLE daydor_schema_owner;

-- ---------------------------------------------------------------------------
-- 1. One breaker per adapter
-- ---------------------------------------------------------------------------
INSERT INTO app.integration_circuit (integration) VALUES
    ('bank'), ('tax_filing'), ('gl'), ('background_check'), ('everify'), ('idp'), ('job_board')
ON CONFLICT (integration) DO NOTHING;
GRANT EXECUTE ON FUNCTION app.circuit_allow(text), app.circuit_record(text, boolean, text) TO daydor_worker;

-- ---------------------------------------------------------------------------
-- 2. Webhook inbox
-- ---------------------------------------------------------------------------
CREATE TABLE app.webhook_endpoint (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL DEFAULT app.tenant_id() REFERENCES public.tenant (id),
    integration     text NOT NULL REFERENCES app.integration_circuit (integration),
    token_sha256    text NOT NULL UNIQUE,                  -- the URL secret is shown once and only its hash is kept
    enabled         boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE app.webhook_endpoint ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.webhook_endpoint FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON app.webhook_endpoint
    USING (tenant_id = app.tenant_id()) WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, integration, enabled, created_at) ON app.webhook_endpoint TO daydor_ops, daydor_admin;
GRANT UPDATE (enabled) ON app.webhook_endpoint TO daydor_ops;

CREATE FUNCTION app.create_webhook_endpoint(p_integration text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    v_token text := replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '');
BEGIN
    IF app.tenant_id() IS NULL THEN
        RAISE EXCEPTION 'an endpoint belongs to a tenant' USING ERRCODE = 'check_violation';
    END IF;
    INSERT INTO app.webhook_endpoint (integration, token_sha256) VALUES (p_integration, encode(sha256(convert_to(v_token, 'UTF8')), 'hex'));
    RETURN v_token;
END $$;
GRANT EXECUTE ON FUNCTION app.create_webhook_endpoint(text) TO daydor_ops;

CREATE TABLE app.webhook_event (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL DEFAULT app.tenant_id() REFERENCES public.tenant (id),
    endpoint_id     uuid NOT NULL REFERENCES app.webhook_endpoint (id),
    integration     text NOT NULL,
    external_id     text NOT NULL,                         -- the vendor's own event id: how a redelivery is recognised
    payload         jsonb NOT NULL,
    status          text NOT NULL DEFAULT 'received' CHECK (status IN ('received', 'processed', 'failed', 'ignored')),
    attempts        integer NOT NULL DEFAULT 0,
    last_error      text,
    received_at     timestamptz NOT NULL DEFAULT now(),
    processed_at    timestamptz,
    UNIQUE (tenant_id, integration, external_id)
);
CREATE INDEX webhook_event_open_idx ON app.webhook_event (status) WHERE status IN ('received', 'failed');
ALTER TABLE app.webhook_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.webhook_event FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON app.webhook_event
    USING (tenant_id = app.tenant_id()) WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, integration, external_id, status, attempts, last_error, received_at, processed_at) ON app.webhook_event
    TO daydor_ops, daydor_admin, external_auditor;       -- the payload is vendor data: ops reads it only through app.webhook_event_load

-- The one write the unauthenticated edge can make: look the endpoint up by the hash of its URL secret, then store the event for that
-- tenant, once. Returns 'unknown' (no such endpoint, or switched off), 'duplicate', or 'received'.
CREATE FUNCTION app.receive_webhook(p_token_sha256 text, p_integration text, p_external_id text, p_payload jsonb)
RETURNS TABLE (outcome text, event_id uuid)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    e record;
    v_id uuid;
BEGIN
    SELECT tenant_id, id INTO e FROM app.webhook_endpoint_lookup(p_token_sha256, p_integration);
    IF NOT FOUND THEN
        RETURN QUERY SELECT 'unknown', NULL::uuid; RETURN;
    END IF;
    PERFORM set_config('app.tenant_id', e.tenant_id::text, true);
    BEGIN
        INSERT INTO app.webhook_event (endpoint_id, integration, external_id, payload)
        VALUES (e.id, p_integration, left(p_external_id, 200), p_payload) RETURNING id INTO v_id;
    EXCEPTION WHEN unique_violation THEN
        RETURN QUERY SELECT 'duplicate', NULL::uuid; RETURN;
    END;
    PERFORM app.enqueue('webhooks', 'webhook.received', jsonb_build_object('event_id', v_id, 'integration', p_integration),
                        'webhook:' || v_id::text);
    RETURN QUERY SELECT 'received', v_id;
END $$;

-- Endpoints are tenant data under row security, but the edge does not know the tenant yet: this is the lookup that finds it, owned by
-- daydor_system for exactly that reason (see below) and returning nothing but the two ids.
CREATE FUNCTION app.webhook_endpoint_lookup(p_token_sha256 text, p_integration text) RETURNS TABLE (tenant_id uuid, id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
    SELECT w.tenant_id, w.id FROM app.webhook_endpoint w
    WHERE w.token_sha256 = p_token_sha256 AND w.integration = p_integration AND w.enabled
$$;

-- What a handler reads and writes about an event, in the event's own tenant.
CREATE FUNCTION app.webhook_event_load(p_id uuid) RETURNS TABLE (id uuid, integration text, external_id text, payload jsonb, status text, attempts integer)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
    SELECT w.id, w.integration, w.external_id, w.payload, w.status, w.attempts FROM app.webhook_event w
    WHERE w.id = p_id AND w.tenant_id = app.tenant_id()
$$;

CREATE FUNCTION app.webhook_event_mark(p_id uuid, p_status text, p_error text DEFAULT NULL) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
BEGIN
    IF p_status NOT IN ('processed', 'failed', 'ignored') THEN
        RAISE EXCEPTION 'a webhook event ends processed, failed or ignored' USING ERRCODE = 'check_violation';
    END IF;
    UPDATE app.webhook_event SET status = p_status, attempts = attempts + 1, last_error = left(p_error, 500),
                                 processed_at = CASE WHEN p_status = 'failed' THEN NULL ELSE now() END
    WHERE id = p_id AND tenant_id = app.tenant_id();
    IF NOT FOUND THEN
        RAISE EXCEPTION 'webhook event % not found', p_id USING ERRCODE = 'no_data_found';
    END IF;
END $$;

-- Ops puts an ignored or failed event back on the queue, e.g. after a handler for its integration ships.
CREATE FUNCTION app.replay_webhook(p_id uuid) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    v_integration text;
BEGIN
    UPDATE app.webhook_event SET status = 'received', last_error = NULL, processed_at = NULL
    WHERE id = p_id AND tenant_id = app.tenant_id() AND status IN ('failed', 'ignored')
    RETURNING integration INTO v_integration;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'webhook event % cannot be replayed', p_id USING ERRCODE = 'check_violation';
    END IF;
    RETURN app.enqueue('webhooks', 'webhook.received', jsonb_build_object('event_id', p_id, 'integration', v_integration),
                       'webhook-replay:' || p_id::text || ':' || gen_random_uuid()::text);
END $$;

GRANT EXECUTE ON FUNCTION app.webhook_event_load(uuid), app.webhook_event_mark(uuid, text, text) TO worker_root_orchestrator;
GRANT EXECUTE ON FUNCTION app.replay_webhook(uuid) TO daydor_ops;

-- ---------------------------------------------------------------------------
-- 3. Platform health: aggregates across tenants, no row content
-- ---------------------------------------------------------------------------
CREATE FUNCTION app.ops_health() RETURNS TABLE (metric text, labels jsonb, value numeric)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
    SELECT 'queue_jobs', jsonb_build_object('queue', queue, 'status', status), count(*)::numeric FROM app.job GROUP BY queue, status
    UNION ALL
    SELECT 'queue_oldest_ready_seconds', jsonb_build_object('queue', queue),
           extract(epoch FROM now() - min(run_at))::numeric FROM app.job WHERE status = 'queued' AND run_at <= now() GROUP BY queue
    UNION ALL
    SELECT 'agent_runs_24h', jsonb_build_object('status', status), count(*)::numeric
    FROM public.agent_task_run WHERE started_at > now() - interval '24 hours' GROUP BY status
    UNION ALL
    SELECT 'agent_failures_24h', jsonb_build_object('code', coalesce(error_code, 'unknown')), count(*)::numeric
    FROM public.agent_task_run WHERE status = 'failed' AND started_at > now() - interval '24 hours' GROUP BY error_code
    UNION ALL
    SELECT 'circuit_open', jsonb_build_object('integration', integration), (state = 'open')::int::numeric FROM app.integration_circuit
    UNION ALL
    SELECT 'approvals_pending', jsonb_build_object('escalated', escalated_at IS NOT NULL), count(*)::numeric
    FROM public.approval_request WHERE status = 'pending' GROUP BY escalated_at IS NOT NULL
    UNION ALL
    SELECT 'webhook_events', jsonb_build_object('integration', integration, 'status', status), count(*)::numeric
    FROM app.webhook_event GROUP BY integration, status
    UNION ALL
    SELECT 'notifications_open', '{}'::jsonb, count(*)::numeric FROM app.notification WHERE dismissed_at IS NULL
    UNION ALL
    SELECT 'ai_tokens_this_month', '{}'::jsonb, coalesce(sum(t), 0)::numeric FROM (
        SELECT input_tokens + output_tokens AS t FROM app.agent_model_call WHERE created_at >= date_trunc('month', now())
        UNION ALL SELECT input_tokens + output_tokens FROM app.frontdoor_turn WHERE created_at >= date_trunc('month', now())) s
    UNION ALL
    SELECT 'tenants_near_ai_cap', '{}'::jsonb, count(*)::numeric FROM (
        SELECT b.tenant_id FROM app.tenant_ai_budget b
        WHERE b.monthly_cap_tokens > 0 AND b.monthly_cap_tokens * 0.8 <= (
            SELECT coalesce(sum(x), 0) FROM (
                SELECT m.input_tokens + m.output_tokens AS x FROM app.agent_model_call m
                WHERE m.tenant_id = b.tenant_id AND m.created_at >= date_trunc('month', now())
                UNION ALL SELECT f.input_tokens + f.output_tokens FROM app.frontdoor_turn f
                WHERE f.tenant_id = b.tenant_id AND f.created_at >= date_trunc('month', now())) u)) near
$$;

-- What needs a person's attention now, derived from the health numbers. Delivery (email, chat, paging) is Phase F's remaining work.
CREATE FUNCTION app.ops_alerts() RETURNS TABLE (severity text, code text, message text, value numeric)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
    WITH h AS (SELECT * FROM app.ops_health())
    SELECT 'critical', 'circuit_open', 'The circuit for ' || (labels ->> 'integration') || ' is open', value FROM h WHERE metric = 'circuit_open' AND value > 0
    UNION ALL
    SELECT 'warning', 'dead_jobs', 'Jobs on ' || (labels ->> 'queue') || ' ran out of retries', value FROM h
    WHERE metric = 'queue_jobs' AND labels ->> 'status' = 'dead' AND value > 0
    UNION ALL
    SELECT 'warning', 'queue_backlog', 'Jobs on ' || (labels ->> 'queue') || ' have waited more than 15 minutes', value FROM h
    WHERE metric = 'queue_oldest_ready_seconds' AND value > 900
    UNION ALL
    SELECT 'warning', 'webhook_failed', 'Failed webhook events for ' || (labels ->> 'integration'), value FROM h
    WHERE metric = 'webhook_events' AND labels ->> 'status' = 'failed' AND value > 0
    UNION ALL
    SELECT 'warning', 'agent_failures', 'Agent runs failed with ' || (labels ->> 'code') || ' in the last day', value FROM h
    WHERE metric = 'agent_failures_24h' AND value >= 10
    UNION ALL
    SELECT 'warning', 'tenants_near_ai_cap', 'Tenants at 80% or more of their monthly AI cap', value FROM h
    WHERE metric = 'tenants_near_ai_cap' AND value > 0
    UNION ALL
    SELECT 'info', 'approvals_escalated', 'Approvals waiting past their deadline', value FROM h
    WHERE metric = 'approvals_pending' AND labels ->> 'escalated' = 'true' AND value > 0
$$;

RESET ROLE;
-- The edge lookup and the health numbers cross tenants on purpose, so they are owned by daydor_system (BYPASSRLS) and nothing else is.
GRANT SELECT ON app.webhook_endpoint, app.webhook_event, app.job, app.integration_circuit, app.notification, app.tenant_ai_budget,
    app.agent_model_call, app.frontdoor_turn, public.agent_task_run, public.approval_request TO daydor_system;
GRANT USAGE ON SCHEMA app, public TO daydor_system;
ALTER FUNCTION app.webhook_endpoint_lookup(text, text) OWNER TO daydor_system;
ALTER FUNCTION app.ops_health() OWNER TO daydor_system;
ALTER FUNCTION app.ops_alerts() OWNER TO daydor_system;
GRANT EXECUTE ON FUNCTION app.webhook_endpoint_lookup(text, text) TO daydor_schema_owner;      -- receive_webhook calls it
GRANT EXECUTE ON FUNCTION app.receive_webhook(text, text, text, jsonb) TO daydor_worker;
GRANT EXECUTE ON FUNCTION app.ops_health(), app.ops_alerts() TO daydor_admin;
GRANT EXECUTE ON FUNCTION app.ops_health() TO daydor_system;
