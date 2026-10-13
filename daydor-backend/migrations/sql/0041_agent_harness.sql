-- Phase B of the agentic infrastructure (docs/agentic-infra-plan.md): what the LLM runtime needs from the database.
--
--   1. Review that blocks. A run left `review_pending` (0040) now also holds the jobs its handler enqueued, so the next step of a
--      workflow does not start until a person acknowledges the run. Rejecting it cancels them.
--   2. app.agent_proposal: the typed proposal a model produced, whether it validated, and whether it was committed. One per run, so a
--      retried or released job reuses it instead of asking the model again.
--   3. app.agent_model_call: every model call a run made (model, prompt version, tokens, cost, latency, which tools), append-only.
-- Workers reach 2 and 3 only through functions that check the run is theirs.

SET ROLE daydor_schema_owner;

-- ---------------------------------------------------------------------------
-- 1. Review blocks the next step
-- ---------------------------------------------------------------------------
ALTER TABLE app.job ADD COLUMN hold_run uuid;
ALTER TABLE app.job DROP CONSTRAINT job_status_check;
ALTER TABLE app.job ADD CONSTRAINT job_status_check
    CHECK (status IN ('queued', 'running', 'succeeded', 'dead', 'cancelled', 'held'));
CREATE INDEX job_hold_idx ON app.job (hold_run) WHERE status = 'held';

-- While a handler runs under review, the worker sets app.agent_review_hold to its run; every job enqueued in that session is held
-- (never claimed) until the run is acknowledged.
CREATE OR REPLACE FUNCTION app.enqueue(p_queue text, p_kind text, p_payload jsonb DEFAULT '{}',
                                       p_idempotency_key text DEFAULT NULL, p_run_at timestamptz DEFAULT now(),
                                       p_max_attempts integer DEFAULT 5, p_priority integer DEFAULT 100)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS $$
DECLARE
    v_id uuid;
    v_hold uuid := app.setting_uuid('app.agent_review_hold');
BEGIN
    INSERT INTO app.job (tenant_id, queue, kind, payload, idempotency_key, run_at, max_attempts, priority, status, hold_run)
    VALUES (app.tenant_id(), p_queue, p_kind, p_payload, p_idempotency_key, p_run_at, p_max_attempts, p_priority,
            CASE WHEN v_hold IS NULL THEN 'queued' ELSE 'held' END, v_hold)
    ON CONFLICT DO NOTHING
    RETURNING id INTO v_id;
    IF v_id IS NULL THEN   -- duplicate idempotency key: return the existing job
        SELECT id INTO v_id FROM app.job
        WHERE coalesce(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid)
              = coalesce(app.tenant_id(), '00000000-0000-0000-0000-000000000000'::uuid)
          AND idempotency_key = p_idempotency_key;
    END IF;
    RETURN v_id;
END $$;

