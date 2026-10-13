-- Platform group for worker roles, role-name functions that know about worker roles, and the PII
-- role check fix (Phase 1, ADR-004). Forward-only on top of 0001, 0006, 0009 and 0011.
--
-- 1. app.current_app_role() collapses worker_* roles to agent_runtime exactly as it does agent_*, so
--    person scope (can_see_employee), masked views and the audit defaults treat a worker as an agent.
-- 2. app.current_agent_role() returns the real worker_* / agent_* role name for the audit trail.
-- 3. BUG FIX: app.encrypt_pii / app.decrypt_pii compared current_app_role() (always 'agent_runtime'
--    for an agent) with registries that list 'agent_hr', 'agent_pay', ... so no agent could ever
--    collect or decrypt PII. They now compare app.current_actor_role(): the real role name (an agent
--    or worker role, or the people role for a human). The registries are re-seeded with worker roles
--    in 0028, alongside the worker roles themselves.
-- 4. worker_platform: what every worker needs regardless of scope (queue, workflow, gate helpers).
--    Model-table grants come only from a worker's own scope (0028). agent_runtime is untouched and
--    keeps its duplicates until the agent_<domain> roles are removed.

SET ROLE daydor_schema_owner;

CREATE OR REPLACE FUNCTION app.current_app_role() RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT CASE WHEN r LIKE 'agent\_%' OR r LIKE 'worker\_%' THEN 'agent_runtime' ELSE r END
    FROM (SELECT coalesce(nullif(current_setting('role', true), 'none'), session_user::text) AS r) s
$$;

CREATE OR REPLACE FUNCTION app.current_agent_role() RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT CASE WHEN r LIKE 'agent\_%' OR r LIKE 'worker\_%' THEN r END
    FROM (SELECT coalesce(nullif(current_setting('role', true), 'none'), session_user::text) AS r) s
$$;

-- The role a caller really switched into: the agent or worker role if there is one, otherwise the
-- people role. Registries of allowed roles (PII collectors, purposes) are written against this.
CREATE FUNCTION app.current_actor_role() RETURNS text
LANGUAGE sql STABLE AS $$ SELECT coalesce(app.current_agent_role(), app.current_app_role()) $$;

CREATE OR REPLACE FUNCTION app.encrypt_pii(p_table text, p_column text, p_row_id uuid, p_plaintext text)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    v_col     app.pii_column%ROWTYPE;
    v_subject uuid;
    v_granted boolean;
    v_rows    int;
BEGIN
    SELECT * INTO v_col FROM app.pii_column WHERE table_name = p_table AND column_name = p_column;
    IF NOT FOUND THEN
        RAISE EXCEPTION '%.% is not a registered PII column', p_table, p_column USING ERRCODE = 'undefined_column';
    END IF;
    IF NOT app.current_actor_role() = ANY (v_col.collect_roles) THEN
        RAISE EXCEPTION 'role % may not collect %.%', app.current_actor_role(), p_table, p_column
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF v_col.requires_consent THEN
        IF v_col.subject_employee_column = 'id' THEN
            v_subject := p_row_id;
        ELSE
            EXECUTE format('SELECT %I FROM public.%I WHERE id = $1 AND tenant_id = $2',
                           v_col.subject_employee_column, p_table)
                INTO v_subject USING p_row_id, app.tenant_id();
        END IF;
        SELECT EXISTS (
            SELECT 1 FROM public.consent_record
            WHERE employee_id = v_subject AND data_category = v_col.data_category
              AND tenant_id = app.tenant_id() AND status = 'granted' AND withdrawn_at IS NULL
        ) INTO v_granted;
        IF NOT v_granted THEN
            RAISE EXCEPTION 'no active consent for % on employee %', v_col.data_category, v_subject
                USING ERRCODE = 'insufficient_privilege';
        END IF;
    END IF;

    EXECUTE format('UPDATE public.%I SET %I = $1 WHERE id = $2 AND tenant_id = $3',
                   p_table, p_column)
        USING pgp_sym_encrypt(p_plaintext, app.pii_key(app.tenant_id()), 'cipher-algo=aes256'),
              p_row_id, app.tenant_id();
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    IF v_rows = 0 THEN
        RAISE EXCEPTION '% % not found', p_table, p_row_id USING ERRCODE = 'no_data_found';
    END IF;

    INSERT INTO public.audit_log (actor_user_id, actor_kind, agent_task_run_id, event_type,
        subject_table, subject_id, occurred_at)
    VALUES (app.user_id(), CASE WHEN app.current_agent_role() IS NULL THEN 'human' ELSE 'agent' END,
            app.agent_task_run_id(), 'pii.collected', p_table, p_row_id, now());
END $$;

CREATE OR REPLACE FUNCTION app.decrypt_pii(p_table text, p_column text, p_row_id uuid, p_purpose text)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    v_col     app.pii_column%ROWTYPE;
    v_purpose app.pii_purpose%ROWTYPE;
    v_cipher  bytea;
    v_tenant  uuid;
    v_subject uuid;
    v_granted boolean;
    v_plain   text;
