-- Sprint 13: the data plumbing that lets a soft gate earn enforcement (ADR-005, ADR-006).
--
--   1. app.gate_shadow_outcome   each evaluation paired with the human's decision on the hard gate it escalated to
--   2. app.gate_example          opt-in, per-gate, retention-limited store of the inputs behind an evaluation,
--                                labelled from the human outcome; ops and admin read it, nobody else
--   3. app.tenant_training_policy  no pooling across tenants unless a tenant has opted in (ADR-006)
--   4. app.gate_calibration      a fitted calibration and its evidence; 'approved' needs the promotion criteria
--                                (docs/backend-plan.md), checked by the database, and a named sign-off
--   5. a trigger so a soft gate can only enforce on an approved calibration of its own
--
-- Nothing here changes a gate's mode. store_examples is false everywhere, so no input is stored until a
-- gate is switched on in a reviewed migration.

SET ROLE daydor_schema_owner;

-- ---------------------------------------------------------------------------
-- 1. Shadow outcome: model versus human
-- ---------------------------------------------------------------------------
-- The runner records the evaluation and then opens the hard gate, so the link is the gate and the subject
-- (the same key request_approval uses), not a column on the append-only evaluation row. human_label is the
-- decision that turned out to be right: a human who approved shows the model's pass was fine ('pass'); one who
-- rejected shows the row needed review ('escalate'). Pending and expired requests are unlabelled.
CREATE VIEW app.gate_shadow_outcome WITH (security_invoker = true) AS
SELECT ge.id AS evaluation_id, ge.tenant_id, ge.gate_id, ge.subject_table, ge.subject_id, ge.created_at,
       ge.mode, ge.model_decision, ge.effective_decision, ge.confidence, ge.threshold, ge.engine,
       ge.engine_version, ge.calibration_version, ge.latency_ms, ge.error, ge.output,
       ar.id AS approval_request_id, ar.status AS human_status, ar.resolved_at,
       CASE ar.status WHEN 'approved' THEN 'pass' WHEN 'rejected' THEN 'escalate' END AS human_label
FROM app.gate_evaluation ge
JOIN app.gate_definition gd ON gd.gate_id = ge.gate_id
LEFT JOIN public.approval_request ar
       ON ar.gate_type = gd.escalate_to AND ar.subject_table = ge.subject_table
      AND ar.subject_id = ge.subject_id AND ar.tenant_id = ge.tenant_id;

GRANT SELECT ON app.gate_shadow_outcome TO daydor_ops, daydor_admin, tenant_founder, tenant_hr, tenant_payroll,
    tenant_it, external_auditor;

-- ---------------------------------------------------------------------------
-- 2. Labelled-example store (off by default, per gate)
-- ---------------------------------------------------------------------------
ALTER TABLE app.gate_definition
    ADD COLUMN store_examples        boolean NOT NULL DEFAULT false,
    ADD COLUMN example_retention_days integer CHECK (example_retention_days BETWEEN 1 AND 730),
    ADD CONSTRAINT gate_definition_examples_need_retention
        CHECK (NOT store_examples OR example_retention_days IS NOT NULL);

CREATE TABLE app.gate_example (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      uuid NOT NULL DEFAULT app.tenant_id(),
    gate_id        text NOT NULL REFERENCES app.gate_definition (gate_id),
    evaluation_id  uuid NOT NULL UNIQUE REFERENCES app.gate_evaluation (id),
    subject_table  text NOT NULL,
    subject_id     uuid NOT NULL,
    input          jsonb NOT NULL,                       -- exactly the gate's declared, class-capped inputs
    label          text CHECK (label IN ('pass', 'escalate')),
    labelled_at    timestamptz,
    expires_at     timestamptz NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    CHECK ((label IS NULL) = (labelled_at IS NULL))
);
CREATE INDEX gate_example_gate_idx ON app.gate_example (gate_id, tenant_id);
CREATE INDEX gate_example_expiry_idx ON app.gate_example (expires_at);
ALTER TABLE app.gate_example ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.gate_example FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON app.gate_example
    USING (tenant_id = app.tenant_id()) WITH CHECK (tenant_id = app.tenant_id());
-- Read by ops and admin only; written only through the functions below.
GRANT SELECT ON app.gate_example TO daydor_ops, daydor_admin;

-- Called by the soft-gate runner right after it records an evaluation. A no-op unless the gate stores examples.
CREATE FUNCTION app.record_gate_example(p_evaluation uuid, p_input jsonb) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS $$
DECLARE
    ev app.gate_evaluation;
    d  app.gate_definition;
    declared text[];
    v_id uuid;