CREATE OR REPLACE FUNCTION app.acknowledge_agent_run(p_run uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
BEGIN
    UPDATE public.agent_task_run SET status = 'succeeded'
    WHERE id = p_run AND tenant_id = app.tenant_id() AND status = 'review_pending';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'run % is not waiting for review', p_run USING ERRCODE = 'check_violation';
    END IF;
    UPDATE app.job SET status = 'queued', hold_run = NULL, run_at = now()
    WHERE hold_run = p_run AND tenant_id = app.tenant_id() AND status = 'held';
END $$;

-- A person looked at what the worker did and does not accept it: the run is rejected and what it set in motion is cancelled.
-- Undoing the worker's own writes is a person's job; this stops the workflow from moving on from them.
CREATE FUNCTION app.reject_agent_run(p_run uuid) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    n integer;
BEGIN
    UPDATE public.agent_task_run SET status = 'rejected', finished_at = now()
    WHERE id = p_run AND tenant_id = app.tenant_id() AND status = 'review_pending';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'run % is not waiting for review', p_run USING ERRCODE = 'check_violation';
    END IF;
    UPDATE app.job SET status = 'cancelled', finished_at = now()
    WHERE hold_run = p_run AND tenant_id = app.tenant_id() AND status = 'held';
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END $$;
GRANT EXECUTE ON FUNCTION app.reject_agent_run(uuid) TO tenant_founder, tenant_hr, tenant_payroll, tenant_it, daydor_ops;

-- ---------------------------------------------------------------------------
-- 2. Proposals
-- ---------------------------------------------------------------------------
CREATE TABLE app.agent_proposal (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL DEFAULT app.tenant_id(),
    run_id          uuid NOT NULL UNIQUE REFERENCES public.agent_task_run (id),
    worker          text NOT NULL REFERENCES app.worker_definition (worker),
    prompt_version  text NOT NULL,
    schema_name     text NOT NULL,
    proposal        jsonb NOT NULL,
    valid           boolean NOT NULL,
    errors          jsonb NOT NULL DEFAULT '[]',
    status          text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'committed', 'discarded')),
    created_at      timestamptz NOT NULL DEFAULT now(),
    committed_at    timestamptz,
    CHECK ((status = 'committed') = (committed_at IS NOT NULL)),
    CHECK (status <> 'committed' OR valid)               -- an invalid proposal is never committed
);
ALTER TABLE app.agent_proposal ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.agent_proposal FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON app.agent_proposal
    USING (tenant_id = app.tenant_id()) WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT ON app.agent_proposal TO daydor_ops, daydor_admin, external_auditor, tenant_founder, tenant_hr, tenant_payroll, tenant_it;

-- A worker's own-run check, shared by the functions below.
CREATE FUNCTION app.assert_own_run(p_run uuid) RETURNS text
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    r public.agent_task_run;
    d app.worker_definition;
BEGIN
    SELECT * INTO r FROM public.agent_task_run WHERE id = p_run AND tenant_id = app.tenant_id();
    IF NOT FOUND THEN
        RAISE EXCEPTION 'run % not found', p_run USING ERRCODE = 'no_data_found';
    END IF;
    SELECT * INTO d FROM app.worker_definition WHERE worker = r.worker_name;
    IF app.current_agent_role() IS DISTINCT FROM d.role_name THEN
        RAISE EXCEPTION 'role % does not own run %', app.current_agent_role(), p_run USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN r.worker_name;
END $$;

CREATE FUNCTION app.store_agent_proposal(p_run uuid, p_prompt_version text, p_schema text, p_proposal jsonb,
                                         p_valid boolean, p_errors jsonb DEFAULT '[]') RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    v_worker text := app.assert_own_run(p_run);
    v_id uuid;
BEGIN
    -- A retry may replace an invalid proposal; a valid one, or a committed one, is never overwritten.
    INSERT INTO app.agent_proposal (run_id, worker, prompt_version, schema_name, proposal, valid, errors)
    VALUES (p_run, v_worker, p_prompt_version, p_schema, p_proposal, p_valid, p_errors)
    ON CONFLICT (run_id) DO UPDATE
        SET prompt_version = EXCLUDED.prompt_version, schema_name = EXCLUDED.schema_name, proposal = EXCLUDED.proposal,
            valid = EXCLUDED.valid, errors = EXCLUDED.errors
        WHERE NOT app.agent_proposal.valid AND app.agent_proposal.status = 'proposed'
    RETURNING id INTO v_id;
    IF v_id IS NULL THEN
        SELECT id INTO v_id FROM app.agent_proposal WHERE run_id = p_run;
    END IF;
    RETURN v_id;
END $$;

