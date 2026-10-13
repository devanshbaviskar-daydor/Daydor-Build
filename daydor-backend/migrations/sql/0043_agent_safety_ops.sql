-- Phase C of the agentic infrastructure (docs/agentic-infra-plan.md): safety and operations for LLM workers.
--
--   1. Rollout. An LLM worker starts in `shadow` for every tenant: its proposal is recorded, never applied. Daydor (daydor_ops) promotes it
--      to `canary` (applied, but a person acknowledges every run) and then `ga`, one tenant at a time, and only with evidence:
--      canary needs a passing eval on the exact prompt in force, ga needs a passing *live* eval and a clean canary period.
--      Changing the prompt drops the worker back to shadow. A tenant can always demote itself.
--   2. Evals. app.worker_eval_result: append-only results of a golden-set run (prompt hash, models, passed/total).
--   3. Tenant AI budgets. A monthly cap in dollars and/or tokens per tenant, read before every model call, plus a usage view.
--   4. A circuit breaker per integration (the model provider is the first). An open circuit defers a job without spending an attempt.
--   5. app.defer_job: put a job back on its queue for later without counting the attempt.

SET ROLE daydor_schema_owner;

-- ---------------------------------------------------------------------------
-- 5. Deferring a job (a circuit is open: nothing is wrong with the job)
-- ---------------------------------------------------------------------------
CREATE FUNCTION app.defer_job(p_job uuid, p_worker text, p_run_at timestamptz, p_reason text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS $$
BEGIN
    UPDATE app.job
    SET status = 'queued', run_at = p_run_at, attempts = greatest(attempts - 1, 0), last_error = left(p_reason, 4000),
        locked_by = NULL, locked_until = NULL
    WHERE id = p_job AND status = 'running' AND locked_by = p_worker;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'lease lost for job %', p_job USING ERRCODE = 'lock_not_available';
    END IF;
END $$;
GRANT EXECUTE ON FUNCTION app.defer_job(uuid, text, timestamptz, text) TO daydor_worker;

-- ---------------------------------------------------------------------------
-- 2. Eval results
-- ---------------------------------------------------------------------------
CREATE TABLE app.worker_eval_result (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    worker          text NOT NULL REFERENCES app.worker_definition (worker),
    mode            text NOT NULL CHECK (mode IN ('replay', 'live')),
    prompt_sha256   text NOT NULL,
    golden_sha256   text NOT NULL,
    models          jsonb NOT NULL DEFAULT '{}',
    total           integer NOT NULL CHECK (total >= 0),
    passed_count    integer NOT NULL CHECK (passed_count BETWEEN 0 AND total),
    passed          boolean GENERATED ALWAYS AS (total > 0 AND passed_count = total) STORED,
    details         jsonb NOT NULL DEFAULT '[]',
    run_at          timestamptz NOT NULL DEFAULT now(),
    run_by          text NOT NULL DEFAULT current_user
);
CREATE INDEX worker_eval_result_idx ON app.worker_eval_result (worker, prompt_sha256, mode) WHERE passed;
CREATE TRIGGER worker_eval_result_append_only BEFORE UPDATE OR DELETE ON app.worker_eval_result
    FOR EACH ROW EXECUTE FUNCTION app.reject_mutation();
GRANT SELECT ON app.worker_eval_result TO daydor_ops, daydor_admin, external_auditor;

CREATE FUNCTION app.record_worker_eval(p_worker text, p_mode text, p_prompt_sha text, p_golden_sha text, p_models jsonb,
                                       p_total integer, p_passed integer, p_details jsonb DEFAULT '[]') RETURNS uuid
LANGUAGE sql SECURITY DEFINER SET search_path = app, pg_temp AS $$
    INSERT INTO app.worker_eval_result (worker, mode, prompt_sha256, golden_sha256, models, total, passed_count, details)
    VALUES (p_worker, p_mode, p_prompt_sha, p_golden_sha, coalesce(p_models, '{}'), p_total, p_passed, coalesce(p_details, '[]'))
    RETURNING id
$$;
GRANT EXECUTE ON FUNCTION app.record_worker_eval(text, text, text, text, jsonb, integer, integer, jsonb) TO daydor_ops, daydor_admin;

-- ---------------------------------------------------------------------------
-- 1. Rollout
-- ---------------------------------------------------------------------------
CREATE TABLE app.worker_rollout (
    tenant_id       uuid NOT NULL DEFAULT app.tenant_id() REFERENCES public.tenant (id),
    worker          text NOT NULL REFERENCES app.worker_definition (worker),
    stage           text NOT NULL CHECK (stage IN ('shadow', 'canary', 'ga')),
    prompt_sha256   text,
    models          jsonb,
    stage_since     timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, worker),
    CHECK ((stage = 'shadow') = (prompt_sha256 IS NULL))
);
ALTER TABLE app.worker_rollout ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.worker_rollout FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON app.worker_rollout
    USING (tenant_id = app.tenant_id()) WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT ON app.worker_rollout TO daydor_ops, daydor_admin, external_auditor, tenant_founder, tenant_hr;

