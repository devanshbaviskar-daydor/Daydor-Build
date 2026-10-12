-- Gate service.
--
-- Hard gates: human approvals recorded in public.approval_request. The database enforces:
--   * only a role listed for the gate can resolve it, and only through app.resolve_approval
--   * maker-checker: whoever raised the request cannot resolve it
--   * resolved requests are immutable
--   * guarded writes (e.g. setting payroll_run.disbursed_at) need an approved request for that row
-- Soft gates: automated pre-checks (Jev). Every evaluation is logged append-only in
-- app.gate_evaluation. A soft gate can only remove an extra review step; it never resolves a hard gate.

SET ROLE daydor_schema_owner;

CREATE TABLE app.gate_definition (
    gate_id              text PRIMARY KEY,
    label                text NOT NULL,
    kind                 text NOT NULL CHECK (kind IN ('hard', 'soft')),
    approver_roles       text[] NOT NULL DEFAULT '{}',          -- hard gates
    tables               text[] NOT NULL DEFAULT '{}',
    source               text NOT NULL,                         -- graph | doc | platform
    -- soft gates
    escalate_to          text REFERENCES app.gate_definition(gate_id),
    mode                 text CHECK (mode IN ('shadow', 'enforce')),
    auto_pass_threshold  numeric CHECK (auto_pass_threshold > 0 AND auto_pass_threshold <= 1),
    max_input_class      text CHECK (max_input_class IN ('S', 'C0', 'C1', 'C2')),   -- never C3/C4
    reversible           boolean NOT NULL DEFAULT false,
    CHECK (kind = 'hard' OR (escalate_to IS NOT NULL AND mode IS NOT NULL
                             AND auto_pass_threshold IS NOT NULL AND max_input_class IS NOT NULL
                             AND reversible)),
    CHECK (kind = 'soft' OR cardinality(approver_roles) > 0)
);

-- Writes that need an approved hard gate on the same row: setting guard_column from NULL to a
-- value requires NEW.approval_request_id to point at an approved request for one of gate_ids.
CREATE TABLE app.gate_guard (
    table_name    text NOT NULL,
    guard_column  text NOT NULL,
    gate_ids      text[] NOT NULL,
    PRIMARY KEY (table_name, guard_column)
);

CREATE TABLE app.gate_evaluation (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            uuid NOT NULL DEFAULT app.tenant_id(),
    gate_id              text NOT NULL REFERENCES app.gate_definition(gate_id),
    subject_table        text NOT NULL,
    subject_id           uuid NOT NULL,
    engine               text NOT NULL,                 -- 'jev'
    engine_version       text,
    schema_version       text NOT NULL,
    input_hash           text NOT NULL,                 -- sha256 of canonical input; inputs not stored
    input_columns        text[] NOT NULL,
    output               jsonb,                         -- typed values + probabilities
    confidence           numeric,
    threshold            numeric NOT NULL,
    model_decision       text NOT NULL CHECK (model_decision IN ('pass', 'escalate', 'error')),
    effective_decision   text NOT NULL CHECK (effective_decision IN ('pass', 'escalate')),
    mode                 text NOT NULL CHECK (mode IN ('shadow', 'enforce')),
    latency_ms           integer,
    error                text,
    approval_request_id  uuid REFERENCES public.approval_request(id),
    agent_task_run_id    uuid DEFAULT app.agent_task_run_id(),
    created_at           timestamptz NOT NULL DEFAULT now(),
    -- fail closed: errors always escalate, and shadow mode never auto-passes
    CHECK (model_decision <> 'error' OR effective_decision = 'escalate'),
    CHECK (mode <> 'shadow' OR effective_decision = 'escalate')
);
CREATE INDEX gate_evaluation_subject_idx ON app.gate_evaluation (tenant_id, subject_table, subject_id);
CREATE INDEX gate_evaluation_gate_idx ON app.gate_evaluation (gate_id, created_at);
ALTER TABLE app.gate_evaluation ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.gate_evaluation FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON app.gate_evaluation
    USING (tenant_id = app.tenant_id()) WITH CHECK (tenant_id = app.tenant_id());
CREATE TRIGGER gate_evaluation_append_only BEFORE UPDATE OR DELETE ON app.gate_evaluation
    FOR EACH ROW EXECUTE FUNCTION app.reject_mutation();

-- ---------------------------------------------------------------------------
-- approval_request enforcement
-- ---------------------------------------------------------------------------
CREATE FUNCTION app.approval_allowed_roles(p_gate text, p_required text) RETURNS text[]
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, pg_temp AS $$
    SELECT coalesce((SELECT approver_roles FROM app.gate_definition
                     WHERE gate_id = p_gate AND kind = 'hard'),
                    CASE WHEN p_required IS NULL THEN '{}'::text[] ELSE ARRAY[p_required] END)
$$;

