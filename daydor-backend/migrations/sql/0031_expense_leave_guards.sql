-- Finding 23 follow-up (ADR-006): gate guards on the two workflow-owned columns that had none.
--
--   expense.reimbursed_at          needs an approved g_expense request for this row
--   leave_request.fmla_designation needs an approved g_fmla request for this row
--
-- leave_request.status is deliberately NOT guarded: it is NOT NULL with a default, and a guard fires
-- on the NULL -> value transition, so it would block every insert. Status stays an application matter.
--
-- No service writes either column yet, so nothing changes today; the database now refuses an
-- ungated write whoever eventually writes it. Incremental for databases that already ran
-- 0007_gate_seed.sql (regenerated in place for fresh installs, which already has these rows),
-- hence ON CONFLICT DO NOTHING and CREATE OR REPLACE TRIGGER.
SET ROLE daydor_schema_owner;

INSERT INTO app.gate_guard (table_name, guard_column, gate_ids) VALUES
    ('expense', 'reimbursed_at', ARRAY['g_expense']::text[]),
    ('leave_request', 'fmla_designation', ARRAY['g_fmla']::text[])
ON CONFLICT (table_name, guard_column) DO NOTHING;

CREATE OR REPLACE TRIGGER expense_gate_guard BEFORE INSERT OR UPDATE ON public.expense
    FOR EACH ROW EXECUTE FUNCTION app.enforce_gate_guard();
CREATE OR REPLACE TRIGGER leave_request_gate_guard BEFORE INSERT OR UPDATE ON public.leave_request
    FOR EACH ROW EXECUTE FUNCTION app.enforce_gate_guard();

RESET ROLE;