BEGIN
    SELECT * INTO ev FROM app.gate_evaluation WHERE id = p_evaluation AND tenant_id = app.tenant_id();
    IF NOT FOUND THEN
        RAISE EXCEPTION 'evaluation % not found', p_evaluation USING ERRCODE = 'no_data_found';
    END IF;
    SELECT * INTO d FROM app.gate_definition WHERE gate_id = ev.gate_id;
    IF NOT d.store_examples THEN
        RETURN NULL;
    END IF;
    -- Only the declared inputs, never more (the runner already refuses undeclared fields).
    SELECT array_agg(split_part(c, '.', 2)) INTO declared FROM unnest(ev.input_columns) AS c;
    IF EXISTS (SELECT 1 FROM jsonb_object_keys(p_input) AS k WHERE k <> ALL (declared)) THEN
        RAISE EXCEPTION 'example for % has fields beyond the gate''s declared inputs', ev.gate_id
            USING ERRCODE = 'check_violation';
    END IF;
    INSERT INTO app.gate_example (tenant_id, gate_id, evaluation_id, subject_table, subject_id, input, expires_at)
    VALUES (ev.tenant_id, ev.gate_id, ev.id, ev.subject_table, ev.subject_id, p_input,
            now() + make_interval(days => d.example_retention_days))
    ON CONFLICT (evaluation_id) DO NOTHING
    RETURNING id INTO v_id;
    RETURN v_id;
END $$;