CREATE FUNCTION app.approval_request_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = app, public, pg_temp AS $$
DECLARE
    allowed text[];
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status IS DISTINCT FROM 'pending' THEN
            RAISE EXCEPTION 'approval requests are created pending' USING ERRCODE = 'check_violation';
        END IF;
        allowed := app.approval_allowed_roles(NEW.gate_type, NEW.required_approver_role);
        IF cardinality(allowed) = 0 THEN
            RAISE EXCEPTION 'unknown gate % and no approver role given', NEW.gate_type
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.required_approver_role IS NULL THEN
            NEW.required_approver_role := allowed[1];
        ELSIF NOT NEW.required_approver_role = ANY (allowed) THEN
            RAISE EXCEPTION 'role % cannot approve gate %', NEW.required_approver_role, NEW.gate_type
                USING ERRCODE = 'check_violation';
        END IF;
        -- the maker is whoever raised it, taken from the session, never from the caller's input
        NEW.requested_by_user_id := app.user_id();
        NEW.requested_by_agent_run_id := app.agent_task_run_id();
        NEW.resolved_by_user_id := NULL;
        NEW.resolved_at := NULL;
        RETURN NEW;
    END IF;

    -- UPDATE
    IF OLD.status IN ('approved', 'rejected', 'expired') THEN
        RAISE EXCEPTION 'approval request % is already %', OLD.id, OLD.status
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF (NEW.gate_type, NEW.subject_table, NEW.subject_id, NEW.requested_by_user_id,
        NEW.requested_by_agent_run_id, NEW.tenant_id)
       IS DISTINCT FROM (OLD.gate_type, OLD.subject_table, OLD.subject_id, OLD.requested_by_user_id,
                         OLD.requested_by_agent_run_id, OLD.tenant_id) THEN
        RAISE EXCEPTION 'gate, subject and maker of an approval request cannot change'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.status IN ('approved', 'rejected') AND NEW.status IS DISTINCT FROM OLD.status THEN
        IF current_setting('app.resolving', true) IS DISTINCT FROM 'on' THEN
            RAISE EXCEPTION 'resolve approvals with app.resolve_approval()'
                USING ERRCODE = 'insufficient_privilege';
        END IF;
        allowed := app.approval_allowed_roles(OLD.gate_type, OLD.required_approver_role);
        IF NOT app.current_app_role() = ANY (allowed) THEN
            RAISE EXCEPTION 'role % cannot resolve gate % (allowed: %)', app.current_app_role(),
                OLD.gate_type, allowed USING ERRCODE = 'insufficient_privilege';
        END IF;
        IF app.user_id() IS NULL THEN
            RAISE EXCEPTION 'resolving an approval needs a signed-in user'
                USING ERRCODE = 'insufficient_privilege';
        END IF;
        IF app.user_id() = OLD.requested_by_user_id THEN
            RAISE EXCEPTION 'maker-checker: the requester cannot resolve their own request'
                USING ERRCODE = 'insufficient_privilege';
        END IF;
        NEW.resolved_by_user_id := app.user_id();
        NEW.resolved_at := now();
    ELSIF NEW.resolved_by_user_id IS DISTINCT FROM OLD.resolved_by_user_id
       OR NEW.resolved_at IS DISTINCT FROM OLD.resolved_at THEN
        RAISE EXCEPTION 'resolver fields are set by the database' USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER approval_request_guard BEFORE INSERT OR UPDATE ON public.approval_request
    FOR EACH ROW EXECUTE FUNCTION app.approval_request_guard();

-- The supported way to approve or reject. SECURITY DEFINER, but app.current_app_role() still
-- reports the caller's role (it reads the "role" setting), so the trigger checks the real
-- resolver. app.resolving is API hygiene only: the trigger's role and maker-checker checks are
-- the actual protection and apply however the update arrives.
CREATE FUNCTION app.resolve_approval(p_request uuid, p_decision text, p_note text DEFAULT NULL)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    v_status text;
    v_gate text;
    v_subject_table text;
    v_subject uuid;
BEGIN
    IF p_decision NOT IN ('approved', 'rejected') THEN
        RAISE EXCEPTION 'decision must be approved or rejected' USING ERRCODE = 'check_violation';
    END IF;
    PERFORM set_config('app.resolving', 'on', true);
    UPDATE public.approval_request
    SET status = p_decision, decision_note = p_note
    WHERE id = p_request AND tenant_id = app.tenant_id()
    RETURNING status, gate_type, subject_table, subject_id
    INTO v_status, v_gate, v_subject_table, v_subject;
    PERFORM set_config('app.resolving', 'off', true);
    IF v_status IS NULL THEN
        RAISE EXCEPTION 'approval request % not found', p_request USING ERRCODE = 'no_data_found';
    END IF;
    PERFORM app.emit_event('gate.resolved', v_subject_table, v_subject,
                           jsonb_build_object('approval_request_id', p_request, 'gate_id', v_gate,
                                              'decision', p_decision));
    RETURN v_status;
