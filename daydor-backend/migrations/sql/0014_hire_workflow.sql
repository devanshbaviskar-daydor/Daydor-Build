-- Hand-written, NOT generated: see daydor.hire.workflow.HIRE_DEFINITION for why.
-- Supersedes the generated 'hire' skeleton (version 1) from 0010_workflow_seed.sql.
SET ROLE daydor_schema_owner;

UPDATE app.workflow_definition SET active = false WHERE name = 'hire' AND active;
INSERT INTO app.workflow_definition (name, version, definition, source) VALUES ('hire', 2, '{"description": "Seat check, requisition, budget approval, job posting.", "initial": "start", "states": {"done": {"terminal": true}, "s01_position": {"on": {"advance": {"to": "s02_job_requisition"}}, "terminal": false}, "s02_job_requisition": {"on": {"advance": {"to": "s03_approval_request"}}, "terminal": false}, "s03_approval_request": {"enter_jobs": [{"kind": "requisition_approval_router", "queue": "platform"}], "on": {"advance": {"gate": "g_requisition_budget", "to": "s04_job_posting"}}, "terminal": false}, "s04_job_posting": {"enter_jobs": [{"kind": "job_posting_publisher", "queue": "ta"}], "on": {"advance": {"to": "done"}}, "terminal": false}, "start": {"on": {"advance": {"to": "s01_position"}}, "terminal": false}}, "title": "Requisition to first payslip (hand-written, steps 1-4)"}'::jsonb, 'hand-written');

RESET ROLE;
