-- Drop the fifteen agent_<domain> roles. Agent work now runs as per-worker roles (0028) through
-- worker_session and Worker.register(worker=...); the API and the tests moved off the domain roles.
--
-- Not dropped: agent_runtime. It is the model's agent ("G") access level that the generated grants
-- (0003) and the grant-matrix test are written against, and it now has no members, so it is inert.
-- Its duplicated platform grants go with it if a later migration retires the level.
--
-- Roles are cluster-wide: every database in the cluster loses them, so a database still on an earlier
-- migration cannot run agent work until it is upgraded. Refuses to run while an exit started on workflow
-- version 2 is still in flight, because its last step (employee_closeout) needs the roles' successor
-- handlers, which only version 3 uses.

DO $$
DECLARE
    r text;
    n integer;
BEGIN
    SELECT count(*) INTO n FROM app.workflow_instance
    WHERE definition_name = 'exit' AND definition_version < 3 AND status IN ('running', 'waiting_gate');
    IF n > 0 THEN
        RAISE EXCEPTION '% exit workflow instance(s) on version 2 are still running; let them finish before dropping the agent roles', n
            USING ERRCODE = 'check_violation';
    END IF;

    FOREACH r IN ARRAY ARRAY['agent_ro', 'agent_priv', 'agent_ref', 'agent_hr', 'agent_ta', 'agent_ob', 'agent_it',
                             'agent_pay', 'agent_ben', 'agent_time', 'agent_comp', 'agent_perf', 'agent_learn',
                             'agent_fin', 'agent_er'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('DROP ROLE %I', r);
        END IF;
    END LOOP;
END $$;

-- The PII registries named the domain roles (and never matched, finding 24); worker roles replaced them in 0028.
SET ROLE daydor_schema_owner;
UPDATE app.pii_column
   SET collect_roles = ARRAY(SELECT x FROM unnest(collect_roles) AS x WHERE x NOT LIKE 'agent\_%');
UPDATE app.pii_purpose
   SET allowed_roles = ARRAY(SELECT x FROM unnest(allowed_roles) AS x WHERE x NOT LIKE 'agent\_%');
RESET ROLE;