END $$;

-- ---------------------------------------------------------------------------
-- Guarded writes
-- ---------------------------------------------------------------------------
CREATE FUNCTION app.enforce_gate_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    g record;
    new_row jsonb := to_jsonb(NEW);
    old_row jsonb := CASE WHEN TG_OP = 'UPDATE' THEN to_jsonb(OLD) ELSE '{}'::jsonb END;
BEGIN
    FOR g IN SELECT * FROM app.gate_guard WHERE table_name = TG_TABLE_NAME LOOP
        IF new_row ->> g.guard_column IS NOT NULL AND old_row ->> g.guard_column IS NULL THEN
            IF NOT EXISTS (
                SELECT 1 FROM public.approval_request ar
                WHERE ar.id = (new_row ->> 'approval_request_id')::uuid
                  AND ar.tenant_id = NEW.tenant_id
                  AND ar.status = 'approved'
                  AND ar.gate_type = ANY (g.gate_ids)
                  AND ar.subject_table = TG_TABLE_NAME
                  AND ar.subject_id = NEW.id
            ) THEN
                RAISE EXCEPTION 'setting %.% needs an approved % gate for this row',
                    TG_TABLE_NAME, g.guard_column, array_to_string(g.gate_ids, ' or ')
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
        END IF;
        IF old_row ->> g.guard_column IS NOT NULL
           AND (new_row ->> g.guard_column) IS DISTINCT FROM (old_row ->> g.guard_column) THEN
            RAISE EXCEPTION '%.% is final once set', TG_TABLE_NAME, g.guard_column
                USING ERRCODE = 'insufficient_privilege';
        END IF;
    END LOOP;
    RETURN NEW;
END $$;

-- ---------------------------------------------------------------------------
-- Soft-gate evaluation log (written by the soft-gate runner)
-- ---------------------------------------------------------------------------
CREATE FUNCTION app.record_gate_evaluation(
    p_gate text, p_subject_table text, p_subject_id uuid, p_engine text, p_engine_version text,
    p_schema_version text, p_input_hash text, p_input_columns text[], p_output jsonb,
    p_confidence numeric, p_model_decision text, p_latency_ms integer, p_error text,
    p_approval_request uuid DEFAULT NULL)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS $$
DECLARE
    d app.gate_definition;
    v_effective text;
    v_id uuid;
BEGIN
    SELECT * INTO d FROM app.gate_definition WHERE gate_id = p_gate AND kind = 'soft';
    IF NOT FOUND THEN
        RAISE EXCEPTION '% is not a soft gate', p_gate USING ERRCODE = 'check_violation';
    END IF;
    -- The database decides the effective outcome, so a caller cannot log a pass the rules forbid.
    v_effective := CASE
        WHEN d.mode = 'shadow' THEN 'escalate'
        WHEN p_model_decision = 'pass' AND p_confidence >= d.auto_pass_threshold THEN 'pass'
        ELSE 'escalate' END;
    INSERT INTO app.gate_evaluation (gate_id, subject_table, subject_id, engine, engine_version,
        schema_version, input_hash, input_columns, output, confidence, threshold, model_decision,
        effective_decision, mode, latency_ms, error, approval_request_id)
    VALUES (p_gate, p_subject_table, p_subject_id, p_engine, p_engine_version, p_schema_version,
        p_input_hash, p_input_columns, p_output, p_confidence, d.auto_pass_threshold, p_model_decision,
        v_effective, d.mode, p_latency_ms, p_error, p_approval_request)
    RETURNING id INTO v_id;
    RETURN v_id;
END $$;

GRANT SELECT ON app.gate_definition, app.gate_guard TO daydor_ops, tenant_founder, tenant_hr,
    tenant_payroll, tenant_it, tenant_manager, external_auditor, agent_runtime;
GRANT SELECT ON app.gate_evaluation TO daydor_ops, tenant_founder, tenant_hr, tenant_payroll,
    external_auditor, agent_runtime;
GRANT EXECUTE ON FUNCTION app.resolve_approval(uuid, text, text)
    TO daydor_ops, tenant_founder, tenant_hr, tenant_payroll, tenant_it, tenant_manager, tenant_employee;
GRANT EXECUTE ON FUNCTION app.record_gate_evaluation(text, text, uuid, text, text, text, text, text[],
    jsonb, numeric, text, integer, text, uuid) TO agent_runtime;
GRANT EXECUTE ON FUNCTION app.approval_allowed_roles(text, text) TO daydor_ops, tenant_founder,
    tenant_hr, tenant_payroll, tenant_it, tenant_manager, tenant_employee, agent_runtime;
-- The guard trigger raises a gate.requested event via app.emit_event in the Python layer.

RESET ROLE;
