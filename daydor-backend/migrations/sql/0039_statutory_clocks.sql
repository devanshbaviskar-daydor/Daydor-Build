-- Statutory clocks beyond the I-9 timer (docs/sprint-plan.md, Sprint 13): COBRA notice and election, work-authorization
-- and role-critical certification expiry, a stale 409A valuation, and a threshold-registration deadline.
--
-- Each clock is a dated column on a row a flow already writes. One function lists what is due; one scans it and, the
-- first time a row enters the lead window ("due_soon") and again when the date passes ("overdue"), emits a
-- clock.due_soon / clock.overdue event in the outbox. Idempotent: app.clock_emission remembers what was emitted.
-- A clock is written into the function on purpose, not configured by data: each one is a legal obligation, and
-- adding or changing one is a reviewed migration.
--
-- Both run as the table owner under FORCE row security, so they see the session's tenant only (and, for ops, only an
-- assigned one: 0037).

SET ROLE daydor_schema_owner;

CREATE TABLE app.clock_emission (
    tenant_id      uuid NOT NULL DEFAULT app.tenant_id(),
    clock_id       text NOT NULL,
    subject_table  text NOT NULL,
    subject_id     uuid NOT NULL,
    stage          text NOT NULL CHECK (stage IN ('due_soon', 'overdue')),
    due_on         date NOT NULL,
    emitted_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, clock_id, subject_id, stage)
);
ALTER TABLE app.clock_emission ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.clock_emission FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON app.clock_emission
    USING (tenant_id = app.tenant_id()) WITH CHECK (tenant_id = app.tenant_id());
CREATE TRIGGER clock_emission_append_only BEFORE UPDATE OR DELETE ON app.clock_emission
    FOR EACH ROW EXECUTE FUNCTION app.reject_mutation();
GRANT SELECT ON app.clock_emission TO daydor_ops, daydor_admin, tenant_founder, tenant_hr;

-- What is due, for the session's tenant. due_on is the statutory date; lead_days is how early to warn; owner is the
-- role that acts on it.
CREATE FUNCTION app.statutory_clocks_due()
RETURNS TABLE (clock_id text, label text, subject_table text, subject_id uuid, due_on date, lead_days integer, owner text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
    -- COBRA: the general notice goes out by notice_due_at (44 days from the event), then the election window runs 60
    -- days from the notice. Illustrative lengths: the plan's own simplification (daydor.exit.cobra).
    SELECT 'cobra_notice', 'COBRA notice due', 'cobra_event', c.id, c.notice_due_at, 7, 'hr'
    FROM public.cobra_event c WHERE c.tenant_id = app.tenant_id() AND c.notice_sent_at IS NULL AND c.notice_due_at IS NOT NULL
    UNION ALL
    SELECT 'cobra_election', 'COBRA election window closes', 'cobra_event', c.id, c.notice_sent_at::date + 60, 7, 'hr'
    FROM public.cobra_event c WHERE c.tenant_id = app.tenant_id() AND c.notice_sent_at IS NOT NULL
      AND c.election_status = 'pending'
    UNION ALL
    -- Work authorization: reverify before it expires. Only people still employed.
    SELECT 'work_authorization_expiry', 'Work authorization expires', 'work_authorization', w.id, w.expiration_date, 90, 'hr'
    FROM public.work_authorization w JOIN public.employee e ON e.id = w.employee_id AND e.is_active
    WHERE w.tenant_id = app.tenant_id() AND w.expiration_date IS NOT NULL
    UNION ALL
    -- Role-critical certifications.
    SELECT 'certification_expiry', 'Role-critical certification expires', 'certification', c.id, c.expires_on, 30, 'hr'
    FROM public.certification c JOIN public.employee e ON e.id = c.employee_id AND e.is_active
    WHERE c.tenant_id = app.tenant_id() AND c.role_critical AND c.expires_on IS NOT NULL
    UNION ALL
    -- 409A: only a legal entity's latest valuation counts; it goes stale on its own expires_on.
    SELECT 'valuation_409a', '409A valuation goes stale', 'valuation_409a', v.id, v.expires_on, 30, 'founder'
    FROM public.valuation_409a v
    WHERE v.tenant_id = app.tenant_id() AND v.expires_on IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM public.valuation_409a n WHERE n.tenant_id = v.tenant_id
                      AND n.legal_entity_id = v.legal_entity_id AND n.valuation_date > v.valuation_date)
    UNION ALL
    -- A statutory scheme's headcount threshold was crossed and the registration is not yet approved.
    SELECT 'threshold_registration', 'Statutory registration deadline', 'threshold_obligation', t.id,
           t.registration_deadline, 14, 'founder'
    FROM public.threshold_obligation t
    WHERE t.tenant_id = app.tenant_id() AND t.applicable AND t.registration_deadline IS NOT NULL
      AND t.approval_request_id IS NULL
$$;

-- Emits what has newly entered its window. Returns how many events it emitted.
CREATE FUNCTION app.scan_statutory_clocks(p_asof date DEFAULT current_date) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    r record;
    v_stage text;
    n integer := 0;
    v_new integer;
BEGIN
    FOR r IN SELECT * FROM app.statutory_clocks_due() LOOP
        v_stage := CASE WHEN p_asof >= r.due_on THEN 'overdue'
                        WHEN p_asof >= r.due_on - r.lead_days THEN 'due_soon' END;
        CONTINUE WHEN v_stage IS NULL;
        INSERT INTO app.clock_emission (clock_id, subject_table, subject_id, stage, due_on)
        VALUES (r.clock_id, r.subject_table, r.subject_id, v_stage, r.due_on)
        ON CONFLICT DO NOTHING;
        GET DIAGNOSTICS v_new = ROW_COUNT;
        IF v_new = 1 THEN
            PERFORM app.emit_event('clock.' || v_stage, r.subject_table, r.subject_id,
                jsonb_build_object('clock', r.clock_id, 'label', r.label, 'due_on', r.due_on, 'owner', r.owner));
            n := n + 1;
        END IF;
    END LOOP;
    RETURN n;
END $$;

GRANT EXECUTE ON FUNCTION app.statutory_clocks_due(), app.scan_statutory_clocks(date)
    TO daydor_ops, daydor_admin, worker_root_orchestrator;
GRANT EXECUTE ON FUNCTION app.statutory_clocks_due() TO tenant_founder, tenant_hr;

RESET ROLE;
