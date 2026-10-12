-- Incremental gate-registry update for databases that already ran 0007_gate_seed.sql (which is
-- regenerated in place for fresh installs -- see daydor.gates.registry.PLATFORM_HARD_GATES --
-- but migrations are forward-only, so an already-migrated database needs this as a new INSERT).
-- ON CONFLICT DO NOTHING because a fresh install replays every migration in order, including
-- this one *and* the now-regenerated 0007, which already inserts this same row.
--
-- Finding 11 (docs/model-findings.md): the hire flow's "approval_request W
-- requisition-approval-router" step needs a gate, and none in the model covers requisition
-- budget sign-off.
SET ROLE daydor_schema_owner;

INSERT INTO app.gate_definition (gate_id, label, kind, approver_roles, tables, source) VALUES
    ('g_requisition_budget', 'Requisition budget sign-off', 'hard', ARRAY['tenant_founder']::text[],
     ARRAY['job_requisition']::text[], 'platform')
ON CONFLICT (gate_id) DO NOTHING;

RESET ROLE;