-- A worker is promoted only on evidence, one step at a time. This is the check; the functions below are only the way in.
CREATE FUNCTION app.worker_rollout_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    d app.worker_definition;
    v_committed integer;
    v_rejected integer;
BEGIN
    SELECT * INTO d FROM app.worker_definition WHERE worker = NEW.worker;
    IF d.kind <> 'llm' THEN
        RAISE EXCEPTION '% is not an LLM worker; it has no rollout', NEW.worker USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.stage = 'shadow' THEN
        NEW.prompt_sha256 := NULL;
        NEW.models := NULL;
    ELSE
        IF NOT EXISTS (SELECT 1 FROM app.worker_eval_result e
                       WHERE e.worker = NEW.worker AND e.prompt_sha256 = NEW.prompt_sha256 AND e.passed
                         AND (NEW.stage = 'canary' OR e.mode = 'live')) THEN
            RAISE EXCEPTION '% cannot go to % on prompt %: no passing %eval on file',
                NEW.worker, NEW.stage, left(NEW.prompt_sha256, 12), CASE NEW.stage WHEN 'ga' THEN 'live ' ELSE '' END
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    IF NEW.stage = 'ga' AND (TG_OP = 'INSERT' OR OLD.stage <> 'ga') THEN
        IF TG_OP = 'INSERT' OR OLD.stage <> 'canary' OR OLD.prompt_sha256 IS DISTINCT FROM NEW.prompt_sha256 THEN
            RAISE EXCEPTION '% must run as canary on this prompt before general availability', NEW.worker
                USING ERRCODE = 'check_violation';
        END IF;
        SELECT count(*) INTO v_committed FROM app.agent_proposal ap
        WHERE ap.tenant_id = NEW.tenant_id AND ap.worker = NEW.worker AND ap.status = 'committed' AND ap.committed_at >= OLD.stage_since;
        SELECT count(*) INTO v_rejected FROM public.agent_task_run r
        WHERE r.tenant_id = NEW.tenant_id AND r.worker_name = NEW.worker AND r.status = 'rejected' AND r.started_at >= OLD.stage_since;
        IF v_committed < 5 OR v_rejected > 0 THEN
            RAISE EXCEPTION '% needs 5 committed canary runs and none rejected before general availability (has %, rejected %)',
                NEW.worker, v_committed, v_rejected USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    IF TG_OP = 'INSERT' OR NEW.stage <> OLD.stage OR NEW.prompt_sha256 IS DISTINCT FROM OLD.prompt_sha256 THEN
        NEW.stage_since := now();
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END $$;
CREATE TRIGGER worker_rollout_guard BEFORE INSERT OR UPDATE ON app.worker_rollout
    FOR EACH ROW EXECUTE FUNCTION app.worker_rollout_guard();

CREATE FUNCTION app.set_worker_rollout(p_worker text, p_stage text, p_prompt_sha text DEFAULT NULL, p_models jsonb DEFAULT NULL)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
BEGIN
    IF app.tenant_id() IS NULL THEN
        RAISE EXCEPTION 'a rollout is per tenant' USING ERRCODE = 'check_violation';
    END IF;
    -- Update first: a BEFORE INSERT trigger fires ahead of ON CONFLICT, so an upsert would always look like a first promotion.
    UPDATE app.worker_rollout SET stage = p_stage, prompt_sha256 = p_prompt_sha, models = p_models
    WHERE tenant_id = app.tenant_id() AND worker = p_worker;
    IF NOT FOUND THEN
        INSERT INTO app.worker_rollout (worker, stage, prompt_sha256, models) VALUES (p_worker, p_stage, p_prompt_sha, p_models);
    END IF;
    RETURN p_stage;
END $$;