BEGIN
    SELECT * INTO v_col FROM app.pii_column WHERE table_name = p_table AND column_name = p_column;
    IF NOT FOUND THEN
        RAISE EXCEPTION '%.% is not a registered PII column', p_table, p_column USING ERRCODE = 'undefined_column';
    END IF;

    SELECT * INTO v_purpose FROM app.pii_purpose WHERE purpose = p_purpose;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'unknown purpose %', p_purpose USING ERRCODE = 'check_violation';
    END IF;
    IF NOT app.current_actor_role() = ANY (v_purpose.allowed_roles) THEN
        RAISE EXCEPTION 'role % may not decrypt PII for purpose %', app.current_actor_role(), p_purpose
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF v_col.data_category IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM app.pii_purpose_scope WHERE purpose = p_purpose AND data_category = v_col.data_category
    ) THEN
        RAISE EXCEPTION 'purpose % does not cover %', p_purpose, v_col.data_category
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    EXECUTE format('SELECT %I, tenant_id FROM public.%I WHERE id = $1', p_column, p_table)
        INTO v_cipher, v_tenant USING p_row_id;
    IF NOT FOUND OR v_tenant IS NULL THEN
        RAISE EXCEPTION '% % not found', p_table, p_row_id USING ERRCODE = 'no_data_found';
    END IF;

    IF v_col.requires_consent THEN
        v_subject := CASE WHEN v_col.subject_employee_column = 'id' THEN p_row_id ELSE NULL END;
        IF v_subject IS NULL THEN
            EXECUTE format('SELECT %I FROM public.%I WHERE id = $1', v_col.subject_employee_column, p_table)
                INTO v_subject USING p_row_id;
        END IF;
        SELECT EXISTS (
            SELECT 1 FROM public.consent_record
            WHERE employee_id = v_subject AND data_category = v_col.data_category
              AND tenant_id = v_tenant AND status = 'granted' AND withdrawn_at IS NULL
        ) INTO v_granted;
        IF NOT v_granted THEN
            RAISE EXCEPTION 'no active consent for % on employee %', v_col.data_category, v_subject
                USING ERRCODE = 'insufficient_privilege';
        END IF;
    END IF;

    IF v_cipher IS NOT NULL THEN
        v_plain := pgp_sym_decrypt(v_cipher, app.pii_key(v_tenant));
    END IF;

    INSERT INTO public.audit_log (actor_user_id, actor_kind, agent_task_run_id, event_type,
        subject_table, subject_id, occurred_at)
    VALUES (app.user_id(), CASE WHEN app.current_agent_role() IS NULL THEN 'human' ELSE 'agent' END,
            app.agent_task_run_id(), 'pii.decrypted', p_table, p_row_id, now());

    RETURN v_plain;
END $$;

GRANT EXECUTE ON FUNCTION app.current_actor_role()
    TO daydor_admin, daydor_ops, tenant_founder, tenant_hr, tenant_payroll, tenant_it,
       tenant_manager, tenant_employee, external_auditor, agent_runtime, daydor_worker, worker_platform;

-- ---------------------------------------------------------------------------
-- worker_platform
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO worker_platform;

GRANT EXECUTE ON FUNCTION app.setting_uuid(text), app.tenant_id(), app.user_id(), app.employee_id(),
    app.agent_task_run_id(), app.purpose(), app.current_app_role(), app.current_agent_role(),
    app.is_daydor_staff(), app.can_see_employee(uuid)
    TO worker_platform;
-- Queue, timers and calendars: how a job enqueues follow-on work and schedules a deadline.
GRANT EXECUTE ON FUNCTION
    app.enqueue(text, text, jsonb, text, timestamptz, integer, integer),
    app.emit_event(text, text, uuid, jsonb),
    app.schedule_timer(text, text, text, timestamptz, jsonb),
    app.cancel_timer(text),
    app.add_business_days(date, integer, text),
    app.is_business_day(date, text)
    TO worker_platform;
-- Approvals: the approval_request insert trigger looks up the gate's allowed approver roles.
GRANT EXECUTE ON FUNCTION app.approval_allowed_roles(text, text) TO worker_platform;
-- Soft gates: run and log an evaluation.
GRANT EXECUTE ON FUNCTION app.record_gate_evaluation(text, text, uuid, text, text, text, text, text[],
    jsonb, numeric, text, integer, text, uuid) TO worker_platform;
GRANT SELECT ON app.gate_definition, app.gate_evaluation, app.gate_guard, app.holiday TO worker_platform;

-- Workflow: every handler that advances a state machine reads definitions and writes instances.
GRANT SELECT ON app.workflow_definition TO worker_platform;
GRANT SELECT, INSERT ON app.workflow_instance, app.workflow_transition TO worker_platform;
GRANT UPDATE (state, status, pending_event, waiting_on_approval, context, version)
    ON app.workflow_instance TO worker_platform;

RESET ROLE;
