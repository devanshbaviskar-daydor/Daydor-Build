-- payroll-run-builder support (docs/sprint-plan.md Sprint 8, finding 19): payroll_run.gross_total
-- /net_total and payslip.gross_pay/net_pay/tax_withheld are all `derived` columns in the model
-- (model/daydor_model.json), so ddl.py's grants() never gives any role, not even agent_runtime,
-- an INSERT/UPDATE grant on them -- the same pattern as the encrypted PII columns in
-- 0011_privacy.sql. "Derived" here means the database computes them, not just that the app isn't
-- trusted to pass a believable-looking number: app.record_payslip takes the already-computed
-- gross/net/withheld amounts (real business logic from daydor.payroll.compute, not re-derivable
-- from other payslip columns) and app.finalize_payroll_run re-sums payroll_run's own totals from
-- the payslip rows it just wrote, rather than trusting a second, possibly-drifted copy of the
-- same arithmetic from the caller.
SET ROLE daydor_schema_owner;

CREATE FUNCTION app.open_payroll_run(p_legal_entity_id uuid, p_period_start date, p_period_end date,
                                     p_retention_class uuid)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    v_id uuid;
BEGIN
    INSERT INTO public.payroll_run (tenant_id, legal_entity_id, period_start, period_end, status,
        gross_total, net_total, retention_class)
    VALUES (app.tenant_id(), p_legal_entity_id, p_period_start, p_period_end, 'built', 0, 0,
            p_retention_class)
    RETURNING id INTO v_id;
    RETURN v_id;
END $$;

CREATE FUNCTION app.record_payslip(p_payroll_run_id uuid, p_employee_id uuid,
                                   p_employment_record_id uuid, p_gross_pay numeric,
                                   p_net_pay numeric, p_tax_withheld numeric,
                                   p_retention_class uuid)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    v_id uuid;
BEGIN
    INSERT INTO public.payslip (tenant_id, payroll_run_id, employee_id, employment_record_id,
        gross_pay, net_pay, tax_withheld, retention_class)
    VALUES (app.tenant_id(), p_payroll_run_id, p_employee_id, p_employment_record_id, p_gross_pay,
            p_net_pay, p_tax_withheld, p_retention_class)
    RETURNING id INTO v_id;
    RETURN v_id;
END $$;

-- Re-sums payroll_run's two derived totals from the payslip rows already recorded for it. Called
-- once after every payslip in the run has been written; idempotent (re-running it just recomputes
-- the same sums).
CREATE FUNCTION app.finalize_payroll_run(p_payroll_run_id uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
BEGIN
    UPDATE public.payroll_run SET
        gross_total = coalesce((SELECT sum(gross_pay) FROM public.payslip WHERE payroll_run_id = p_payroll_run_id), 0),
        net_total   = coalesce((SELECT sum(net_pay) FROM public.payslip WHERE payroll_run_id = p_payroll_run_id), 0)
    WHERE id = p_payroll_run_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'payroll_run % not found', p_payroll_run_id USING ERRCODE = 'no_data_found';
    END IF;
END $$;

GRANT EXECUTE ON FUNCTION app.open_payroll_run(uuid, date, date, uuid),
    app.record_payslip(uuid, uuid, uuid, numeric, numeric, numeric, uuid),
    app.finalize_payroll_run(uuid)
    TO agent_runtime;

RESET ROLE;
