-- Phase A of the agentic infrastructure (docs/agentic-infra-plan.md): the trace spine, and autonomy that does something.
--
-- agent_task_run (in the model since the start, "one row per agent worker execution") is now written: one row per worker
-- job, opened and closed in its own transactions so a failed job still leaves a record, idempotent on the job. It links
-- audit_log, gate_evaluation and approval_request through the agent_task_run_id they already carry.
--
-- Autonomy (auto < review < approve): a tenant may only raise a worker's caution (0026). Now the platform acts on it.
--   approve, above the worker's default  hold the job behind the hard gate g_agent_action (subject: the run), run it
--                                        when a person approves, never if they reject
--   review,  above the worker's default  run it, leave the run 'review_pending' until a person acknowledges it
--   anything else                        as before
-- Workers never write the table directly: they go through these functions, which also stop one worker opening or closing
-- another's run.

SET ROLE daydor_schema_owner;

ALTER TABLE public.agent_task_run
    ADD CONSTRAINT agent_task_run_status_check
    CHECK (status IN ('running', 'succeeded', 'review_pending', 'awaiting_approval', 'rejected', 'failed', 'cancelled'));

-- The gate a held run waits on. Any of the owner roles may decide it; the worker's own owner is named on the request.
INSERT INTO app.gate_definition (gate_id, label, kind, approver_roles, tables, source) VALUES
    ('g_agent_action', 'Agent action held by tenant policy', 'hard',
     ARRAY['tenant_founder', 'tenant_hr', 'tenant_payroll', 'tenant_it', 'daydor_ops']::text[],
     ARRAY['agent_task_run']::text[], 'platform')
ON CONFLICT (gate_id) DO NOTHING;