CREATE FUNCTION app.agent_proposal_for(p_run uuid)
RETURNS TABLE (id uuid, prompt_version text, schema_name text, proposal jsonb, valid boolean, errors jsonb, status text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
BEGIN
    PERFORM app.assert_own_run(p_run);
    RETURN QUERY SELECT ap.id, ap.prompt_version, ap.schema_name, ap.proposal, ap.valid, ap.errors, ap.status
                 FROM app.agent_proposal ap WHERE ap.run_id = p_run AND ap.tenant_id = app.tenant_id();
END $$;

CREATE FUNCTION app.mark_agent_proposal(p_run uuid, p_status text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
BEGIN
    PERFORM app.assert_own_run(p_run);
    IF p_status NOT IN ('committed', 'discarded') THEN
        RAISE EXCEPTION 'a proposal can only become committed or discarded' USING ERRCODE = 'check_violation';
    END IF;
    UPDATE app.agent_proposal SET status = p_status, committed_at = CASE WHEN p_status = 'committed' THEN now() END
    WHERE run_id = p_run AND tenant_id = app.tenant_id() AND status = 'proposed';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no open proposal for run %', p_run USING ERRCODE = 'no_data_found';
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 3. Model calls
-- ---------------------------------------------------------------------------
CREATE TABLE app.agent_model_call (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL DEFAULT app.tenant_id(),
    run_id          uuid NOT NULL REFERENCES public.agent_task_run (id),
    turn            integer NOT NULL CHECK (turn >= 1),
    model           text NOT NULL,
    prompt_version  text NOT NULL,
    input_tokens    integer NOT NULL CHECK (input_tokens >= 0),
    output_tokens   integer NOT NULL CHECK (output_tokens >= 0),
    cost_usd        numeric,                                 -- NULL when no price is configured for the model
    latency_ms      integer,
    stop_reason     text,
    tool_names      text[] NOT NULL DEFAULT '{}',
    error           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, turn)
);
CREATE INDEX agent_model_call_run_idx ON app.agent_model_call (run_id);
ALTER TABLE app.agent_model_call ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.agent_model_call FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON app.agent_model_call
    USING (tenant_id = app.tenant_id()) WITH CHECK (tenant_id = app.tenant_id());
CREATE TRIGGER agent_model_call_append_only BEFORE UPDATE OR DELETE ON app.agent_model_call
    FOR EACH ROW EXECUTE FUNCTION app.reject_mutation();
GRANT SELECT ON app.agent_model_call TO daydor_ops, daydor_admin, external_auditor, tenant_founder;

CREATE FUNCTION app.record_agent_model_call(p_run uuid, p_turn integer, p_model text, p_prompt_version text,
        p_input_tokens integer, p_output_tokens integer, p_cost_usd numeric, p_latency_ms integer,
        p_stop_reason text, p_tool_names text[], p_error text DEFAULT NULL) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    v_id uuid;
BEGIN
    PERFORM app.assert_own_run(p_run);
    INSERT INTO app.agent_model_call (run_id, turn, model, prompt_version, input_tokens, output_tokens, cost_usd, latency_ms,
                                      stop_reason, tool_names, error)
    VALUES (p_run, p_turn, p_model, p_prompt_version, p_input_tokens, p_output_tokens, p_cost_usd, p_latency_ms,
            p_stop_reason, coalesce(p_tool_names, '{}'), left(p_error, 500))
    ON CONFLICT (run_id, turn) DO NOTHING
    RETURNING id INTO v_id;
    RETURN v_id;
END $$;

-- What a run has spent so far, across every attempt, so budgets hold over retries.
CREATE FUNCTION app.agent_run_usage(p_run uuid)
RETURNS TABLE (turns integer, input_tokens bigint, output_tokens bigint, cost_usd numeric)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
BEGIN
    PERFORM app.assert_own_run(p_run);
    RETURN QUERY SELECT coalesce(max(mc.turn), 0)::integer, coalesce(sum(mc.input_tokens), 0)::bigint,
                        coalesce(sum(mc.output_tokens), 0)::bigint, coalesce(sum(mc.cost_usd), 0)
                 FROM app.agent_model_call mc WHERE mc.run_id = p_run AND mc.tenant_id = app.tenant_id();
END $$;

GRANT EXECUTE ON FUNCTION app.agent_run_usage(uuid) TO worker_platform;
GRANT EXECUTE ON FUNCTION app.store_agent_proposal(uuid, text, text, jsonb, boolean, jsonb), app.agent_proposal_for(uuid),
    app.mark_agent_proposal(uuid, text), app.record_agent_model_call(uuid, integer, text, text, integer, integer, numeric,
    integer, text, text[], text) TO worker_platform;

-- The trace now includes the proposal and the model calls.
CREATE OR REPLACE FUNCTION app.agent_run_trace(p_run uuid)
RETURNS TABLE (at timestamptz, kind text, ref text, detail jsonb)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
    WITH r AS (SELECT * FROM public.agent_task_run WHERE id = p_run AND tenant_id = app.tenant_id()),
         j AS (SELECT jb.* FROM app.job jb, r WHERE jb.id = nullif(substring(r.input_ref from '^job:(.*)$'), '')::uuid
                                                    AND jb.tenant_id = app.tenant_id())
    SELECT r.started_at, 'run', r.id::text,
           jsonb_build_object('worker', r.worker_name, 'status', r.status, 'domain', r.domain, 'error', r.error_code) FROM r
    UNION ALL
    SELECT j.created_at, 'job', j.id::text,
           jsonb_build_object('queue', j.queue, 'kind', j.kind, 'status', j.status, 'attempts', j.attempts) FROM j
    UNION ALL
    SELECT wi.created_at, 'workflow_instance', wi.id::text,
           jsonb_build_object('definition', wi.definition_name, 'version', wi.definition_version, 'state', wi.state, 'status', wi.status)
    FROM app.workflow_instance wi, j
    WHERE wi.id = nullif(j.payload ->> 'workflow_instance_id', '')::uuid AND wi.tenant_id = app.tenant_id()
    UNION ALL
    SELECT mc.created_at, 'model_call', mc.id::text,
           jsonb_build_object('turn', mc.turn, 'model', mc.model, 'prompt_version', mc.prompt_version, 'input_tokens', mc.input_tokens,
                              'output_tokens', mc.output_tokens, 'cost_usd', mc.cost_usd, 'tools', mc.tool_names, 'stop', mc.stop_reason)
    FROM app.agent_model_call mc WHERE mc.run_id = p_run AND mc.tenant_id = app.tenant_id()
    UNION ALL
    SELECT ap.created_at, 'proposal', ap.id::text,
           jsonb_build_object('schema', ap.schema_name, 'valid', ap.valid, 'status', ap.status, 'prompt_version', ap.prompt_version)
    FROM app.agent_proposal ap WHERE ap.run_id = p_run AND ap.tenant_id = app.tenant_id()
    UNION ALL
    SELECT ge.created_at, 'gate_evaluation', ge.id::text,
           jsonb_build_object('gate', ge.gate_id, 'model_decision', ge.model_decision, 'effective', ge.effective_decision)
    FROM app.gate_evaluation ge WHERE ge.agent_task_run_id = p_run AND ge.tenant_id = app.tenant_id()
    UNION ALL
    SELECT ar.created_at, 'approval_request', ar.id::text,
           jsonb_build_object('gate', ar.gate_type, 'status', ar.status, 'subject', ar.subject_table)
    FROM public.approval_request ar
    WHERE ar.tenant_id = app.tenant_id()
      AND ((ar.subject_table = 'agent_task_run' AND ar.subject_id = p_run) OR ar.id IN (SELECT approval_request_id FROM r))
    UNION ALL
    SELECT al.occurred_at, 'audit', al.id::text,
           jsonb_build_object('event', al.event_type, 'subject_table', al.subject_table, 'actor_kind', al.actor_kind)
    FROM public.audit_log al WHERE al.agent_task_run_id = p_run AND al.tenant_id = app.tenant_id()
    ORDER BY 1, 2
$$;

RESET ROLE;
