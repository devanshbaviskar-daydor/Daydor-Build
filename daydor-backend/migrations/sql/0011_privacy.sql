-- Privacy services (ADR-002): app.encrypt_pii / app.decrypt_pii for employee's 4 encrypted
-- columns (Aadhaar e-KYC ref, PAN, SSN, bank account).
--
-- Encrypted columns carry no SELECT, INSERT or UPDATE grant for any role (ddl.py never grants
-- them). The only way to populate or read one is through these two SECURITY DEFINER functions,
-- which run as the table owner, so column-level grants do not apply to them, while row-level
-- security still does (FORCE RLS binds to the session's app.tenant_id()/app.can_see_employee(),
-- not to the function's defining role).
--
-- app.encrypt_pii UPDATEs an already-inserted row (the employee row is created first with these
-- columns NULL, then populated here). That does not fit er_case_note.note_body: er_case_note is
-- append-only (UPDATE is rejected by trigger for every role, including the owner), note_body is
-- NOT NULL, so its ciphertext must be supplied at INSERT time. That needs a column-level INSERT
-- grant plus a pure encrypt-and-return-bytea function, which is a different, not-yet-needed
-- design (no ER case flow is built yet); left for when that flow is built.
--
-- app.pii_column is the purpose registry's column side: which data_category (matching
-- consent_record.data_category) a column belongs to, whether writing it needs an active
-- consent_record, and which roles may collect it. app.pii_purpose / app.pii_purpose_scope are
-- its purpose side: named purposes, which roles may decrypt for each, and which data categories
-- each purpose covers. A caller must name a registered purpose; there is no "just give me the
-- plaintext" path.
--
-- Key management: dev holds one pgcrypto passphrase in a database-level GUC
-- (app.pii_master_key, set below). app.pii_key(tenant_id) is the single place that changes when
-- this is replaced by per-tenant KMS data keys in production.

DO $$
BEGIN
    EXECUTE format('ALTER DATABASE %I SET app.pii_master_key = %L', current_database(),
                   'dev-only-pgcrypto-passphrase-rotate-before-prod');
END
$$;

SET ROLE daydor_schema_owner;

CREATE TABLE app.pii_column (
    table_name       text NOT NULL,
    column_name      text NOT NULL,
    data_category    text,                       -- matches consent_record.data_category; NULL if consent does not apply
    subject_employee_column text,                -- column on this table holding the data subject's employee id ('id' means this row is the employee)
    requires_consent boolean NOT NULL DEFAULT true,
    collect_roles    text[] NOT NULL DEFAULT '{}',
    PRIMARY KEY (table_name, column_name),
    CHECK (NOT requires_consent OR (data_category IS NOT NULL AND subject_employee_column IS NOT NULL))
);

CREATE TABLE app.pii_purpose (
    purpose       text PRIMARY KEY,
    label         text NOT NULL,
    allowed_roles text[] NOT NULL
);

CREATE TABLE app.pii_purpose_scope (
    purpose       text NOT NULL REFERENCES app.pii_purpose(purpose),
    data_category text NOT NULL,
    PRIMARY KEY (purpose, data_category)
);

-- ---------------------------------------------------------------------------
-- Key derivation (dev implementation; see header note)
-- ---------------------------------------------------------------------------
CREATE FUNCTION app.pii_key(p_tenant uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, pg_temp AS $$
    SELECT current_setting('app.pii_master_key')
$$;

-- ---------------------------------------------------------------------------
-- Write path: encrypt and store. Requires the column to be registered, the caller's role to be
-- a collector of that data category, and (if the category requires it) an active, granted,
-- non-withdrawn consent_record for the data subject.
-- ---------------------------------------------------------------------------
CREATE FUNCTION app.encrypt_pii(p_table text, p_column text, p_row_id uuid, p_plaintext text)
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
    IF NOT app.current_app_role() = ANY (v_col.collect_roles) THEN
        RAISE EXCEPTION 'role % may not collect %.%', app.current_app_role(), p_table, p_column
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

-- ---------------------------------------------------------------------------
-- Read path: check purpose and role, check consent, decrypt, and log the access. Every
-- successful or failed-for-lack-of-consent attempt is only reachable through here, so
-- audit_log is a complete record of who read what PII and why.
-- ---------------------------------------------------------------------------
CREATE FUNCTION app.decrypt_pii(p_table text, p_column text, p_row_id uuid, p_purpose text)
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
    IF NOT app.current_app_role() = ANY (v_purpose.allowed_roles) THEN
        RAISE EXCEPTION 'role % may not decrypt PII for purpose %', app.current_app_role(), p_purpose
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

-- ---------------------------------------------------------------------------
-- Registry seed. New encrypted columns or purposes are added here (and pushed back into the
-- model as a jurisdiction-neutral data_category once there is a column for it; see
-- docs/model-findings.md).
-- ---------------------------------------------------------------------------
INSERT INTO app.pii_column (table_name, column_name, data_category, subject_employee_column, collect_roles) VALUES
    ('employee', 'aadhaar_ekyc_ref',       'aadhaar',      'id', ARRAY['tenant_hr', 'agent_hr', 'agent_ob']),
    ('employee', 'pan_encrypted',          'pan',          'id', ARRAY['tenant_hr', 'agent_hr', 'agent_ob']),
    ('employee', 'ssn_encrypted',          'ssn',          'id', ARRAY['tenant_hr', 'agent_hr', 'agent_ob']),
    ('employee', 'bank_account_encrypted', 'bank_account', 'id', ARRAY['tenant_hr', 'agent_hr', 'agent_pay']);

INSERT INTO app.pii_purpose (purpose, label, allowed_roles) VALUES
    ('identity_verification', 'Verify identity during onboarding or e-KYC',
     ARRAY['tenant_hr', 'tenant_it', 'agent_hr', 'agent_ob']),
    ('background_check', 'Share with a background-check vendor',
     ARRAY['tenant_hr', 'agent_hr']),
    ('payroll_disbursal', 'Pay the employee via bank transfer',
     ARRAY['tenant_payroll', 'agent_pay']),
    ('tax_filing', 'Statutory tax filing', ARRAY['tenant_payroll', 'agent_pay']);

INSERT INTO app.pii_purpose_scope (purpose, data_category) VALUES
    ('identity_verification', 'aadhaar'), ('identity_verification', 'pan'), ('identity_verification', 'ssn'),
    ('background_check', 'aadhaar'), ('background_check', 'pan'), ('background_check', 'ssn'),
    ('payroll_disbursal', 'bank_account'),
    ('tax_filing', 'pan');

GRANT SELECT ON app.pii_column, app.pii_purpose, app.pii_purpose_scope TO daydor_admin, daydor_ops;
GRANT EXECUTE ON FUNCTION app.encrypt_pii(text, text, uuid, text), app.decrypt_pii(text, text, uuid, text)
    TO tenant_hr, tenant_it, tenant_payroll, agent_runtime;

RESET ROLE;