-- gate.resolved also reaches the agent-run settler, alongside the workflow engine and timekeeping.
INSERT INTO app.subscription (topic, queue, kind) VALUES ('gate.resolved', 'agent-runs', 'agent.gate_resolved')
ON CONFLICT (topic, queue, kind) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Open a run (idempotent) and report what the caller needs to decide how to proceed
-- ---------------------------------------------------------------------------
CREATE FUNCTION app.begin_agent_run(p_worker text, p_key text, p_input_ref text)
RETURNS TABLE (run_id uuid, status text, created boolean, released boolean, effective_autonomy text, default_autonomy text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    d app.worker_definition;
    v_id uuid;
    v_status text;
    v_created boolean := false;
    v_released boolean := false;
BEGIN
    SELECT * INTO d FROM app.worker_definition WHERE worker = p_worker;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'unknown worker %', p_worker USING ERRCODE = 'undefined_object';
    END IF;
    IF app.current_agent_role() IS DISTINCT FROM d.role_name THEN
        RAISE EXCEPTION 'role % may not open a run for %', app.current_agent_role(), p_worker USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF app.tenant_id() IS NULL THEN
        RAISE EXCEPTION 'a worker run needs a tenant' USING ERRCODE = 'check_violation';
    END IF;

    INSERT INTO public.agent_task_run (tenant_id, worker_name, domain, status, idempotency_key, input_ref, started_at)
    VALUES (app.tenant_id(), p_worker, d.home_domain, 'running', p_key, p_input_ref, now())
    ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
    RETURNING id INTO v_id;

    IF v_id IS NOT NULL THEN
        v_created := true;
        v_status := 'running';
    ELSE
        SELECT r.id, r.status INTO v_id, v_status FROM public.agent_task_run r
        WHERE r.tenant_id = app.tenant_id() AND r.idempotency_key = p_key AND r.worker_name = p_worker;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'idempotency key % belongs to another worker', p_key USING ERRCODE = 'check_violation';
        END IF;
        IF v_status = 'awaiting_approval' AND app.agent_run_decision(v_id) = 'approved' THEN
            v_released := true;
        END IF;
        -- A failed or crashed attempt retries; an approved hold is released to run.
        IF v_status IN ('failed', 'running') OR v_released THEN
            UPDATE public.agent_task_run SET status = 'running', started_at = now(), finished_at = NULL, error_code = NULL
            WHERE id = v_id;
            v_status := 'running';
        END IF;
    END IF;
    RETURN QUERY SELECT v_id, v_status, v_created, v_released, app.worker_effective_autonomy(p_worker), d.autonomy;
END $$;

-- What the people said about a held run: 'approved', 'rejected', 'pending', or NULL if it was never held.
CREATE FUNCTION app.agent_run_decision(p_run uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
    SELECT ar.status FROM public.approval_request ar
    WHERE ar.tenant_id = app.tenant_id() AND ar.gate_type = 'g_agent_action'
      AND ar.subject_table = 'agent_task_run' AND ar.subject_id = p_run
$$;

-- ---------------------------------------------------------------------------
-- Close a run
-- ---------------------------------------------------------------------------
CREATE FUNCTION app.finish_agent_run(p_run uuid, p_status text, p_error text DEFAULT NULL, p_approval uuid DEFAULT NULL)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    r public.agent_task_run;
    d app.worker_definition;
BEGIN
    IF p_status NOT IN ('succeeded', 'review_pending', 'awaiting_approval', 'failed') THEN
        RAISE EXCEPTION 'a worker cannot set a run to %', p_status USING ERRCODE = 'check_violation';
    END IF;
    SELECT * INTO r FROM public.agent_task_run WHERE id = p_run AND tenant_id = app.tenant_id();
    IF NOT FOUND THEN
        RAISE EXCEPTION 'run % not found', p_run USING ERRCODE = 'no_data_found';
    END IF;
    SELECT * INTO d FROM app.worker_definition WHERE worker = r.worker_name;
    IF app.current_agent_role() IS DISTINCT FROM d.role_name THEN
        RAISE EXCEPTION 'role % may not close a run of %', app.current_agent_role(), r.worker_name USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF r.status <> 'running' THEN
        RAISE EXCEPTION 'run % is % and cannot be closed from there', p_run, r.status USING ERRCODE = 'check_violation';
    END IF;
    UPDATE public.agent_task_run
       SET status = p_status, finished_at = now(), error_code = left(p_error, 200),
           approval_request_id = coalesce(p_approval, approval_request_id)
     WHERE id = p_run;
END $$;

-- A person looks at what a 'review' run did and accepts it.
CREATE FUNCTION app.acknowledge_agent_run(p_run uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
BEGIN
    UPDATE public.agent_task_run SET status = 'succeeded'
    WHERE id = p_run AND tenant_id = app.tenant_id() AND status = 'review_pending';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'run % is not waiting for review', p_run USING ERRCODE = 'check_violation';
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- A held run's gate was resolved: run it, or stop it. Called by the workflow-engine platform actor on gate.resolved.
-- ---------------------------------------------------------------------------
CREATE FUNCTION app.settle_agent_run(p_approval uuid) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    ar public.approval_request;
    r public.agent_task_run;
    j app.job;
    v_job uuid;
BEGIN
    IF app.current_agent_role() IS DISTINCT FROM 'worker_workflow_engine' THEN
        RAISE EXCEPTION 'only the workflow engine settles held runs' USING ERRCODE = 'insufficient_privilege';
    END IF;
    SELECT * INTO ar FROM public.approval_request
    WHERE id = p_approval AND tenant_id = app.tenant_id() AND gate_type = 'g_agent_action' AND subject_table = 'agent_task_run';
    IF NOT FOUND THEN
        RETURN NULL;                                   -- some other gate
    END IF;
    SELECT * INTO r FROM public.agent_task_run WHERE id = ar.subject_id AND tenant_id = app.tenant_id();
    IF NOT FOUND OR r.status <> 'awaiting_approval' THEN
        RETURN NULL;                                   -- already settled: a duplicate delivery
    END IF;
    IF ar.status = 'rejected' THEN
        UPDATE public.agent_task_run SET status = 'rejected', finished_at = now() WHERE id = r.id;
        RETURN 'rejected';
    END IF;
    IF ar.status <> 'approved' THEN
        RETURN NULL;
    END IF;
    -- Approved: put the same job back on its queue, once, so the handler runs under the same run.
    SELECT * INTO j FROM app.job
    WHERE id = nullif(substring(r.input_ref from '^job:(.*)$'), '')::uuid AND tenant_id = app.tenant_id();
    IF NOT FOUND THEN
        RAISE EXCEPTION 'the job behind run % is gone', r.id USING ERRCODE = 'no_data_found';
    END IF;
    v_job := app.enqueue(j.queue, j.kind, j.payload || jsonb_build_object('agent_run_key', r.idempotency_key),
                         'agent-approved:' || r.id::text);
    RETURN 'approved';
END $$;

-- ---------------------------------------------------------------------------
-- One trace per piece of work: workflow instance, job, run, evaluations, approvals, audit rows, in time order
-- ---------------------------------------------------------------------------
CREATE FUNCTION app.agent_run_trace(p_run uuid)
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

GRANT EXECUTE ON FUNCTION app.begin_agent_run(text, text, text), app.agent_run_decision(uuid),
    app.finish_agent_run(uuid, text, text, uuid), app.settle_agent_run(uuid) TO worker_platform;
GRANT EXECUTE ON FUNCTION app.acknowledge_agent_run(uuid)
    TO tenant_founder, tenant_hr, tenant_payroll, tenant_it, daydor_ops;
GRANT EXECUTE ON FUNCTION app.agent_run_trace(uuid)
    TO daydor_ops, daydor_admin, external_auditor, tenant_founder, tenant_hr, tenant_payroll, tenant_it;

RESET ROLE;
