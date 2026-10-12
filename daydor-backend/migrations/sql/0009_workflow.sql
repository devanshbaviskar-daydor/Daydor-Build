-- State machines stored as data (ADR-001).
--
-- definition JSON:
--   {"initial": "<state>",
--    "states": {"<state>": {"terminal": false,
--                           "enter_jobs": [{"queue": "...", "kind": "..."}],
--                           "on": {"<event>": {"to": "<state>",
--                                              "gate": "<hard gate id>",          optional
--                                              "gate_if": "<context flag>",       optional: gate only if flag true
--                                              "soft_gate": "<soft gate id>",     optional: Jev first
--                                              "on_reject": "<state>"}}}}}        optional

SET ROLE daydor_schema_owner;

CREATE TABLE app.workflow_definition (
    name        text NOT NULL,
    version     integer NOT NULL,
    definition  jsonb NOT NULL,
    source      text NOT NULL DEFAULT 'platform',      -- 'model-flow' for generated skeletons
    active      boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (name, version),
    CHECK (definition ? 'initial' AND definition ? 'states'
           AND definition -> 'states' ? (definition ->> 'initial'))
);
CREATE UNIQUE INDEX workflow_definition_one_active ON app.workflow_definition (name) WHERE active;

CREATE TABLE app.workflow_instance (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            uuid NOT NULL DEFAULT app.tenant_id(),
    definition_name      text NOT NULL,
    definition_version   integer NOT NULL,
    subject_table        text NOT NULL,
    subject_id           uuid NOT NULL,
    state                text NOT NULL,
    status               text NOT NULL DEFAULT 'running'
                         CHECK (status IN ('running', 'waiting_gate', 'completed', 'cancelled')),
    pending_event        text,
    waiting_on_approval  uuid REFERENCES public.approval_request(id),
    context              jsonb NOT NULL DEFAULT '{}',
    version              integer NOT NULL DEFAULT 1,      -- optimistic concurrency
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (definition_name, definition_version) REFERENCES app.workflow_definition (name, version),
    UNIQUE (tenant_id, definition_name, subject_table, subject_id),
    CHECK ((status = 'waiting_gate') = (waiting_on_approval IS NOT NULL))
);
CREATE INDEX workflow_instance_waiting_idx ON app.workflow_instance (waiting_on_approval)
    WHERE waiting_on_approval IS NOT NULL;
CREATE TRIGGER workflow_instance_touch BEFORE UPDATE ON app.workflow_instance
    FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();

CREATE TABLE app.workflow_transition (
    id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id            uuid NOT NULL DEFAULT app.tenant_id(),
    instance_id          uuid NOT NULL REFERENCES app.workflow_instance(id),
    event                text NOT NULL,
    event_id             text,                            -- dedupes at-least-once delivery
    from_state           text NOT NULL,
    to_state             text NOT NULL,
    outcome              text NOT NULL CHECK (outcome IN ('moved', 'waiting_gate', 'rejected')),
    approval_request_id  uuid REFERENCES public.approval_request(id),
    actor_role           text NOT NULL DEFAULT app.current_app_role(),
    actor_user_id        uuid DEFAULT app.user_id(),
    agent_task_run_id    uuid DEFAULT app.agent_task_run_id(),
    created_at           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (instance_id, event_id)
);
CREATE TRIGGER workflow_transition_append_only BEFORE UPDATE OR DELETE ON app.workflow_transition
    FOR EACH ROW EXECUTE FUNCTION app.reject_mutation();

ALTER TABLE app.workflow_instance ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.workflow_instance FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON app.workflow_instance
    USING (tenant_id = app.tenant_id()) WITH CHECK (tenant_id = app.tenant_id());
ALTER TABLE app.workflow_transition ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.workflow_transition FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON app.workflow_transition
    USING (tenant_id = app.tenant_id()) WITH CHECK (tenant_id = app.tenant_id());

-- Agents drive workflows; people with tenant-wide roles can see them.
GRANT SELECT ON app.workflow_definition TO agent_runtime, daydor_ops, tenant_founder, tenant_hr,
    tenant_payroll, external_auditor;
GRANT SELECT, INSERT ON app.workflow_instance, app.workflow_transition TO agent_runtime;
GRANT UPDATE (state, status, pending_event, waiting_on_approval, context, version)
    ON app.workflow_instance TO agent_runtime;
GRANT SELECT ON app.workflow_instance, app.workflow_transition TO daydor_ops, tenant_founder,
    tenant_hr, tenant_payroll, external_auditor;
GRANT INSERT, UPDATE (active) ON app.workflow_definition TO daydor_ops;

-- Gate resolutions wake up waiting workflows.
INSERT INTO app.subscription (topic, queue, kind) VALUES ('gate.resolved', 'workflow', 'workflow.gate_resolved');

RESET ROLE;
