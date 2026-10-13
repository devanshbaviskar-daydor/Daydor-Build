-- Activate exit workflow version 3 (one close-out step per worker; inserted inactive by 0029).
--
-- The queue runner (daydor_api.worker) now registers vesting_schedule_tracker, rehire_eligibility_flagger
-- and employee_record_writer_closeout, so new exits use version 3. Exits already running keep their own
-- version: version 2 instances still enqueue employee_closeout, which the runner keeps registering until
-- they finish (0034 refuses to drop the agent roles while any remain).
SET ROLE daydor_schema_owner;

UPDATE app.workflow_definition SET active = false WHERE name = 'exit' AND active AND version <> 3;
UPDATE app.workflow_definition SET active = true  WHERE name = 'exit' AND version = 3;

RESET ROLE;
