-- Incremental gate-registry update for databases that already ran 0007_gate_seed.sql (which is
-- regenerated in place for fresh installs -- see daydor.gates.registry.PLATFORM_HARD_GATES --
-- but migrations are forward-only, so an already-migrated database needs this as a new INSERT).
-- ON CONFLICT DO NOTHING because a fresh install replays every migration in order, including
-- this one *and* the now-regenerated 0007, which already inserts these same rows.
--
-- Finding 9 (docs/model-findings.md): managers have read-only access to approval_request, but
-- timecard-approval-router (and expense-approval-router) send approvals to managers, and no
-- gate in the model names the manager as an approver.
--
-- Also subscribes the 'timekeeping' queue to gate.resolved, alongside the workflow engine's own
-- subscription (0009_workflow.sql): a timecard's approval isn't tracked by any
-- app.workflow_instance (timecards aren't part of a flow with a start/end, they recur every pay
-- period), so daydor.timekeeping.timecard's own handler needs its own delivery of the event
-- rather than piggybacking on the hire/payroll/exit workflow definitions.
SET ROLE daydor_schema_owner;

INSERT INTO app.gate_definition (gate_id, label, kind, approver_roles, tables, source) VALUES
    ('g_timecard', 'Timecard approval', 'hard', ARRAY['tenant_manager']::text[],
     ARRAY['timecard']::text[], 'platform'),
    ('g_expense', 'Expense report approval', 'hard', ARRAY['tenant_manager']::text[],
     ARRAY['expense']::text[], 'platform')
ON CONFLICT (gate_id) DO NOTHING;

INSERT INTO app.subscription (topic, queue, kind) VALUES
    ('gate.resolved', 'timekeeping', 'timekeeping.gate_resolved')
ON CONFLICT (topic, queue, kind) DO NOTHING;

RESET ROLE;