-- Fills in labels from resolved human decisions. Idempotent; works one tenant (the session's) at a time.
CREATE FUNCTION app.label_gate_examples(p_gate text DEFAULT NULL) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS $$
DECLARE
    n integer;
BEGIN
    UPDATE app.gate_example e
       SET label = so.human_label, labelled_at = now()
      FROM app.gate_shadow_outcome so
     WHERE so.evaluation_id = e.evaluation_id AND e.tenant_id = app.tenant_id()
       AND e.label IS NULL AND so.human_label IS NOT NULL
       AND (p_gate IS NULL OR e.gate_id = p_gate);
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END $$;

-- Retention: removes this tenant's expired examples. A scheduler calls it per tenant.
CREATE FUNCTION app.purge_expired_gate_examples() RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS $$
DECLARE
    n integer;
BEGIN
    DELETE FROM app.gate_example WHERE tenant_id = app.tenant_id() AND expires_at <= now();
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END $$;

GRANT EXECUTE ON FUNCTION app.record_gate_example(uuid, jsonb) TO worker_platform;
GRANT EXECUTE ON FUNCTION app.label_gate_examples(text), app.purge_expired_gate_examples()
    TO daydor_ops, daydor_worker;

-- ---------------------------------------------------------------------------
-- 3. No pooling across tenants without an explicit opt-in (ADR-006)
-- ---------------------------------------------------------------------------
CREATE TABLE app.tenant_training_policy (
    tenant_id      uuid PRIMARY KEY REFERENCES public.tenant (id),
    allow_pooling  boolean NOT NULL DEFAULT false,
    basis          text,                                   -- the contractual opt-in, when there is one
    recorded_at    timestamptz NOT NULL DEFAULT now(),
    CHECK (NOT allow_pooling OR basis IS NOT NULL)
);
ALTER TABLE app.tenant_training_policy ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.tenant_training_policy FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON app.tenant_training_policy
    USING (tenant_id = app.tenant_id()) WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT ON app.tenant_training_policy TO daydor_ops, daydor_admin, tenant_founder;
GRANT INSERT (tenant_id, allow_pooling, basis), UPDATE (allow_pooling, basis)
    ON app.tenant_training_policy TO daydor_ops, daydor_admin;

-- ---------------------------------------------------------------------------
-- 4. Calibrations and the promotion criteria
-- ---------------------------------------------------------------------------
CREATE TABLE app.gate_calibration (
    version               text PRIMARY KEY,
    gate_id               text NOT NULL REFERENCES app.gate_definition (gate_id),
    checkpoint            text NOT NULL,
    engine_version        text,                            -- the pinned model it was fitted on
    status                text NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate', 'approved', 'retired')),
    n_labels              integer NOT NULL CHECK (n_labels >= 0),
    n_rarer_label         integer NOT NULL CHECK (n_rarer_label >= 0),
    ece                   numeric NOT NULL CHECK (ece >= 0 AND ece <= 1),
    rule_baseline_beaten  boolean NOT NULL,
    disagreement_rate     numeric NOT NULL CHECK (disagreement_rate >= 0 AND disagreement_rate <= 1),
    auto_pass_threshold   numeric NOT NULL CHECK (auto_pass_threshold > 0 AND auto_pass_threshold <= 1),   -- the threshold the evidence was measured at
    shadow_clean_since    date,                            -- start of the clean shadow window after the last model or calibration change
    temperatures          jsonb NOT NULL DEFAULT '{}',
    fitted_at             timestamptz NOT NULL DEFAULT now(),
    signed_off_by         text,
    signed_off_at         timestamptz,
    note                  text,
    -- Promotion criteria (docs/backend-plan.md, "Promotion to enforce"). Starting points, set per gate with its owner.
    CONSTRAINT gate_calibration_approved_meets_criteria CHECK (status <> 'approved' OR (
        n_labels >= 300 AND n_rarer_label >= 50 AND n_rarer_label <= n_labels
        AND ece <= 0.10 AND rule_baseline_beaten AND disagreement_rate < 0.01
        AND signed_off_by IS NOT NULL AND signed_off_at IS NOT NULL
        AND shadow_clean_since IS NOT NULL AND signed_off_at::date >= shadow_clean_since + 14))
);
CREATE INDEX gate_calibration_gate_idx ON app.gate_calibration (gate_id, status);
-- worker_platform reads it: the soft-gate runner applies a gate's fitted temperatures before it thresholds.
GRANT SELECT ON app.gate_calibration TO daydor_ops, daydor_admin, tenant_founder, external_auditor, worker_platform;
GRANT INSERT (version, gate_id, checkpoint, engine_version, n_labels, n_rarer_label, ece, rule_baseline_beaten,
              disagreement_rate, auto_pass_threshold, shadow_clean_since, temperatures, note)
    ON app.gate_calibration TO daydor_ops, daydor_admin;
GRANT UPDATE (status, signed_off_by, signed_off_at, note) ON app.gate_calibration TO daydor_ops, daydor_admin;

-- The evidence is fixed once recorded; only the status and the sign-off move, and only forward.
CREATE FUNCTION app.gate_calibration_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'calibrations are never deleted; retire one instead' USING ERRCODE = 'check_violation';
    END IF;
    IF TG_OP = 'INSERT' AND NEW.status <> 'candidate' THEN
        RAISE EXCEPTION 'a calibration starts as a candidate and is approved afterwards' USING ERRCODE = 'check_violation';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF (to_jsonb(NEW) - 'status' - 'signed_off_by' - 'signed_off_at' - 'note')
           IS DISTINCT FROM (to_jsonb(OLD) - 'status' - 'signed_off_by' - 'signed_off_at' - 'note') THEN
            RAISE EXCEPTION 'calibration evidence is immutable; record a new version' USING ERRCODE = 'check_violation';
        END IF;
        IF OLD.status = 'retired' OR (OLD.status = 'approved' AND NEW.status <> 'approved' AND NEW.status <> 'retired')
           OR (OLD.status = 'candidate' AND NEW.status NOT IN ('candidate', 'approved', 'retired')) THEN
            RAISE EXCEPTION 'calibration % cannot go from % to %', OLD.version, OLD.status, NEW.status
                USING ERRCODE = 'check_violation';
        END IF;
        IF OLD.status = 'approved' AND NEW.status = 'retired'
           AND EXISTS (SELECT 1 FROM app.gate_definition g WHERE g.calibration_version = OLD.version AND g.mode = 'enforce') THEN
            RAISE EXCEPTION 'calibration % is in use by a gate in enforce mode', OLD.version USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN COALESCE(NEW, OLD);
END $$;
CREATE TRIGGER gate_calibration_guard BEFORE INSERT OR UPDATE OR DELETE ON app.gate_calibration
    FOR EACH ROW EXECUTE FUNCTION app.gate_calibration_guard();

-- ---------------------------------------------------------------------------
-- 5. A soft gate enforces only on an approved calibration of its own
-- ---------------------------------------------------------------------------
CREATE FUNCTION app.gate_definition_calibration_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS $$
BEGIN
    IF NEW.kind = 'soft' AND NEW.mode = 'enforce' THEN
        IF NOT EXISTS (SELECT 1 FROM app.gate_calibration c WHERE c.version = NEW.calibration_version
                       AND c.gate_id = NEW.gate_id AND c.status = 'approved') THEN
            RAISE EXCEPTION 'gate % cannot enforce: calibration % is not an approved calibration of this gate',
                NEW.gate_id, coalesce(NEW.calibration_version, '(none)') USING ERRCODE = 'check_violation';
        END IF;
        -- Never looser than what the calibration was measured at.
        IF NEW.auto_pass_threshold < (SELECT c.auto_pass_threshold FROM app.gate_calibration c
                                      WHERE c.version = NEW.calibration_version) THEN
            RAISE EXCEPTION 'gate % threshold % is below the % the calibration % was measured at',
                NEW.gate_id, NEW.auto_pass_threshold,
                (SELECT c.auto_pass_threshold FROM app.gate_calibration c WHERE c.version = NEW.calibration_version),
                NEW.calibration_version USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER gate_definition_calibration_guard BEFORE INSERT OR UPDATE ON app.gate_definition
    FOR EACH ROW EXECUTE FUNCTION app.gate_definition_calibration_guard();

RESET ROLE;
