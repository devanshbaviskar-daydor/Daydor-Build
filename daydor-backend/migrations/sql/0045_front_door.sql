-- Phase E of the agentic infrastructure (docs/agentic-infra-plan.md): the front door.
--
-- The front door turns what a person types into a typed command they confirm and the app then runs as them. It never executes a step and
-- never opens a gate (it works in a read-only transaction and has no command that resolves an approval). What the database holds for it:
--   1. app.frontdoor_tenant: off until Daydor switches it on for a tenant (the same shadow-first stance as LLM workers).
--   2. app.frontdoor_turn: one row per interpretation: outcome, model, tokens, cost. Never the text a person typed and never argument values
--      (utterance hash and length, argument names only), because those can be personal data.
--   3. app.frontdoor_gate(): before a model call: enabled for this tenant, the model provider's circuit, the tenant's AI budget, and a
--      per-person rate limit. app.frontdoor_record(): after it: the turn, and the circuit's view of the provider.
--   4. Front-door spend counts against the tenant's monthly AI cap like any worker's (app.tenant_ai_headroom).

SET ROLE daydor_schema_owner;

CREATE TABLE app.frontdoor_tenant (
    tenant_id   uuid PRIMARY KEY DEFAULT app.tenant_id() REFERENCES public.tenant (id),
    enabled     boolean NOT NULL DEFAULT false,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE app.frontdoor_tenant ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.frontdoor_tenant FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON app.frontdoor_tenant
    USING (tenant_id = app.tenant_id()) WITH CHECK (tenant_id = app.tenant_id());
CREATE TRIGGER frontdoor_tenant_touch BEFORE UPDATE ON app.frontdoor_tenant
    FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
GRANT SELECT ON app.frontdoor_tenant TO daydor_ops, daydor_admin, external_auditor, tenant_founder;
GRANT INSERT (enabled), UPDATE (enabled) ON app.frontdoor_tenant TO daydor_ops;

CREATE TABLE app.frontdoor_turn (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         uuid NOT NULL DEFAULT app.tenant_id() REFERENCES public.tenant (id),
    user_id           uuid,
    role              text NOT NULL DEFAULT app.current_app_role(),
    status            text NOT NULL CHECK (status IN ('ready', 'needs_input', 'unsupported', 'refused', 'failed')),
    command_id        text,
    arg_names         text[] NOT NULL DEFAULT '{}',
    utterance_sha256  text NOT NULL,
    utterance_chars   integer NOT NULL CHECK (utterance_chars >= 0),
    model             text,
    turns             integer NOT NULL DEFAULT 0,
    input_tokens      integer NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens     integer NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    cost_usd          numeric,
    latency_ms        integer,
    error             text,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX frontdoor_turn_user_idx ON app.frontdoor_turn (tenant_id, user_id, created_at DESC);
ALTER TABLE app.frontdoor_turn ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.frontdoor_turn FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON app.frontdoor_turn
    USING (tenant_id = app.tenant_id()) WITH CHECK (tenant_id = app.tenant_id());
CREATE TRIGGER frontdoor_turn_append_only BEFORE UPDATE OR DELETE ON app.frontdoor_turn
    FOR EACH ROW EXECUTE FUNCTION app.reject_mutation();
GRANT SELECT ON app.frontdoor_turn TO daydor_ops, daydor_admin, external_auditor, tenant_founder;

-- Spend counts against the tenant's cap whichever way the model was called.
CREATE OR REPLACE FUNCTION app.tenant_ai_headroom() RETURNS TABLE (cap_usd numeric, cap_tokens bigint, used_usd numeric, used_tokens bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
    WITH month AS (SELECT (date_trunc('month', now() AT TIME ZONE 'utc') AT TIME ZONE 'utc') AS since),
    spend AS (
        SELECT mc.cost_usd, (mc.input_tokens + mc.output_tokens)::bigint AS tokens
        FROM app.agent_model_call mc, month WHERE mc.tenant_id = app.tenant_id() AND mc.created_at >= month.since
        UNION ALL
        SELECT ft.cost_usd, (ft.input_tokens + ft.output_tokens)::bigint
        FROM app.frontdoor_turn ft, month WHERE ft.tenant_id = app.tenant_id() AND ft.created_at >= month.since
    )
    SELECT (SELECT b.monthly_cap_usd FROM app.tenant_ai_budget b WHERE b.tenant_id = app.tenant_id()),
           (SELECT b.monthly_cap_tokens FROM app.tenant_ai_budget b WHERE b.tenant_id = app.tenant_id()),
           coalesce(sum(s.cost_usd), 0), coalesce(sum(s.tokens), 0)::bigint
    FROM spend s
$$;
GRANT EXECUTE ON FUNCTION app.tenant_ai_headroom() TO tenant_manager, tenant_employee, tenant_hr, tenant_payroll, tenant_it;

-- One call before the model: may this person ask, and what is left?
CREATE FUNCTION app.frontdoor_gate(p_per_hour integer DEFAULT 30)
RETURNS TABLE (allowed boolean, reason text, retry_after_s integer, cap_usd numeric, cap_tokens bigint, used_usd numeric, used_tokens bigint)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    v_enabled boolean;
    v_circuit record;
    v_recent integer;
    h record;
BEGIN
    SELECT enabled INTO v_enabled FROM app.frontdoor_tenant WHERE tenant_id = app.tenant_id();
    SELECT * INTO h FROM app.tenant_ai_headroom();
    IF NOT coalesce(v_enabled, false) THEN
        RETURN QUERY SELECT false, 'not_enabled', 0, h.cap_usd, h.cap_tokens, h.used_usd, h.used_tokens; RETURN;
    END IF;
    SELECT * INTO v_circuit FROM app.circuit_allow('model_provider');
    IF NOT v_circuit.allowed THEN
        RETURN QUERY SELECT false, 'provider_unavailable', v_circuit.retry_after_s, h.cap_usd, h.cap_tokens, h.used_usd, h.used_tokens; RETURN;
    END IF;
    IF (h.cap_tokens IS NOT NULL AND h.used_tokens >= h.cap_tokens) OR (h.cap_usd IS NOT NULL AND h.used_usd >= h.cap_usd) THEN
        RETURN QUERY SELECT false, 'budget_used_up', 0, h.cap_usd, h.cap_tokens, h.used_usd, h.used_tokens; RETURN;
    END IF;
    SELECT count(*) INTO v_recent FROM app.frontdoor_turn ft
    WHERE ft.tenant_id = app.tenant_id() AND ft.user_id IS NOT DISTINCT FROM app.user_id() AND ft.created_at > now() - interval '1 hour';
    IF v_recent >= p_per_hour THEN
        RETURN QUERY SELECT false, 'rate_limited', 60, h.cap_usd, h.cap_tokens, h.used_usd, h.used_tokens; RETURN;
    END IF;
    RETURN QUERY SELECT true, 'ok', 0, h.cap_usd, h.cap_tokens, h.used_usd, h.used_tokens;
END $$;

-- After: the turn, and what the provider did (p_provider_ok NULL = the model was not called).
CREATE FUNCTION app.frontdoor_record(p_status text, p_command_id text, p_arg_names text[], p_utterance_sha text, p_utterance_chars integer,
        p_model text, p_turns integer, p_input_tokens integer, p_output_tokens integer, p_cost_usd numeric, p_latency_ms integer,
        p_error text, p_provider_ok boolean) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    v_id uuid;
BEGIN
    INSERT INTO app.frontdoor_turn (user_id, status, command_id, arg_names, utterance_sha256, utterance_chars, model, turns,
                                    input_tokens, output_tokens, cost_usd, latency_ms, error)
    VALUES (app.user_id(), p_status, p_command_id, coalesce(p_arg_names, '{}'), p_utterance_sha, p_utterance_chars, p_model,
            coalesce(p_turns, 0), coalesce(p_input_tokens, 0), coalesce(p_output_tokens, 0), p_cost_usd, p_latency_ms, left(p_error, 300))
    RETURNING id INTO v_id;
    IF p_provider_ok IS NOT NULL THEN
        PERFORM app.circuit_record('model_provider', p_provider_ok, p_error);
    END IF;
    RETURN v_id;
END $$;

GRANT EXECUTE ON FUNCTION app.frontdoor_gate(integer), app.frontdoor_record(text, text, text[], text, integer, text, integer, integer,
    integer, numeric, integer, text, boolean) TO tenant_founder, tenant_hr, tenant_payroll, tenant_it, tenant_manager, tenant_employee;

RESET ROLE;
