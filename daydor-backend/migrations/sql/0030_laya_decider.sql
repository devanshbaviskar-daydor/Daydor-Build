-- Laya replaces Jev as the soft-gate engine (ADR-005). Forward-only: 0006 is not edited.
--
-- Laya checkpoints ship over-confident, so a soft gate may not leave shadow mode until a
-- calibration has been fitted on our own data. The database enforces that, records which
-- calibration decided each evaluation, and refuses an evaluation from the wrong engine.
--
-- Ported from the Laya fork's 0011_laya_decider.sql; renumbered because 0011 is the privacy migration
-- here. record_gate_evaluation keeps its signature (and so its grants), so callers do not change.

SET ROLE daydor_schema_owner;

ALTER TABLE app.gate_definition
    ADD COLUMN engine              text,
    ADD COLUMN checkpoint          text CHECK (checkpoint IN ('english', 'multilingual', 'typed-decisions', 'custom')),
    ADD COLUMN calibration_version text;

UPDATE app.gate_definition SET engine = 'laya', checkpoint = 'english' WHERE kind = 'soft';

ALTER TABLE app.gate_definition
    ADD CONSTRAINT gate_definition_soft_has_engine
        CHECK (kind <> 'soft' OR (engine IS NOT NULL AND checkpoint IS NOT NULL)),
    ADD CONSTRAINT gate_definition_enforce_needs_calibration
        CHECK (kind <> 'soft' OR mode <> 'enforce' OR calibration_version IS NOT NULL);

ALTER TABLE app.gate_evaluation
    ADD COLUMN calibration_version text,
    ADD CONSTRAINT gate_evaluation_enforce_needs_calibration
        CHECK (mode <> 'enforce' OR calibration_version IS NOT NULL);

COMMENT ON COLUMN app.gate_evaluation.engine IS 'The decider that answered: ''laya'' (ADR-005); earlier rows may say ''jev''.';

CREATE OR REPLACE FUNCTION app.record_gate_evaluation(
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
    IF p_engine IS DISTINCT FROM d.engine THEN
        RAISE EXCEPTION 'gate % is decided by %, not %', p_gate, d.engine, p_engine
            USING ERRCODE = 'check_violation';
    END IF;
    -- The database decides the effective outcome, so a caller cannot log a pass the rules forbid.
    v_effective := CASE
        WHEN d.mode = 'shadow' THEN 'escalate'
        WHEN d.calibration_version IS NULL THEN 'escalate'
        WHEN p_model_decision = 'pass' AND p_confidence >= d.auto_pass_threshold THEN 'pass'
        ELSE 'escalate' END;
    INSERT INTO app.gate_evaluation (gate_id, subject_table, subject_id, engine, engine_version,
        schema_version, input_hash, input_columns, output, confidence, threshold, model_decision,
        effective_decision, mode, latency_ms, error, approval_request_id, calibration_version)
    VALUES (p_gate, p_subject_table, p_subject_id, p_engine, p_engine_version, p_schema_version,
        p_input_hash, p_input_columns, p_output, p_confidence, d.auto_pass_threshold, p_model_decision,
        v_effective, d.mode, p_latency_ms, p_error, p_approval_request, d.calibration_version)
    RETURNING id INTO v_id;
    RETURN v_id;
END $$;

RESET ROLE;