-- A tenant may always step a worker back to shadow. Never forward.
CREATE FUNCTION app.demote_worker_rollout(p_worker text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
BEGIN
    INSERT INTO app.worker_rollout (worker, stage) VALUES (p_worker, 'shadow')
    ON CONFLICT (tenant_id, worker) DO UPDATE SET stage = 'shadow', prompt_sha256 = NULL, models = NULL;
    RETURN 'shadow';
END $$;

-- What a run does: the stage on the prompt in force. A promotion earned on another prompt does not carry over.
CREATE FUNCTION app.worker_rollout_stage(p_worker text, p_prompt_sha text) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
    SELECT coalesce((SELECT r.stage FROM app.worker_rollout r
                     WHERE r.tenant_id = app.tenant_id() AND r.worker = p_worker
                       AND (r.stage = 'shadow' OR r.prompt_sha256 = p_prompt_sha)), 'shadow')
$$;

GRANT EXECUTE ON FUNCTION app.set_worker_rollout(text, text, text, jsonb) TO daydor_ops, daydor_admin;
GRANT EXECUTE ON FUNCTION app.demote_worker_rollout(text) TO daydor_ops, tenant_founder, tenant_hr;
GRANT EXECUTE ON FUNCTION app.worker_rollout_stage(text, text) TO worker_platform, daydor_ops, tenant_founder, tenant_hr;

-- A shadow proposal is recorded, never applied.
ALTER TABLE app.agent_proposal DROP CONSTRAINT agent_proposal_status_check;
ALTER TABLE app.agent_proposal ADD CONSTRAINT agent_proposal_status_check
    CHECK (status IN ('proposed', 'committed', 'discarded', 'shadow'));

CREATE OR REPLACE FUNCTION app.mark_agent_proposal(p_run uuid, p_status text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
BEGIN
    PERFORM app.assert_own_run(p_run);
    IF p_status NOT IN ('committed', 'discarded', 'shadow') THEN
        RAISE EXCEPTION 'a proposal can only become committed, discarded or shadow' USING ERRCODE = 'check_violation';
    END IF;
    UPDATE app.agent_proposal SET status = p_status, committed_at = CASE WHEN p_status = 'committed' THEN now() END
    WHERE run_id = p_run AND tenant_id = app.tenant_id() AND status = 'proposed';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no open proposal for run %', p_run USING ERRCODE = 'no_data_found';
    END IF;
END $$;

-- How a worker is doing in a tenant: what it proposed, whether it was valid, what became of it.
CREATE VIEW app.agent_proposal_stats WITH (security_invoker = true) AS
    SELECT ap.tenant_id, ap.worker, ap.prompt_version, ap.status, ap.valid, count(*) AS proposals, max(ap.created_at) AS latest
    FROM app.agent_proposal ap GROUP BY ap.tenant_id, ap.worker, ap.prompt_version, ap.status, ap.valid;
GRANT SELECT ON app.agent_proposal_stats TO daydor_ops, daydor_admin, external_auditor, tenant_founder, tenant_hr, tenant_payroll, tenant_it;

-- ---------------------------------------------------------------------------
-- 3. Tenant AI budgets and usage
-- ---------------------------------------------------------------------------
CREATE TABLE app.tenant_ai_budget (
    tenant_id           uuid PRIMARY KEY DEFAULT app.tenant_id() REFERENCES public.tenant (id),
    monthly_cap_usd     numeric CHECK (monthly_cap_usd >= 0),
    monthly_cap_tokens  bigint CHECK (monthly_cap_tokens >= 0),
    note                text,
    updated_at          timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE app.tenant_ai_budget ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.tenant_ai_budget FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON app.tenant_ai_budget
    USING (tenant_id = app.tenant_id()) WITH CHECK (tenant_id = app.tenant_id());
CREATE TRIGGER tenant_ai_budget_touch BEFORE UPDATE ON app.tenant_ai_budget
    FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
GRANT SELECT ON app.tenant_ai_budget TO daydor_ops, daydor_admin, external_auditor, tenant_founder;
GRANT INSERT (monthly_cap_usd, monthly_cap_tokens, note), UPDATE (monthly_cap_usd, monthly_cap_tokens, note)
    ON app.tenant_ai_budget TO daydor_ops;      -- Daydor sets a tenant's cap; a tenant cannot raise its own

-- The caps and this calendar month's (UTC) spend. A NULL cap is no cap. Spend in dollars counts only priced calls.
CREATE FUNCTION app.tenant_ai_headroom() RETURNS TABLE (cap_usd numeric, cap_tokens bigint, used_usd numeric, used_tokens bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
    SELECT (SELECT b.monthly_cap_usd FROM app.tenant_ai_budget b WHERE b.tenant_id = app.tenant_id()),
           (SELECT b.monthly_cap_tokens FROM app.tenant_ai_budget b WHERE b.tenant_id = app.tenant_id()),
           coalesce(sum(mc.cost_usd), 0),
           coalesce(sum(mc.input_tokens + mc.output_tokens), 0)::bigint
    FROM app.agent_model_call mc
    WHERE mc.tenant_id = app.tenant_id() AND mc.created_at >= (date_trunc('month', now() AT TIME ZONE 'utc') AT TIME ZONE 'utc')
$$;
GRANT EXECUTE ON FUNCTION app.tenant_ai_headroom() TO worker_platform, daydor_ops, tenant_founder;

CREATE VIEW app.ai_usage_daily WITH (security_invoker = true) AS
    SELECT mc.tenant_id, (mc.created_at AT TIME ZONE 'utc')::date AS day, r.worker_name AS worker, mc.model,
           count(*) AS calls, sum(mc.input_tokens)::bigint AS input_tokens, sum(mc.output_tokens)::bigint AS output_tokens,
           sum(mc.cost_usd) AS cost_usd, count(*) FILTER (WHERE mc.cost_usd IS NULL) AS unpriced_calls,
           count(*) FILTER (WHERE mc.error IS NOT NULL) AS failed_calls
    FROM app.agent_model_call mc JOIN public.agent_task_run r ON r.id = mc.run_id
    GROUP BY mc.tenant_id, (mc.created_at AT TIME ZONE 'utc')::date, r.worker_name, mc.model;
GRANT SELECT ON app.ai_usage_daily TO daydor_ops, daydor_admin, external_auditor, tenant_founder;
GRANT SELECT ON public.agent_task_run TO tenant_founder;

-- ---------------------------------------------------------------------------
-- 4. Circuit breaker per integration
-- ---------------------------------------------------------------------------
-- Not per tenant: a vendor outage is everyone's. Closed lets calls through. After `threshold` failures in a row it opens and
-- refuses calls for `cooldown_s`; then calls are let through again as probes, and the first result decides: success closes it, a
-- failure reopens it. An integration must be registered here (a migration), so a worker cannot trip a breaker it does not use.
CREATE TABLE app.integration_circuit (
    integration     text PRIMARY KEY,
    state           text NOT NULL DEFAULT 'closed' CHECK (state IN ('closed', 'open')),
    failures        integer NOT NULL DEFAULT 0 CHECK (failures >= 0),
    threshold       integer NOT NULL DEFAULT 5 CHECK (threshold >= 1),
    cooldown_s      integer NOT NULL DEFAULT 60 CHECK (cooldown_s >= 1),
    opened_at       timestamptz,
    last_error      text,
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CHECK ((state = 'open') = (opened_at IS NOT NULL))
);
INSERT INTO app.integration_circuit (integration) VALUES ('model_provider');
GRANT SELECT ON app.integration_circuit TO daydor_ops, daydor_admin, external_auditor;

CREATE FUNCTION app.circuit_allow(p_integration text) RETURNS TABLE (allowed boolean, retry_after_s integer)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = app, pg_temp AS $$
DECLARE
    c app.integration_circuit;
BEGIN
    SELECT * INTO c FROM app.integration_circuit WHERE integration = p_integration;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'unknown integration %', p_integration USING ERRCODE = 'undefined_object';
    END IF;
    IF c.state = 'closed' OR now() >= c.opened_at + make_interval(secs => c.cooldown_s) THEN
        RETURN QUERY SELECT true, 0;
    ELSE
        RETURN QUERY SELECT false, ceil(extract(epoch FROM c.opened_at + make_interval(secs => c.cooldown_s) - now()))::integer;
    END IF;
END $$;

CREATE FUNCTION app.circuit_record(p_integration text, p_ok boolean, p_error text DEFAULT NULL) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS $$
DECLARE
    v_state text;
BEGIN
    UPDATE app.integration_circuit c SET
        state = CASE WHEN p_ok THEN 'closed' WHEN c.state = 'open' OR c.failures + 1 >= c.threshold THEN 'open' ELSE 'closed' END,
        opened_at = CASE WHEN p_ok THEN NULL WHEN c.state = 'open' OR c.failures + 1 >= c.threshold THEN now() ELSE NULL END,
        failures = CASE WHEN p_ok THEN 0 ELSE c.failures + 1 END,
        last_error = CASE WHEN p_ok THEN c.last_error ELSE left(p_error, 300) END,
        updated_at = now()
    WHERE c.integration = p_integration
    RETURNING c.state INTO v_state;
    IF v_state IS NULL THEN
        RAISE EXCEPTION 'unknown integration %', p_integration USING ERRCODE = 'undefined_object';
    END IF;
    RETURN v_state;
END $$;

CREATE FUNCTION app.circuit_reset(p_integration text) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = app, pg_temp AS $$
    UPDATE app.integration_circuit SET state = 'closed', failures = 0, opened_at = NULL, updated_at = now()
    WHERE integration = p_integration
$$;
GRANT EXECUTE ON FUNCTION app.circuit_allow(text), app.circuit_record(text, boolean, text) TO worker_platform;
GRANT EXECUTE ON FUNCTION app.circuit_allow(text), app.circuit_reset(text) TO daydor_ops, daydor_admin;

RESET ROLE;
