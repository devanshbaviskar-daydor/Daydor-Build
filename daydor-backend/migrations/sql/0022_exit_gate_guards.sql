-- Exit flow support (docs/sprint-plan.md Sprints 10-11), three corrections surfaced reading the
-- model against the generated DDL:
--
-- finding 20: `final_settlement.approval_request_id` is modelled NOT NULL, but, like
-- `employee`'s encrypted columns (finding 10) and `payroll_run`'s derived totals (finding 19),
-- nothing can reference an approval for a row that doesn't exist yet. Relaxed to nullable; the
-- row is created with it NULL via app.open_final_settlement (a SECURITY DEFINER function, same
-- pattern as app.open_payroll_run, since `total_settlement` is also `derived` -- no role has an
-- INSERT grant on it at all).
--
-- finding 20 (cont'd): the model's own `g_pay_disburse.tables` list names `final_settlement`
-- alongside `payroll_run`/`contractor_invoice`, but the gate_guard seeded for
-- `final_settlement.disbursed_at` in 0007_gate_seed.sql named `g_finalpay` instead -- the gate for
-- approving the *calculated amounts*, not the one for approving the *fund transfer*. Corrected
-- here; `g_finalpay` becomes a workflow-level checkpoint (daydor.exit.workflow) with no column of
-- its own to guard, same role `dpdp_consent` plays in the hire flow.
--
-- `cobra_event.notice_sent_at` had no gate_guard at all despite `g_cobra` existing for exactly
-- this ("COBRA notice content and timing"); added for symmetry with every other guarded send/pay/
-- deprovision action.
-- ON CONFLICT DO NOTHING / CREATE OR REPLACE throughout: a fresh install replays every migration
-- in order, including this one *and* the now-regenerated 0007_gate_seed.sql, which already seeds
-- cobra_event's gate_guard row and trigger (daydor.gates.registry.GUARDS) -- same reasoning as
-- 0019_timecard_gates.sql.
SET ROLE daydor_schema_owner;

ALTER TABLE public.final_settlement ALTER COLUMN approval_request_id DROP NOT NULL;

CREATE OR REPLACE FUNCTION app.open_final_settlement(p_employee_id uuid, p_termination_id uuid,
                                          p_pending_wages numeric, p_gratuity_payout numeric,
                                          p_leave_encashment numeric, p_recoveries numeric)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    v_id uuid;
BEGIN
    INSERT INTO public.final_settlement (tenant_id, employee_id, termination_id, pending_wages,
        gratuity_payout, leave_encashment, recoveries, total_settlement)
    VALUES (app.tenant_id(), p_employee_id, p_termination_id, p_pending_wages, p_gratuity_payout,
            p_leave_encashment, p_recoveries,
            p_pending_wages + p_gratuity_payout + p_leave_encashment - p_recoveries)
    RETURNING id INTO v_id;
    RETURN v_id;
END $$;

GRANT EXECUTE ON FUNCTION app.open_final_settlement(uuid, uuid, numeric, numeric, numeric, numeric)
    TO agent_runtime;

UPDATE app.gate_guard SET gate_ids = ARRAY['g_pay_disburse']::text[]
    WHERE table_name = 'final_settlement' AND guard_column = 'disbursed_at';

INSERT INTO app.gate_guard VALUES ('cobra_event', 'notice_sent_at', ARRAY['g_cobra']::text[])
    ON CONFLICT (table_name, guard_column) DO NOTHING;
CREATE OR REPLACE TRIGGER cobra_event_gate_guard BEFORE INSERT OR UPDATE ON public.cobra_event
    FOR EACH ROW EXECUTE FUNCTION app.enforce_gate_guard();

RESET ROLE;
