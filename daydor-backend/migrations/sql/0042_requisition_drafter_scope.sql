-- requisition-drafter reads the seat's job profile and department (its LLM contract's context): 0025 and 0028 are regenerated in
-- place for fresh installs; this is the incremental for databases that already ran them. Generated once from the difference between
-- the old and new 0028; a GRANT that already exists is a no-op, so it is safe to replay on a fresh install.
SET ROLE daydor_schema_owner;

GRANT SELECT (cost_center_code, created_at, head_employee_id, id, name, parent_department_id, tenant_id, updated_at) ON public.department TO worker_requisition_drafter;
GRANT SELECT (created_at, description, flsa_default, id, job_family, level, tenant_id, title, updated_at) ON public.job_profile TO worker_requisition_drafter;

-- worker_definition is immutable at runtime except `enabled`; a migration lifts that for one statement.
ALTER TABLE app.worker_definition DISABLE TRIGGER worker_definition_guard;
UPDATE app.worker_definition SET reads = ARRAY['department', 'job_profile', 'position']::text[], extra_scope = CAST('{"reads": ["job_profile", "department"], "why": "The drafter''s context is the seat''s job profile (title, family, level, description: C0) and the department name (C0); the model lists only position as a read (daydor.agents.workers.requisition_drafter).", "writes": []}' AS jsonb) WHERE worker = 'requisition-drafter';
ALTER TABLE app.worker_definition ENABLE TRIGGER worker_definition_guard;

RESET ROLE;
