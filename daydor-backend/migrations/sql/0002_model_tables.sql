-- GENERATED from model/daydor_model.json + model/extensions.json. Do not edit by hand.
-- tables: 82

-- tenant: One row per client company and the root of isolation: every tenant-scoped row’s tenant_id references it.
CREATE TABLE public.tenant (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    legal_name                      text NOT NULL,
    cin                             text NOT NULL,
    primary_state_code              text NOT NULL,
    status                          text NOT NULL,
    founder_user_id                 uuid,
    data_residency_region           text NOT NULL,
    plan_tier                       text NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.tenant.id IS 'class=S';
COMMENT ON COLUMN public.tenant.legal_name IS 'class=C0';
COMMENT ON COLUMN public.tenant.cin IS 'class=C0';
COMMENT ON COLUMN public.tenant.primary_state_code IS 'class=C0';
COMMENT ON COLUMN public.tenant.status IS 'class=S';
COMMENT ON COLUMN public.tenant.founder_user_id IS 'class=S';
COMMENT ON COLUMN public.tenant.data_residency_region IS 'class=S';
COMMENT ON COLUMN public.tenant.plan_tier IS 'class=S';
COMMENT ON COLUMN public.tenant.created_at IS 'class=S';
COMMENT ON COLUMN public.tenant.updated_at IS 'class=S';
COMMENT ON TABLE public.tenant IS 'domain=ro;source=doc';

-- legal_entity: A registered employer under the tenant, such as an Indian Pvt Ltd, a US Inc, or an EOR partner. Payroll, filings, benefits and thresholds hang off the entity because statutory registrations are per entity.
CREATE TABLE public.legal_entity (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    name                            text NOT NULL,
    country_code                    text NOT NULL,
    entity_type                     text NOT NULL,
    employer_registrations          jsonb NOT NULL,
    is_eor_partner                  boolean NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.legal_entity.id IS 'class=S';
COMMENT ON COLUMN public.legal_entity.tenant_id IS 'class=S';
COMMENT ON COLUMN public.legal_entity.name IS 'class=C0';
COMMENT ON COLUMN public.legal_entity.country_code IS 'class=C0';
COMMENT ON COLUMN public.legal_entity.entity_type IS 'class=S';
COMMENT ON COLUMN public.legal_entity.employer_registrations IS 'class=C0';
COMMENT ON COLUMN public.legal_entity.is_eor_partner IS 'class=S';
COMMENT ON COLUMN public.legal_entity.created_at IS 'class=S';
COMMENT ON COLUMN public.legal_entity.updated_at IS 'class=S';
COMMENT ON TABLE public.legal_entity IS 'domain=ro;source=new';

-- department: Org units as a tree. Carries the cost centre that GL postings roll up to.
CREATE TABLE public.department (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    name                            text NOT NULL,
    parent_department_id            uuid,
    head_employee_id                uuid,
    cost_center_code                text NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.department.id IS 'class=S';
COMMENT ON COLUMN public.department.tenant_id IS 'class=S';
COMMENT ON COLUMN public.department.name IS 'class=C0';
COMMENT ON COLUMN public.department.parent_department_id IS 'class=S';
COMMENT ON COLUMN public.department.head_employee_id IS 'class=S';
COMMENT ON COLUMN public.department.cost_center_code IS 'class=C0';
COMMENT ON COLUMN public.department.created_at IS 'class=S';
COMMENT ON COLUMN public.department.updated_at IS 'class=S';
COMMENT ON TABLE public.department IS 'domain=ro;source=new';

-- location: Work locations. state_code drives PT slabs in India and state tax nexus in the US.
CREATE TABLE public.location (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    name                            text NOT NULL,
    country_code                    text NOT NULL,
    state_code                      text NOT NULL,
    is_remote                       boolean NOT NULL,
    legal_entity_id                 uuid NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.location.id IS 'class=S';
COMMENT ON COLUMN public.location.tenant_id IS 'class=S';
COMMENT ON COLUMN public.location.name IS 'class=C0';
COMMENT ON COLUMN public.location.country_code IS 'class=C0';
COMMENT ON COLUMN public.location.state_code IS 'class=C0';
COMMENT ON COLUMN public.location.is_remote IS 'class=S';
COMMENT ON COLUMN public.location.legal_entity_id IS 'class=S';
COMMENT ON COLUMN public.location.created_at IS 'class=S';
COMMENT ON COLUMN public.location.updated_at IS 'class=S';
COMMENT ON TABLE public.location IS 'domain=ro;source=new';

-- app_user: Who can log in, distinct from employee (a record about a person). tenant_id is nullable only for Daydor staff, the one deliberate exception to tenant scoping.
CREATE TABLE public.app_user (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id(),
    email                           citext NOT NULL,
    role                            text NOT NULL,
    employee_id                     uuid,
    is_active                       boolean NOT NULL,
    mfa_enrolled                    boolean NOT NULL,
    last_login_at                   timestamptz,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.app_user ADD CONSTRAINT app_user_email_key UNIQUE (email);
COMMENT ON COLUMN public.app_user.id IS 'class=S';
COMMENT ON COLUMN public.app_user.tenant_id IS 'class=S';
COMMENT ON COLUMN public.app_user.email IS 'class=C1';
COMMENT ON COLUMN public.app_user.role IS 'class=S';
COMMENT ON COLUMN public.app_user.employee_id IS 'class=S';
COMMENT ON COLUMN public.app_user.is_active IS 'class=S';
COMMENT ON COLUMN public.app_user.mfa_enrolled IS 'class=S';
COMMENT ON COLUMN public.app_user.last_login_at IS 'class=S';
COMMENT ON COLUMN public.app_user.created_at IS 'class=S';
COMMENT ON COLUMN public.app_user.updated_at IS 'class=S';
COMMENT ON TABLE public.app_user IS 'domain=ro;source=doc';

-- role_assignment: Grants a role at a scope (tenant, department, team, self). This makes access hierarchical: one person can be an employee everywhere, a manager over a subtree, and the EEO officer by designation.
CREATE TABLE public.role_assignment (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    user_id                         uuid NOT NULL,
    role                            text NOT NULL,
    scope_type                      text NOT NULL,
    scope_id                        uuid,
    granted_by_user_id              uuid NOT NULL,
    valid_from                      timestamptz NOT NULL,
    valid_to                        timestamptz,
    purpose                         text NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.role_assignment.id IS 'class=S';
COMMENT ON COLUMN public.role_assignment.tenant_id IS 'class=S';
COMMENT ON COLUMN public.role_assignment.user_id IS 'class=S';
COMMENT ON COLUMN public.role_assignment.role IS 'class=S';
COMMENT ON COLUMN public.role_assignment.scope_type IS 'class=S';
COMMENT ON COLUMN public.role_assignment.scope_id IS 'class=S';
COMMENT ON COLUMN public.role_assignment.granted_by_user_id IS 'class=S';
COMMENT ON COLUMN public.role_assignment.valid_from IS 'class=S';
COMMENT ON COLUMN public.role_assignment.valid_to IS 'class=S';
COMMENT ON COLUMN public.role_assignment.purpose IS 'class=C0';
COMMENT ON COLUMN public.role_assignment.created_at IS 'class=S';
COMMENT ON COLUMN public.role_assignment.updated_at IS 'class=S';
COMMENT ON TABLE public.role_assignment IS 'domain=ro;source=new';

-- tenant_compliance_config: Soft per-tenant preferences as data, never schema. Holds the switch for whether managers see team pay.
CREATE TABLE public.tenant_compliance_config (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    settings                        jsonb NOT NULL,
    manager_can_view_comp           boolean NOT NULL,
    approver_overrides              jsonb NOT NULL,
    feature_flags                   jsonb NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.tenant_compliance_config.id IS 'class=S';
COMMENT ON COLUMN public.tenant_compliance_config.tenant_id IS 'class=S';
COMMENT ON COLUMN public.tenant_compliance_config.settings IS 'class=C0';
COMMENT ON COLUMN public.tenant_compliance_config.manager_can_view_comp IS 'class=S';
COMMENT ON COLUMN public.tenant_compliance_config.approver_overrides IS 'class=S';
COMMENT ON COLUMN public.tenant_compliance_config.feature_flags IS 'class=S';
COMMENT ON COLUMN public.tenant_compliance_config.created_at IS 'class=S';
COMMENT ON COLUMN public.tenant_compliance_config.updated_at IS 'class=S';
COMMENT ON TABLE public.tenant_compliance_config IS 'domain=ro;source=doc';

-- approval_request: One polymorphic row per gate instance, pointing at whatever it guards. deadline_at closes Gap 2 (registration_deadline_scheduler) from the design doc.
CREATE TABLE public.approval_request (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    gate_type                       text NOT NULL,
    subject_table                   text NOT NULL,
    subject_id                      uuid NOT NULL,
    required_approver_role          text NOT NULL,
    status                          text NOT NULL,
    resolved_by_user_id             uuid,
    resolved_at                     timestamptz,
    escalated_at                    timestamptz,
    deadline_at                     timestamptz,
    idempotency_key                 text NOT NULL,
    requested_by_user_id            uuid,
    requested_by_agent_run_id       uuid,
    decision_note                   text,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.approval_request ADD CONSTRAINT approval_request_idempotency_key_key UNIQUE (tenant_id, idempotency_key);
COMMENT ON COLUMN public.approval_request.id IS 'class=S';
COMMENT ON COLUMN public.approval_request.tenant_id IS 'class=S';
COMMENT ON COLUMN public.approval_request.gate_type IS 'class=S';
COMMENT ON COLUMN public.approval_request.subject_table IS 'class=S';
COMMENT ON COLUMN public.approval_request.subject_id IS 'class=S';
COMMENT ON COLUMN public.approval_request.required_approver_role IS 'class=S';
COMMENT ON COLUMN public.approval_request.status IS 'class=S';
COMMENT ON COLUMN public.approval_request.resolved_by_user_id IS 'class=S';
COMMENT ON COLUMN public.approval_request.resolved_at IS 'class=S';
COMMENT ON COLUMN public.approval_request.escalated_at IS 'class=S';
COMMENT ON COLUMN public.approval_request.deadline_at IS 'class=S';
COMMENT ON COLUMN public.approval_request.idempotency_key IS 'class=S';
COMMENT ON COLUMN public.approval_request.requested_by_user_id IS 'class=S;extension';
COMMENT ON COLUMN public.approval_request.requested_by_agent_run_id IS 'class=S;extension';
COMMENT ON COLUMN public.approval_request.decision_note IS 'class=C1;extension';
COMMENT ON COLUMN public.approval_request.created_at IS 'class=S';
COMMENT ON COLUMN public.approval_request.updated_at IS 'class=S';
COMMENT ON TABLE public.approval_request IS 'domain=ro;source=doc';

-- agent_task_run: One row per agent worker execution. Gives gated-irreversible workers a durable idempotency record and lets ops see what agents did without reading Temporal history.
CREATE TABLE public.agent_task_run (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    worker_name                     text NOT NULL,
    domain                          text NOT NULL,
    status                          text NOT NULL,
    idempotency_key                 text NOT NULL,
    approval_request_id             uuid,
    input_ref                       text NOT NULL,
    started_at                      timestamptz NOT NULL,
    finished_at                     timestamptz,
    error_code                      text,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.agent_task_run ADD CONSTRAINT agent_task_run_idempotency_key_key UNIQUE (tenant_id, idempotency_key);
COMMENT ON COLUMN public.agent_task_run.id IS 'class=S';
COMMENT ON COLUMN public.agent_task_run.tenant_id IS 'class=S';
COMMENT ON COLUMN public.agent_task_run.worker_name IS 'class=S';
COMMENT ON COLUMN public.agent_task_run.domain IS 'class=S';
COMMENT ON COLUMN public.agent_task_run.status IS 'class=S';
COMMENT ON COLUMN public.agent_task_run.idempotency_key IS 'class=S';
COMMENT ON COLUMN public.agent_task_run.approval_request_id IS 'class=S';
COMMENT ON COLUMN public.agent_task_run.input_ref IS 'class=C1';
COMMENT ON COLUMN public.agent_task_run.started_at IS 'class=S';
COMMENT ON COLUMN public.agent_task_run.finished_at IS 'class=S';
COMMENT ON COLUMN public.agent_task_run.error_code IS 'class=S';
COMMENT ON COLUMN public.agent_task_run.created_at IS 'class=S';
COMMENT ON COLUMN public.agent_task_run.updated_at IS 'class=S';
COMMENT ON TABLE public.agent_task_run IS 'domain=ro;source=new';

-- document: The vault (document_vault in the 32-table ERD). document_class picks the retention rule; blobs live in India-resident object storage behind signed URLs.
CREATE TABLE public.document (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    subject_type                    text NOT NULL,
    subject_id                      uuid NOT NULL,
    document_class                  text NOT NULL,
    storage_ref                     text NOT NULL,
    retention_class                 uuid NOT NULL,
    consent_record_id               uuid,
    signed_at                       timestamptz,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.document.id IS 'class=S';
COMMENT ON COLUMN public.document.tenant_id IS 'class=S';
COMMENT ON COLUMN public.document.subject_type IS 'class=S';
COMMENT ON COLUMN public.document.subject_id IS 'class=S';
COMMENT ON COLUMN public.document.document_class IS 'class=S';
COMMENT ON COLUMN public.document.storage_ref IS 'class=C3';
COMMENT ON COLUMN public.document.retention_class IS 'class=S';
COMMENT ON COLUMN public.document.consent_record_id IS 'class=S';
COMMENT ON COLUMN public.document.signed_at IS 'class=S';
COMMENT ON COLUMN public.document.created_at IS 'class=S';
COMMENT ON COLUMN public.document.updated_at IS 'class=S';
COMMENT ON TABLE public.document IS 'domain=priv;source=doc';

-- consent_record: Purpose- and field-scoped DPDP consent, one row per (employee, data_category, purpose). Only the data principal writes it; PAN, bank and Aadhaar columns cannot be populated without a granted row.
CREATE TABLE public.consent_record (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    data_category                   text NOT NULL,
    purpose                         text NOT NULL,
    status                          text NOT NULL,
    granted_at                      timestamptz NOT NULL,
    withdrawn_at                    timestamptz,
    consent_artifact_ref            text NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.consent_record.id IS 'class=S';
COMMENT ON COLUMN public.consent_record.tenant_id IS 'class=S';
COMMENT ON COLUMN public.consent_record.employee_id IS 'class=S';
COMMENT ON COLUMN public.consent_record.data_category IS 'class=S';
COMMENT ON COLUMN public.consent_record.purpose IS 'class=S';
COMMENT ON COLUMN public.consent_record.status IS 'class=S';
COMMENT ON COLUMN public.consent_record.granted_at IS 'class=S';
COMMENT ON COLUMN public.consent_record.withdrawn_at IS 'class=S';
COMMENT ON COLUMN public.consent_record.consent_artifact_ref IS 'class=C1';
COMMENT ON COLUMN public.consent_record.created_at IS 'class=S';
COMMENT ON COLUMN public.consent_record.updated_at IS 'class=S';
COMMENT ON TABLE public.consent_record IS 'domain=priv;source=doc';

-- data_subject_request: DPDP access, correction and erasure requests with the 90-day clock. partially_fulfilled_retention_held is the honest outcome when a statutory floor wins.
CREATE TABLE public.data_subject_request (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    request_type                    text NOT NULL,
    status                          text NOT NULL,
    received_at                     timestamptz NOT NULL,
    due_at                          timestamptz NOT NULL,
    resolution_notes                text NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.data_subject_request.id IS 'class=S';
COMMENT ON COLUMN public.data_subject_request.tenant_id IS 'class=S';
COMMENT ON COLUMN public.data_subject_request.employee_id IS 'class=S';
COMMENT ON COLUMN public.data_subject_request.request_type IS 'class=S';
COMMENT ON COLUMN public.data_subject_request.status IS 'class=S';
COMMENT ON COLUMN public.data_subject_request.received_at IS 'class=S';
COMMENT ON COLUMN public.data_subject_request.due_at IS 'class=S;derived';
COMMENT ON COLUMN public.data_subject_request.resolution_notes IS 'class=C2';
COMMENT ON COLUMN public.data_subject_request.created_at IS 'class=S';
COMMENT ON COLUMN public.data_subject_request.updated_at IS 'class=S';
COMMENT ON TABLE public.data_subject_request IS 'domain=priv;source=doc';

-- audit_log: Append-only business-event log written in the same transaction as the mutation. Indexed by (tenant_id, subject_id, occurred_at) for the 72-hour breach report.
CREATE TABLE public.audit_log (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    actor_user_id                   uuid,
    actor_kind                      text NOT NULL,
    agent_task_run_id               uuid,
    event_type                      text NOT NULL,
    subject_table                   text NOT NULL,
    subject_id                      uuid NOT NULL,
    before_value                    jsonb,
    after_value                     jsonb,
    occurred_at                     timestamptz NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.audit_log.id IS 'class=S';
COMMENT ON COLUMN public.audit_log.tenant_id IS 'class=S';
COMMENT ON COLUMN public.audit_log.actor_user_id IS 'class=S';
COMMENT ON COLUMN public.audit_log.actor_kind IS 'class=S';
COMMENT ON COLUMN public.audit_log.agent_task_run_id IS 'class=S';
COMMENT ON COLUMN public.audit_log.event_type IS 'class=S';
COMMENT ON COLUMN public.audit_log.subject_table IS 'class=S';
COMMENT ON COLUMN public.audit_log.subject_id IS 'class=S';
COMMENT ON COLUMN public.audit_log.before_value IS 'class=C3';
COMMENT ON COLUMN public.audit_log.after_value IS 'class=C3';
COMMENT ON COLUMN public.audit_log.occurred_at IS 'class=S';
COMMENT ON COLUMN public.audit_log.created_at IS 'class=S';
COMMENT ON TABLE public.audit_log IS 'domain=priv;source=doc';

-- legal_hold: Backs the root orchestrator’s legal-hold gate. Every irreversible worker checks for an active hold on its subject before acting.
CREATE TABLE public.legal_hold (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    scope_type                      text NOT NULL,
    scope_id                        uuid NOT NULL,
    reason                          text NOT NULL,
    placed_by_user_id               uuid NOT NULL,
    placed_at                       timestamptz NOT NULL,
    released_at                     timestamptz,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.legal_hold.id IS 'class=S';
COMMENT ON COLUMN public.legal_hold.tenant_id IS 'class=S';
COMMENT ON COLUMN public.legal_hold.scope_type IS 'class=S';
COMMENT ON COLUMN public.legal_hold.scope_id IS 'class=S';
COMMENT ON COLUMN public.legal_hold.reason IS 'class=C2';
COMMENT ON COLUMN public.legal_hold.placed_by_user_id IS 'class=S';
COMMENT ON COLUMN public.legal_hold.placed_at IS 'class=S';
COMMENT ON COLUMN public.legal_hold.released_at IS 'class=S';
COMMENT ON COLUMN public.legal_hold.created_at IS 'class=S';
COMMENT ON COLUMN public.legal_hold.updated_at IS 'class=S';
COMMENT ON TABLE public.legal_hold IS 'domain=priv;source=new';

-- retention_policy: Shared reference: duration plus the anchor field the clock starts from (filed_on, last_entry_date, employee.date_of_exit, created_at). Four statutes, four anchors.
CREATE TABLE public.retention_policy (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    retention_class                 text NOT NULL,
    record_type                     text NOT NULL,
    duration_months                 integer NOT NULL,
    anchor_field                    text NOT NULL,
    legal_basis                     text NOT NULL,
    jurisdiction                    text NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.retention_policy ADD CONSTRAINT retention_policy_retention_class_key UNIQUE (retention_class);
COMMENT ON COLUMN public.retention_policy.id IS 'class=S';
COMMENT ON COLUMN public.retention_policy.retention_class IS 'class=S';
COMMENT ON COLUMN public.retention_policy.record_type IS 'class=C0';
COMMENT ON COLUMN public.retention_policy.duration_months IS 'class=C0';
COMMENT ON COLUMN public.retention_policy.anchor_field IS 'class=C0';
COMMENT ON COLUMN public.retention_policy.legal_basis IS 'class=C0';
COMMENT ON COLUMN public.retention_policy.jurisdiction IS 'class=S';
COMMENT ON COLUMN public.retention_policy.created_at IS 'class=S';
COMMENT ON COLUMN public.retention_policy.updated_at IS 'class=S';
COMMENT ON TABLE public.retention_policy IS 'domain=priv;source=doc';

-- pt_slab_rule: Professional-tax slabs per state, effective-dated so a past period always recomputes against the slab in force then.
CREATE TABLE public.pt_slab_rule (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    state_code                      text NOT NULL,
    effective_from                  date NOT NULL,
    effective_to                    date,
    slab_min                        numeric(14,2) NOT NULL,
    slab_max                        numeric(14,2),
    monthly_amount                  numeric(14,2) NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.pt_slab_rule.id IS 'class=S';
COMMENT ON COLUMN public.pt_slab_rule.state_code IS 'class=C0';
COMMENT ON COLUMN public.pt_slab_rule.effective_from IS 'class=S';
COMMENT ON COLUMN public.pt_slab_rule.effective_to IS 'class=S';
COMMENT ON COLUMN public.pt_slab_rule.slab_min IS 'class=C0';
COMMENT ON COLUMN public.pt_slab_rule.slab_max IS 'class=C0';
COMMENT ON COLUMN public.pt_slab_rule.monthly_amount IS 'class=C0';
COMMENT ON COLUMN public.pt_slab_rule.created_at IS 'class=S';
COMMENT ON COLUMN public.pt_slab_rule.updated_at IS 'class=S';
COMMENT ON TABLE public.pt_slab_rule IS 'domain=ref;source=doc;pack=IN';

-- statutory_rate_rule: Generalises the doc’s epf_rate_rule and esi_rate_rule into one effective-dated table keyed by scheme, so US FICA, FUTA and SUI rates fit the same shape.
CREATE TABLE public.statutory_rate_rule (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scheme                          text NOT NULL,
    jurisdiction_code               text NOT NULL,
    effective_from                  date NOT NULL,
    effective_to                    date,
    wage_ceiling                    numeric(14,2),
    employee_rate                   numeric(14,2) NOT NULL,
    employer_rate                   numeric(14,2) NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.statutory_rate_rule.id IS 'class=S';
COMMENT ON COLUMN public.statutory_rate_rule.scheme IS 'class=C0';
COMMENT ON COLUMN public.statutory_rate_rule.jurisdiction_code IS 'class=C0';
COMMENT ON COLUMN public.statutory_rate_rule.effective_from IS 'class=S';
COMMENT ON COLUMN public.statutory_rate_rule.effective_to IS 'class=S';
COMMENT ON COLUMN public.statutory_rate_rule.wage_ceiling IS 'class=C0';
COMMENT ON COLUMN public.statutory_rate_rule.employee_rate IS 'class=C0';
COMMENT ON COLUMN public.statutory_rate_rule.employer_rate IS 'class=C0';
COMMENT ON COLUMN public.statutory_rate_rule.created_at IS 'class=S';
COMMENT ON COLUMN public.statutory_rate_rule.updated_at IS 'class=S';
COMMENT ON TABLE public.statutory_rate_rule IS 'domain=ref;source=doc';

-- employee: One person in one tenant (employee_core in the 32-table ERD). hire_event_id is the creation idempotency key. Raw Aadhaar is never stored: masked last-4 plus an offline e-KYC reference.
CREATE TABLE public.employee (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    hire_event_id                   text NOT NULL,
    full_name                       text NOT NULL,
    work_email                      citext NOT NULL,
    employment_type                 text NOT NULL,
    legal_entity_id                 uuid NOT NULL,
    department_id                   uuid NOT NULL,
    location_id                     uuid NOT NULL,
    position_id                     uuid,
    state_code                      text NOT NULL,
    date_of_joining                 date NOT NULL,
    date_of_exit                    date,
    is_active                       boolean NOT NULL,
    date_of_birth                   date NOT NULL,
    personal_address                text NOT NULL,
    aadhaar_last4                   text NOT NULL,
    aadhaar_ekyc_ref                bytea NOT NULL,
    pan_encrypted                   bytea NOT NULL,
    ssn_encrypted                   bytea NOT NULL,
    bank_account_encrypted          bytea NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.employee ADD CONSTRAINT employee_hire_event_id_key UNIQUE (tenant_id, hire_event_id);
COMMENT ON COLUMN public.employee.id IS 'class=S';
COMMENT ON COLUMN public.employee.tenant_id IS 'class=S';
COMMENT ON COLUMN public.employee.hire_event_id IS 'class=S';
COMMENT ON COLUMN public.employee.full_name IS 'class=C1';
COMMENT ON COLUMN public.employee.work_email IS 'class=C1';
COMMENT ON COLUMN public.employee.employment_type IS 'class=C1';
COMMENT ON COLUMN public.employee.legal_entity_id IS 'class=S';
COMMENT ON COLUMN public.employee.department_id IS 'class=S';
COMMENT ON COLUMN public.employee.location_id IS 'class=S';
COMMENT ON COLUMN public.employee.position_id IS 'class=S';
COMMENT ON COLUMN public.employee.state_code IS 'class=C1';
COMMENT ON COLUMN public.employee.date_of_joining IS 'class=C1';
COMMENT ON COLUMN public.employee.date_of_exit IS 'class=C1';
COMMENT ON COLUMN public.employee.is_active IS 'class=S';
COMMENT ON COLUMN public.employee.date_of_birth IS 'class=C3';
COMMENT ON COLUMN public.employee.personal_address IS 'class=C3';
COMMENT ON COLUMN public.employee.aadhaar_last4 IS 'class=C3;masked;pack=IN';
COMMENT ON COLUMN public.employee.aadhaar_ekyc_ref IS 'class=C3;enc=pgcrypto;pack=IN';
COMMENT ON COLUMN public.employee.pan_encrypted IS 'class=C3;enc=pgcrypto;pack=IN';
COMMENT ON COLUMN public.employee.ssn_encrypted IS 'class=C3;enc=pgcrypto;pack=US';
COMMENT ON COLUMN public.employee.bank_account_encrypted IS 'class=C3;enc=pgcrypto';
COMMENT ON COLUMN public.employee.created_at IS 'class=S';
COMMENT ON COLUMN public.employee.updated_at IS 'class=S';
COMMENT ON TABLE public.employee IS 'domain=hr;source=doc';

-- employment_record: Effective-dated job and pay structure. Immutable once a payroll run has used it; a raise is a new version. wage_floor_compliant enforces the Labour Codes 50% Basic+DA floor.
CREATE TABLE public.employment_record (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    effective_from                  date NOT NULL,
    effective_to                    date,
    job_profile_id                  uuid NOT NULL,
    comp_band_id                    uuid,
    fte                             numeric(14,2) NOT NULL,
    ctc_annual                      numeric(14,2) NOT NULL,
    basic_da_monthly                numeric(14,2) NOT NULL,
    other_allowances_json           jsonb NOT NULL,
    wage_floor_compliant            boolean NOT NULL,
    tax_regime_election             text NOT NULL,
    flsa_status                     text NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.employment_record.id IS 'class=S';
COMMENT ON COLUMN public.employment_record.tenant_id IS 'class=S';
COMMENT ON COLUMN public.employment_record.employee_id IS 'class=S';
COMMENT ON COLUMN public.employment_record.effective_from IS 'class=S';
COMMENT ON COLUMN public.employment_record.effective_to IS 'class=S';
COMMENT ON COLUMN public.employment_record.job_profile_id IS 'class=S';
COMMENT ON COLUMN public.employment_record.comp_band_id IS 'class=S';
COMMENT ON COLUMN public.employment_record.fte IS 'class=C1';
COMMENT ON COLUMN public.employment_record.ctc_annual IS 'class=C2';
COMMENT ON COLUMN public.employment_record.basic_da_monthly IS 'class=C2';
COMMENT ON COLUMN public.employment_record.other_allowances_json IS 'class=C2';
COMMENT ON COLUMN public.employment_record.wage_floor_compliant IS 'class=S;pack=IN';
COMMENT ON COLUMN public.employment_record.tax_regime_election IS 'class=C2;pack=IN';
COMMENT ON COLUMN public.employment_record.flsa_status IS 'class=C1;pack=US';
COMMENT ON COLUMN public.employment_record.created_at IS 'class=S';
COMMENT ON COLUMN public.employment_record.updated_at IS 'class=S';
COMMENT ON TABLE public.employment_record IS 'domain=hr;source=doc';

-- position: A budgeted seat, distinct from the person in it, so backfills and reorgs keep headcount-plan history. headcount-planner already assumes this exists.
CREATE TABLE public.position (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    department_id                   uuid NOT NULL,
    job_profile_id                  uuid NOT NULL,
    status                          text NOT NULL,
    budgeted_fte                    numeric(14,2) NOT NULL,
    budgeted_cost                   numeric(14,2) NOT NULL,
    current_employee_id             uuid,
    opened_at                       date NOT NULL,
    closed_at                       date,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.position.id IS 'class=S';
COMMENT ON COLUMN public.position.tenant_id IS 'class=S';
COMMENT ON COLUMN public.position.department_id IS 'class=S';
COMMENT ON COLUMN public.position.job_profile_id IS 'class=S';
COMMENT ON COLUMN public.position.status IS 'class=S';
COMMENT ON COLUMN public.position.budgeted_fte IS 'class=C1';
COMMENT ON COLUMN public.position.budgeted_cost IS 'class=C2';
COMMENT ON COLUMN public.position.current_employee_id IS 'class=S';
COMMENT ON COLUMN public.position.opened_at IS 'class=S';
COMMENT ON COLUMN public.position.closed_at IS 'class=S';
COMMENT ON COLUMN public.position.created_at IS 'class=S';
COMMENT ON COLUMN public.position.updated_at IS 'class=S';
COMMENT ON TABLE public.position IS 'domain=hr;source=gap';

-- job_profile: Company-level reference data the gap analysis flagged as load-bearing: replaces free-text job_title and gives comp-band-validator something to validate against.
CREATE TABLE public.job_profile (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    title                           text NOT NULL,
    job_family                      text NOT NULL,
    level                           text NOT NULL,
    flsa_default                    text NOT NULL,
    description                     text NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.job_profile.id IS 'class=S';
COMMENT ON COLUMN public.job_profile.tenant_id IS 'class=S';
COMMENT ON COLUMN public.job_profile.title IS 'class=C0';
COMMENT ON COLUMN public.job_profile.job_family IS 'class=C0';
COMMENT ON COLUMN public.job_profile.level IS 'class=C0';
COMMENT ON COLUMN public.job_profile.flsa_default IS 'class=C0;pack=US';
COMMENT ON COLUMN public.job_profile.description IS 'class=C0';
COMMENT ON COLUMN public.job_profile.created_at IS 'class=S';
COMMENT ON COLUMN public.job_profile.updated_at IS 'class=S';
COMMENT ON TABLE public.job_profile IS 'domain=hr;source=gap';

-- comp_band: Pay range per job profile and geo, effective-dated. The other half of the job_profile / comp_band follow-up blocking comp-band-validator.
CREATE TABLE public.comp_band (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    job_profile_id                  uuid NOT NULL,
    location_id                     uuid,
    currency                        text NOT NULL,
    band_min                        numeric(14,2) NOT NULL,
    band_mid                        numeric(14,2) NOT NULL,
    band_max                        numeric(14,2) NOT NULL,
    effective_from                  date NOT NULL,
    effective_to                    date,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.comp_band.id IS 'class=S';
COMMENT ON COLUMN public.comp_band.tenant_id IS 'class=S';
COMMENT ON COLUMN public.comp_band.job_profile_id IS 'class=S';
COMMENT ON COLUMN public.comp_band.location_id IS 'class=S';
COMMENT ON COLUMN public.comp_band.currency IS 'class=C0';
COMMENT ON COLUMN public.comp_band.band_min IS 'class=C2';
COMMENT ON COLUMN public.comp_band.band_mid IS 'class=C2';
COMMENT ON COLUMN public.comp_band.band_max IS 'class=C2';
COMMENT ON COLUMN public.comp_band.effective_from IS 'class=S';
COMMENT ON COLUMN public.comp_band.effective_to IS 'class=S';
COMMENT ON COLUMN public.comp_band.created_at IS 'class=S';
COMMENT ON COLUMN public.comp_band.updated_at IS 'class=S';
COMMENT ON TABLE public.comp_band IS 'domain=hr;source=gap';

-- reporting_line: Effective-dated reporting edges. A materialised closure built from this table is what the manager RLS policy checks: is this row’s employee anywhere under me?
CREATE TABLE public.reporting_line (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    manager_employee_id             uuid NOT NULL,
    relation                        text NOT NULL,
    effective_from                  date NOT NULL,
    effective_to                    date,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.reporting_line.id IS 'class=S';
COMMENT ON COLUMN public.reporting_line.tenant_id IS 'class=S';
COMMENT ON COLUMN public.reporting_line.employee_id IS 'class=S';
COMMENT ON COLUMN public.reporting_line.manager_employee_id IS 'class=S';
COMMENT ON COLUMN public.reporting_line.relation IS 'class=S';
COMMENT ON COLUMN public.reporting_line.effective_from IS 'class=S';
COMMENT ON COLUMN public.reporting_line.effective_to IS 'class=S';
COMMENT ON COLUMN public.reporting_line.created_at IS 'class=S';
COMMENT ON COLUMN public.reporting_line.updated_at IS 'class=S';
COMMENT ON TABLE public.reporting_line IS 'domain=hr;source=new';

-- emergency_contact: A flat miss in the 32-table list. Needed from day one at any company size.
CREATE TABLE public.emergency_contact (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    contact_name                    text NOT NULL,
    relationship                    text NOT NULL,
    phone                           text NOT NULL,
    priority                        integer NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.emergency_contact.id IS 'class=S';
COMMENT ON COLUMN public.emergency_contact.tenant_id IS 'class=S';
COMMENT ON COLUMN public.emergency_contact.employee_id IS 'class=S';
COMMENT ON COLUMN public.emergency_contact.contact_name IS 'class=C3';
COMMENT ON COLUMN public.emergency_contact.relationship IS 'class=C3';
COMMENT ON COLUMN public.emergency_contact.phone IS 'class=C3';
COMMENT ON COLUMN public.emergency_contact.priority IS 'class=S';
COMMENT ON COLUMN public.emergency_contact.created_at IS 'class=S';
COMMENT ON COLUMN public.emergency_contact.updated_at IS 'class=S';
COMMENT ON TABLE public.emergency_contact IS 'domain=hr;source=gap';

-- work_authorization: Case-status tracking for I-9, E-Verify, H-1B, OPT and TN with expiry and next action, instead of a static document in the vault.
CREATE TABLE public.work_authorization (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    auth_type                       text NOT NULL,
    status                          text NOT NULL,
    i9_section2_completed_at        timestamptz,
    everify_case_no                 text,
    everify_status                  text NOT NULL,
    expiration_date                 date,
    sponsor_flag                    boolean NOT NULL,
    renewal_case_status             text,
    next_action_due                 date,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.work_authorization.id IS 'class=S';
COMMENT ON COLUMN public.work_authorization.tenant_id IS 'class=S';
COMMENT ON COLUMN public.work_authorization.employee_id IS 'class=S';
COMMENT ON COLUMN public.work_authorization.auth_type IS 'class=C3';
COMMENT ON COLUMN public.work_authorization.status IS 'class=C3';
COMMENT ON COLUMN public.work_authorization.i9_section2_completed_at IS 'class=C1';
COMMENT ON COLUMN public.work_authorization.everify_case_no IS 'class=C3';
COMMENT ON COLUMN public.work_authorization.everify_status IS 'class=C1';
COMMENT ON COLUMN public.work_authorization.expiration_date IS 'class=C3';
COMMENT ON COLUMN public.work_authorization.sponsor_flag IS 'class=C3';
COMMENT ON COLUMN public.work_authorization.renewal_case_status IS 'class=C3';
COMMENT ON COLUMN public.work_authorization.next_action_due IS 'class=C1';
COMMENT ON COLUMN public.work_authorization.created_at IS 'class=S';
COMMENT ON COLUMN public.work_authorization.updated_at IS 'class=S';
COMMENT ON TABLE public.work_authorization IS 'domain=hr;source=gap;pack=US';

-- self_identification: Voluntary EEO self-ID kept apart from decision records in a restricted schema. Hiring managers never see it; reporting reads an aggregate view only.
CREATE TABLE public.self_identification (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    race_ethnicity                  text NOT NULL,
    gender                          text NOT NULL,
    veteran_status                  text NOT NULL,
    disability_status               text NOT NULL,
    collection_context              text NOT NULL,
    collected_at                    timestamptz NOT NULL,
    next_reoffer_due                date NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.self_identification.id IS 'class=S';
COMMENT ON COLUMN public.self_identification.tenant_id IS 'class=S';
COMMENT ON COLUMN public.self_identification.employee_id IS 'class=S';
COMMENT ON COLUMN public.self_identification.race_ethnicity IS 'class=C4';
COMMENT ON COLUMN public.self_identification.gender IS 'class=C4';
COMMENT ON COLUMN public.self_identification.veteran_status IS 'class=C4';
COMMENT ON COLUMN public.self_identification.disability_status IS 'class=C4';
COMMENT ON COLUMN public.self_identification.collection_context IS 'class=S';
COMMENT ON COLUMN public.self_identification.collected_at IS 'class=S';
COMMENT ON COLUMN public.self_identification.next_reoffer_due IS 'class=S';
COMMENT ON COLUMN public.self_identification.created_at IS 'class=S';
COMMENT ON COLUMN public.self_identification.updated_at IS 'class=S';
COMMENT ON TABLE public.self_identification IS 'domain=hr;source=gap;pack=US';

-- threshold_obligation: Per-scheme applicability (ESI, EPF, Gratuity, POSH, ACA ALE, EEO-1, WARN) per legal entity, with the founder confirmation gate and a registration deadline.
CREATE TABLE public.threshold_obligation (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    legal_entity_id                 uuid NOT NULL,
    scheme                          text NOT NULL,
    headcount_at_check              integer NOT NULL,
    threshold                       integer NOT NULL,
    applicable                      boolean NOT NULL,
    crossed_at                      date,
    registration_deadline           date,
    approval_request_id             uuid,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.threshold_obligation.id IS 'class=S';
COMMENT ON COLUMN public.threshold_obligation.tenant_id IS 'class=S';
COMMENT ON COLUMN public.threshold_obligation.legal_entity_id IS 'class=S';
COMMENT ON COLUMN public.threshold_obligation.scheme IS 'class=C0';
COMMENT ON COLUMN public.threshold_obligation.headcount_at_check IS 'class=C0';
COMMENT ON COLUMN public.threshold_obligation.threshold IS 'class=C0';
COMMENT ON COLUMN public.threshold_obligation.applicable IS 'class=S';
COMMENT ON COLUMN public.threshold_obligation.crossed_at IS 'class=S';
COMMENT ON COLUMN public.threshold_obligation.registration_deadline IS 'class=S';
COMMENT ON COLUMN public.threshold_obligation.approval_request_id IS 'class=S';
COMMENT ON COLUMN public.threshold_obligation.created_at IS 'class=S';
COMMENT ON COLUMN public.threshold_obligation.updated_at IS 'class=S';
COMMENT ON TABLE public.threshold_obligation IS 'domain=hr;source=doc';

-- skill: One skill catalogue shared by recruiting, performance, learning and succession.
CREATE TABLE public.skill (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    name                            text NOT NULL,
    category                        text NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.skill.id IS 'class=S';
COMMENT ON COLUMN public.skill.tenant_id IS 'class=S';
COMMENT ON COLUMN public.skill.name IS 'class=C0';
COMMENT ON COLUMN public.skill.category IS 'class=C0';
COMMENT ON COLUMN public.skill.created_at IS 'class=S';
COMMENT ON COLUMN public.skill.updated_at IS 'class=S';
COMMENT ON TABLE public.skill IS 'domain=hr;source=gap';

-- employee_skill: Proficiency per person per skill with its source, so training and succession have something to reason from.
CREATE TABLE public.employee_skill (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    skill_id                        uuid NOT NULL,
    proficiency_level               integer NOT NULL,
    source                          text NOT NULL,
    last_updated                    timestamptz NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.employee_skill.id IS 'class=S';
COMMENT ON COLUMN public.employee_skill.tenant_id IS 'class=S';
COMMENT ON COLUMN public.employee_skill.employee_id IS 'class=S';
COMMENT ON COLUMN public.employee_skill.skill_id IS 'class=S';
COMMENT ON COLUMN public.employee_skill.proficiency_level IS 'class=C2';
COMMENT ON COLUMN public.employee_skill.source IS 'class=S';
COMMENT ON COLUMN public.employee_skill.last_updated IS 'class=S';
COMMENT ON COLUMN public.employee_skill.created_at IS 'class=S';
COMMENT ON COLUMN public.employee_skill.updated_at IS 'class=S';
COMMENT ON TABLE public.employee_skill IS 'domain=hr;source=gap';

-- job_requisition: Request to fill a position, routed for budget sign-off.
CREATE TABLE public.job_requisition (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    position_id                     uuid NOT NULL,
    hiring_manager_id               uuid NOT NULL,
    status                          text NOT NULL,
    target_start_date               date NOT NULL,
    approval_request_id             uuid,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.job_requisition.id IS 'class=S';
COMMENT ON COLUMN public.job_requisition.tenant_id IS 'class=S';
COMMENT ON COLUMN public.job_requisition.position_id IS 'class=S';
COMMENT ON COLUMN public.job_requisition.hiring_manager_id IS 'class=S';
COMMENT ON COLUMN public.job_requisition.status IS 'class=S';
COMMENT ON COLUMN public.job_requisition.target_start_date IS 'class=C0';
COMMENT ON COLUMN public.job_requisition.approval_request_id IS 'class=S';
COMMENT ON COLUMN public.job_requisition.created_at IS 'class=S';
COMMENT ON COLUMN public.job_requisition.updated_at IS 'class=S';
COMMENT ON TABLE public.job_requisition IS 'domain=ta;source=graph';

-- job_posting: A published req. pay_transparency_checked closes the review flag: no posting goes live without a salary-range check.
CREATE TABLE public.job_posting (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    requisition_id                  uuid NOT NULL,
    channel                         text NOT NULL,
    pay_range_min                   numeric(14,2) NOT NULL,
    pay_range_max                   numeric(14,2) NOT NULL,
    pay_transparency_checked        boolean NOT NULL,
    posted_at                       timestamptz,
    closed_at                       timestamptz,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.job_posting.id IS 'class=S';
COMMENT ON COLUMN public.job_posting.tenant_id IS 'class=S';
COMMENT ON COLUMN public.job_posting.requisition_id IS 'class=S';
COMMENT ON COLUMN public.job_posting.channel IS 'class=S';
COMMENT ON COLUMN public.job_posting.pay_range_min IS 'class=C0';
COMMENT ON COLUMN public.job_posting.pay_range_max IS 'class=C0';
COMMENT ON COLUMN public.job_posting.pay_transparency_checked IS 'class=S';
COMMENT ON COLUMN public.job_posting.posted_at IS 'class=S';
COMMENT ON COLUMN public.job_posting.closed_at IS 'class=S';
COMMENT ON COLUMN public.job_posting.created_at IS 'class=S';
COMMENT ON COLUMN public.job_posting.updated_at IS 'class=S';
COMMENT ON TABLE public.job_posting IS 'domain=ta;source=graph';

-- candidate: A person before hire. Kept separate from employee per TA’s own boundary: candidate is not employee until hire is confirmed.
CREATE TABLE public.candidate (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    full_name                       text NOT NULL,
    email                           citext NOT NULL,
    phone                           text NOT NULL,
    resume_ref                      text NOT NULL,
    source                          text NOT NULL,
    retain_until                    date NOT NULL,
    converted_employee_id           uuid,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.candidate.id IS 'class=S';
COMMENT ON COLUMN public.candidate.tenant_id IS 'class=S';
COMMENT ON COLUMN public.candidate.full_name IS 'class=C1';
COMMENT ON COLUMN public.candidate.email IS 'class=C1';
COMMENT ON COLUMN public.candidate.phone IS 'class=C3';
COMMENT ON COLUMN public.candidate.resume_ref IS 'class=C3';
COMMENT ON COLUMN public.candidate.source IS 'class=S';
COMMENT ON COLUMN public.candidate.retain_until IS 'class=S';
COMMENT ON COLUMN public.candidate.converted_employee_id IS 'class=S';
COMMENT ON COLUMN public.candidate.created_at IS 'class=S';
COMMENT ON COLUMN public.candidate.updated_at IS 'class=S';
COMMENT ON TABLE public.candidate IS 'domain=ta;source=gap';

-- application: Candidate applied to a requisition, with stage history.
CREATE TABLE public.application (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    candidate_id                    uuid NOT NULL,
    requisition_id                  uuid NOT NULL,
    stage                           text NOT NULL,
    stage_changed_at                timestamptz NOT NULL,
    rejection_reason_code           text,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.application.id IS 'class=S';
COMMENT ON COLUMN public.application.tenant_id IS 'class=S';
COMMENT ON COLUMN public.application.candidate_id IS 'class=S';
COMMENT ON COLUMN public.application.requisition_id IS 'class=S';
COMMENT ON COLUMN public.application.stage IS 'class=S';
COMMENT ON COLUMN public.application.stage_changed_at IS 'class=S';
COMMENT ON COLUMN public.application.rejection_reason_code IS 'class=C2';
COMMENT ON COLUMN public.application.created_at IS 'class=S';
COMMENT ON COLUMN public.application.updated_at IS 'class=S';
COMMENT ON TABLE public.application IS 'domain=ta;source=graph';

-- screening_result: Automated screening output, the highest-exposure decision in TA. Records tool version, audit in force, candidate notice and human review so LL144, IL HB3773 and CO SB24-205 are provable.
CREATE TABLE public.screening_result (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    application_id                  uuid NOT NULL,
    aedt_audit_id                   uuid,
    tool_name                       text NOT NULL,
    model_version                   text NOT NULL,
    score                           numeric(14,2) NOT NULL,
    recommendation                  text NOT NULL,
    candidate_notified_at           timestamptz,
    human_reviewer_user_id          uuid,
    human_override                  boolean NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.screening_result.id IS 'class=S';
COMMENT ON COLUMN public.screening_result.tenant_id IS 'class=S';
COMMENT ON COLUMN public.screening_result.application_id IS 'class=S';
COMMENT ON COLUMN public.screening_result.aedt_audit_id IS 'class=S';
COMMENT ON COLUMN public.screening_result.tool_name IS 'class=C0';
COMMENT ON COLUMN public.screening_result.model_version IS 'class=C0';
COMMENT ON COLUMN public.screening_result.score IS 'class=C2';
COMMENT ON COLUMN public.screening_result.recommendation IS 'class=C2';
COMMENT ON COLUMN public.screening_result.candidate_notified_at IS 'class=S';
COMMENT ON COLUMN public.screening_result.human_reviewer_user_id IS 'class=S';
COMMENT ON COLUMN public.screening_result.human_override IS 'class=S';
COMMENT ON COLUMN public.screening_result.created_at IS 'class=S';
COMMENT ON COLUMN public.screening_result.updated_at IS 'class=S';
COMMENT ON TABLE public.screening_result IS 'domain=ta;source=graph';

-- aedt_audit: Bias-audit currency for each screening tool. aedt-audit-monitor blocks the screener when expires_on has passed.
CREATE TABLE public.aedt_audit (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    tool_name                       text NOT NULL,
    auditor_firm                    text NOT NULL,
    audit_date                      date NOT NULL,
    expires_on                      date NOT NULL,
    impact_ratio_summary            jsonb NOT NULL,
    published_url                   text NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.aedt_audit.id IS 'class=S';
COMMENT ON COLUMN public.aedt_audit.tenant_id IS 'class=S';
COMMENT ON COLUMN public.aedt_audit.tool_name IS 'class=C0';
COMMENT ON COLUMN public.aedt_audit.auditor_firm IS 'class=C0';
COMMENT ON COLUMN public.aedt_audit.audit_date IS 'class=S';
COMMENT ON COLUMN public.aedt_audit.expires_on IS 'class=S';
COMMENT ON COLUMN public.aedt_audit.impact_ratio_summary IS 'class=C1';
COMMENT ON COLUMN public.aedt_audit.published_url IS 'class=C0';
COMMENT ON COLUMN public.aedt_audit.created_at IS 'class=S';
COMMENT ON COLUMN public.aedt_audit.updated_at IS 'class=S';
COMMENT ON TABLE public.aedt_audit IS 'domain=ta;source=graph';

-- interview: Scheduled interviews and scorecards.
CREATE TABLE public.interview (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    application_id                  uuid NOT NULL,
    interviewer_employee_id         uuid NOT NULL,
    scheduled_at                    timestamptz NOT NULL,
    scorecard                       jsonb,
    recommendation                  text,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.interview.id IS 'class=S';
COMMENT ON COLUMN public.interview.tenant_id IS 'class=S';
COMMENT ON COLUMN public.interview.application_id IS 'class=S';
COMMENT ON COLUMN public.interview.interviewer_employee_id IS 'class=S';
COMMENT ON COLUMN public.interview.scheduled_at IS 'class=S';
COMMENT ON COLUMN public.interview.scorecard IS 'class=C2';
COMMENT ON COLUMN public.interview.recommendation IS 'class=C2';
COMMENT ON COLUMN public.interview.created_at IS 'class=S';
COMMENT ON COLUMN public.interview.updated_at IS 'class=S';
COMMENT ON TABLE public.interview IS 'domain=ta;source=graph';

-- background_check: Vendor check plus the FCRA adverse-action stages. Findings are special category: HR only.
CREATE TABLE public.background_check (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    candidate_id                    uuid NOT NULL,
    vendor                          text NOT NULL,
    ordered_at                      timestamptz NOT NULL,
    status                          text NOT NULL,
    findings_summary                text,
    adverse_action_stage            text,
    pre_adverse_notice_at           timestamptz,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.background_check.id IS 'class=S';
COMMENT ON COLUMN public.background_check.tenant_id IS 'class=S';
COMMENT ON COLUMN public.background_check.candidate_id IS 'class=S';
COMMENT ON COLUMN public.background_check.vendor IS 'class=C0';
COMMENT ON COLUMN public.background_check.ordered_at IS 'class=S';
COMMENT ON COLUMN public.background_check.status IS 'class=S';
COMMENT ON COLUMN public.background_check.findings_summary IS 'class=C4';
COMMENT ON COLUMN public.background_check.adverse_action_stage IS 'class=S';
COMMENT ON COLUMN public.background_check.pre_adverse_notice_at IS 'class=S';
COMMENT ON COLUMN public.background_check.created_at IS 'class=S';
COMMENT ON COLUMN public.background_check.updated_at IS 'class=S';
COMMENT ON TABLE public.background_check IS 'domain=ta;source=graph';

-- offer: Offer drafted from the approved band. within_band false routes to the founder.
CREATE TABLE public.offer (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    application_id                  uuid NOT NULL,
    comp_band_id                    uuid NOT NULL,
    proposed_base                   numeric(14,2) NOT NULL,
    proposed_equity                 numeric(14,2),
    within_band                     boolean NOT NULL,
    approval_request_id             uuid,
    offer_document_id               uuid,
    sent_at                         timestamptz,
    accepted_at                     timestamptz,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.offer.id IS 'class=S';
COMMENT ON COLUMN public.offer.tenant_id IS 'class=S';
COMMENT ON COLUMN public.offer.application_id IS 'class=S';
COMMENT ON COLUMN public.offer.comp_band_id IS 'class=S';
COMMENT ON COLUMN public.offer.proposed_base IS 'class=C2';
COMMENT ON COLUMN public.offer.proposed_equity IS 'class=C2';
COMMENT ON COLUMN public.offer.within_band IS 'class=S';
COMMENT ON COLUMN public.offer.approval_request_id IS 'class=S';
COMMENT ON COLUMN public.offer.offer_document_id IS 'class=S';
COMMENT ON COLUMN public.offer.sent_at IS 'class=S';
COMMENT ON COLUMN public.offer.accepted_at IS 'class=S';
COMMENT ON COLUMN public.offer.created_at IS 'class=S';
COMMENT ON COLUMN public.offer.updated_at IS 'class=S';
COMMENT ON TABLE public.offer IS 'domain=ta;source=graph';

-- checklist: One checklist per lifecycle event. kind is onboarding or offboarding, so ER reuses the same shape.
CREATE TABLE public.checklist (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    kind                            text NOT NULL,
    template_key                    text NOT NULL,
    status                          text NOT NULL,
    due_date                        date NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.checklist.id IS 'class=S';
COMMENT ON COLUMN public.checklist.tenant_id IS 'class=S';
COMMENT ON COLUMN public.checklist.employee_id IS 'class=S';
COMMENT ON COLUMN public.checklist.kind IS 'class=S';
COMMENT ON COLUMN public.checklist.template_key IS 'class=C0';
COMMENT ON COLUMN public.checklist.status IS 'class=S';
COMMENT ON COLUMN public.checklist.due_date IS 'class=S';
COMMENT ON COLUMN public.checklist.created_at IS 'class=S';
COMMENT ON COLUMN public.checklist.updated_at IS 'class=S';
COMMENT ON TABLE public.checklist IS 'domain=ob;source=graph';

-- checklist_task: Tasks owned by different domains (IT, payroll, the manager, the new hire). blocking tasks hold the next stage.
CREATE TABLE public.checklist_task (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    checklist_id                    uuid NOT NULL,
    owner_domain                    text NOT NULL,
    assignee_user_id                uuid,
    title                           text NOT NULL,
    status                          text NOT NULL,
    due_at                          timestamptz NOT NULL,
    completed_at                    timestamptz,
    blocking                        boolean NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.checklist_task.id IS 'class=S';
COMMENT ON COLUMN public.checklist_task.tenant_id IS 'class=S';
COMMENT ON COLUMN public.checklist_task.checklist_id IS 'class=S';
COMMENT ON COLUMN public.checklist_task.owner_domain IS 'class=S';
COMMENT ON COLUMN public.checklist_task.assignee_user_id IS 'class=S';
COMMENT ON COLUMN public.checklist_task.title IS 'class=C0';
COMMENT ON COLUMN public.checklist_task.status IS 'class=S';
COMMENT ON COLUMN public.checklist_task.due_at IS 'class=S';
COMMENT ON COLUMN public.checklist_task.completed_at IS 'class=S';
COMMENT ON COLUMN public.checklist_task.blocking IS 'class=S';
COMMENT ON COLUMN public.checklist_task.created_at IS 'class=S';
COMMENT ON COLUMN public.checklist_task.updated_at IS 'class=S';
COMMENT ON TABLE public.checklist_task IS 'domain=ob;source=graph';

-- access_role_template: Default app bundle per job profile and department. Anything outside it is an exception gate.
CREATE TABLE public.access_role_template (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    job_profile_id                  uuid NOT NULL,
    department_id                   uuid,
    app_bundle                      jsonb NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.access_role_template.id IS 'class=S';
COMMENT ON COLUMN public.access_role_template.tenant_id IS 'class=S';
COMMENT ON COLUMN public.access_role_template.job_profile_id IS 'class=S';
COMMENT ON COLUMN public.access_role_template.department_id IS 'class=S';
COMMENT ON COLUMN public.access_role_template.app_bundle IS 'class=C0';
COMMENT ON COLUMN public.access_role_template.created_at IS 'class=S';
COMMENT ON COLUMN public.access_role_template.updated_at IS 'class=S';
COMMENT ON TABLE public.access_role_template IS 'domain=it;source=graph';

-- identity_account: Directory identity (Google, Okta, Entra). Deprovisioning always passes through a gate.
CREATE TABLE public.identity_account (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    directory_provider              text NOT NULL,
    external_id                     text NOT NULL,
    status                          text NOT NULL,
    provisioned_at                  timestamptz NOT NULL,
    deprovisioned_at                timestamptz,
    approval_request_id             uuid,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.identity_account.id IS 'class=S';
COMMENT ON COLUMN public.identity_account.tenant_id IS 'class=S';
COMMENT ON COLUMN public.identity_account.employee_id IS 'class=S';
COMMENT ON COLUMN public.identity_account.directory_provider IS 'class=C0';
COMMENT ON COLUMN public.identity_account.external_id IS 'class=C1';
COMMENT ON COLUMN public.identity_account.status IS 'class=S';
COMMENT ON COLUMN public.identity_account.provisioned_at IS 'class=S';
COMMENT ON COLUMN public.identity_account.deprovisioned_at IS 'class=S';
COMMENT ON COLUMN public.identity_account.approval_request_id IS 'class=S';
COMMENT ON COLUMN public.identity_account.created_at IS 'class=S';
COMMENT ON COLUMN public.identity_account.updated_at IS 'class=S';
COMMENT ON TABLE public.identity_account IS 'domain=it;source=graph';

-- app_access_grant: Per-app access with its source (template or exception). The input to access-compliance-auditor’s drift check.
CREATE TABLE public.app_access_grant (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    identity_account_id             uuid NOT NULL,
    app_name                        text NOT NULL,
    permission_level                text NOT NULL,
    source                          text NOT NULL,
    template_id                     uuid,
    approval_request_id             uuid,
    granted_at                      timestamptz NOT NULL,
    revoked_at                      timestamptz,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.app_access_grant.id IS 'class=S';
COMMENT ON COLUMN public.app_access_grant.tenant_id IS 'class=S';
COMMENT ON COLUMN public.app_access_grant.identity_account_id IS 'class=S';
COMMENT ON COLUMN public.app_access_grant.app_name IS 'class=C0';
COMMENT ON COLUMN public.app_access_grant.permission_level IS 'class=C0';
COMMENT ON COLUMN public.app_access_grant.source IS 'class=S';
COMMENT ON COLUMN public.app_access_grant.template_id IS 'class=S';
COMMENT ON COLUMN public.app_access_grant.approval_request_id IS 'class=S';
COMMENT ON COLUMN public.app_access_grant.granted_at IS 'class=S';
COMMENT ON COLUMN public.app_access_grant.revoked_at IS 'class=S';
COMMENT ON COLUMN public.app_access_grant.created_at IS 'class=S';
COMMENT ON COLUMN public.app_access_grant.updated_at IS 'class=S';
COMMENT ON TABLE public.app_access_grant IS 'domain=it;source=graph';

-- device: Hardware inventory.
CREATE TABLE public.device (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    asset_tag                       text NOT NULL,
    model                           text NOT NULL,
    serial_no                       text NOT NULL,
    status                          text NOT NULL,
    purchase_cost                   numeric(14,2) NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.device.id IS 'class=S';
COMMENT ON COLUMN public.device.tenant_id IS 'class=S';
COMMENT ON COLUMN public.device.asset_tag IS 'class=C0';
COMMENT ON COLUMN public.device.model IS 'class=C0';
COMMENT ON COLUMN public.device.serial_no IS 'class=C1';
COMMENT ON COLUMN public.device.status IS 'class=S';
COMMENT ON COLUMN public.device.purchase_cost IS 'class=C0';
COMMENT ON COLUMN public.device.created_at IS 'class=S';
COMMENT ON COLUMN public.device.updated_at IS 'class=S';
COMMENT ON TABLE public.device IS 'domain=it;source=graph';

-- device_assignment: Who holds which device, including the shipping address (restricted).
CREATE TABLE public.device_assignment (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    device_id                       uuid NOT NULL,
    employee_id                     uuid NOT NULL,
    assigned_at                     timestamptz NOT NULL,
    shipped_to_address              text,
    tracking_no                     text,
    returned_at                     timestamptz,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.device_assignment.id IS 'class=S';
COMMENT ON COLUMN public.device_assignment.tenant_id IS 'class=S';
COMMENT ON COLUMN public.device_assignment.device_id IS 'class=S';
COMMENT ON COLUMN public.device_assignment.employee_id IS 'class=S';
COMMENT ON COLUMN public.device_assignment.assigned_at IS 'class=S';
COMMENT ON COLUMN public.device_assignment.shipped_to_address IS 'class=C3';
COMMENT ON COLUMN public.device_assignment.tracking_no IS 'class=C1';
COMMENT ON COLUMN public.device_assignment.returned_at IS 'class=S';
COMMENT ON COLUMN public.device_assignment.created_at IS 'class=S';
COMMENT ON COLUMN public.device_assignment.updated_at IS 'class=S';
COMMENT ON TABLE public.device_assignment IS 'domain=it;source=graph';

-- payroll_profile: Per-employee pay setup. Carries the tax-residency fields from the gap analysis (work_state vs tax_state, reciprocity) plus India UAN and ESIC numbers.
CREATE TABLE public.payroll_profile (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    pay_frequency                   text NOT NULL,
    payment_method                  text NOT NULL,
    work_state                      text NOT NULL,
    tax_state                       text NOT NULL,
    reciprocity_agreement_flag      boolean NOT NULL,
    state_registration_status       text NOT NULL,
    w4_elections                    jsonb NOT NULL,
    uan_number                      text NOT NULL,
    esic_ip_number                  text NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.payroll_profile.id IS 'class=S';
COMMENT ON COLUMN public.payroll_profile.tenant_id IS 'class=S';
COMMENT ON COLUMN public.payroll_profile.employee_id IS 'class=S';
COMMENT ON COLUMN public.payroll_profile.pay_frequency IS 'class=C1';
COMMENT ON COLUMN public.payroll_profile.payment_method IS 'class=S';
COMMENT ON COLUMN public.payroll_profile.work_state IS 'class=C1';
COMMENT ON COLUMN public.payroll_profile.tax_state IS 'class=C1;pack=US';
COMMENT ON COLUMN public.payroll_profile.reciprocity_agreement_flag IS 'class=S;pack=US';
COMMENT ON COLUMN public.payroll_profile.state_registration_status IS 'class=S;pack=US';
COMMENT ON COLUMN public.payroll_profile.w4_elections IS 'class=C2;pack=US';
COMMENT ON COLUMN public.payroll_profile.uan_number IS 'class=C3;pack=IN';
COMMENT ON COLUMN public.payroll_profile.esic_ip_number IS 'class=C3;pack=IN';
COMMENT ON COLUMN public.payroll_profile.created_at IS 'class=S';
COMMENT ON COLUMN public.payroll_profile.updated_at IS 'class=S';
COMMENT ON TABLE public.payroll_profile IS 'domain=pay;source=gap';

-- payroll_run: One cycle for one legal entity. Maker-checker: payroll builds it, the founder releases it.
CREATE TABLE public.payroll_run (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    legal_entity_id                 uuid NOT NULL,
    period_start                    date NOT NULL,
    period_end                      date NOT NULL,
    status                          text NOT NULL,
    gross_total                     numeric(14,2) NOT NULL,
    net_total                       numeric(14,2) NOT NULL,
    anomaly_score                   numeric(14,2),
    approval_request_id             uuid,
    disbursed_at                    timestamptz,
    retention_class                 uuid NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.payroll_run.id IS 'class=S';
COMMENT ON COLUMN public.payroll_run.tenant_id IS 'class=S';
COMMENT ON COLUMN public.payroll_run.legal_entity_id IS 'class=S';
COMMENT ON COLUMN public.payroll_run.period_start IS 'class=S';
COMMENT ON COLUMN public.payroll_run.period_end IS 'class=S';
COMMENT ON COLUMN public.payroll_run.status IS 'class=S';
COMMENT ON COLUMN public.payroll_run.gross_total IS 'class=C2;derived';
COMMENT ON COLUMN public.payroll_run.net_total IS 'class=C2;derived';
COMMENT ON COLUMN public.payroll_run.anomaly_score IS 'class=S';
COMMENT ON COLUMN public.payroll_run.approval_request_id IS 'class=S';
COMMENT ON COLUMN public.payroll_run.disbursed_at IS 'class=S';
COMMENT ON COLUMN public.payroll_run.retention_class IS 'class=S';
COMMENT ON COLUMN public.payroll_run.created_at IS 'class=S';
COMMENT ON COLUMN public.payroll_run.updated_at IS 'class=S';
COMMENT ON TABLE public.payroll_run IS 'domain=pay;source=doc';

-- payslip: Derived per employee per run, and pinned to the employment_record version it used so it stays an honest record after later changes.
CREATE TABLE public.payslip (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    payroll_run_id                  uuid NOT NULL,
    employee_id                     uuid NOT NULL,
    employment_record_id            uuid NOT NULL,
    gross_pay                       numeric(14,2) NOT NULL,
    net_pay                         numeric(14,2) NOT NULL,
    tax_withheld                    numeric(14,2) NOT NULL,
    issued_at                       timestamptz,
    retention_class                 uuid NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.payslip.id IS 'class=S';
COMMENT ON COLUMN public.payslip.tenant_id IS 'class=S';
COMMENT ON COLUMN public.payslip.payroll_run_id IS 'class=S';
COMMENT ON COLUMN public.payslip.employee_id IS 'class=S';
COMMENT ON COLUMN public.payslip.employment_record_id IS 'class=S';
COMMENT ON COLUMN public.payslip.gross_pay IS 'class=C2;derived';
COMMENT ON COLUMN public.payslip.net_pay IS 'class=C2;derived';
COMMENT ON COLUMN public.payslip.tax_withheld IS 'class=C2;derived';
COMMENT ON COLUMN public.payslip.issued_at IS 'class=S';
COMMENT ON COLUMN public.payslip.retention_class IS 'class=S';
COMMENT ON COLUMN public.payslip.created_at IS 'class=S';
COMMENT ON COLUMN public.payslip.updated_at IS 'class=S';
COMMENT ON TABLE public.payslip IS 'domain=pay;source=doc';

-- payslip_line: Earnings and deduction components, each pointing at the rule row that produced it, so a recompute is explainable line by line.
CREATE TABLE public.payslip_line (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    payslip_id                      uuid NOT NULL,
    component_code                  text NOT NULL,
    amount                          numeric(14,2) NOT NULL,
    rule_id                         uuid,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.payslip_line.id IS 'class=S';
COMMENT ON COLUMN public.payslip_line.tenant_id IS 'class=S';
COMMENT ON COLUMN public.payslip_line.payslip_id IS 'class=S';
COMMENT ON COLUMN public.payslip_line.component_code IS 'class=C0';
COMMENT ON COLUMN public.payslip_line.amount IS 'class=C2';
COMMENT ON COLUMN public.payslip_line.rule_id IS 'class=S';
COMMENT ON COLUMN public.payslip_line.created_at IS 'class=S';
COMMENT ON COLUMN public.payslip_line.updated_at IS 'class=S';
COMMENT ON TABLE public.payslip_line IS 'domain=pay;source=new';

-- garnishment_order: Court-ordered deductions. Special category: the issuing authority and order reveal legal circumstances.
CREATE TABLE public.garnishment_order (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    issuing_authority               text NOT NULL,
    order_type                      text NOT NULL,
    amount_or_pct                   numeric(14,2) NOT NULL,
    priority                        integer NOT NULL,
    effective_from                  date NOT NULL,
    effective_to                    date,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.garnishment_order.id IS 'class=S';
COMMENT ON COLUMN public.garnishment_order.tenant_id IS 'class=S';
COMMENT ON COLUMN public.garnishment_order.employee_id IS 'class=S';
COMMENT ON COLUMN public.garnishment_order.issuing_authority IS 'class=C4';
COMMENT ON COLUMN public.garnishment_order.order_type IS 'class=C4';
COMMENT ON COLUMN public.garnishment_order.amount_or_pct IS 'class=C4';
COMMENT ON COLUMN public.garnishment_order.priority IS 'class=S';
COMMENT ON COLUMN public.garnishment_order.effective_from IS 'class=S';
COMMENT ON COLUMN public.garnishment_order.effective_to IS 'class=S';
COMMENT ON COLUMN public.garnishment_order.created_at IS 'class=S';
COMMENT ON COLUMN public.garnishment_order.updated_at IS 'class=S';
COMMENT ON TABLE public.garnishment_order IS 'domain=pay;source=graph';

-- filing_record: One statutory submission (ECR, ESI, 24Q, 941, W-2, state UI) with its acknowledgement.
CREATE TABLE public.filing_record (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    legal_entity_id                 uuid NOT NULL,
    scheme                          text NOT NULL,
    period                          text NOT NULL,
    filed_on                        date,
    acknowledgement_no              text,
    document_id                     uuid,
    approval_request_id             uuid,
    retention_class                 uuid NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.filing_record.id IS 'class=S';
COMMENT ON COLUMN public.filing_record.tenant_id IS 'class=S';
COMMENT ON COLUMN public.filing_record.legal_entity_id IS 'class=S';
COMMENT ON COLUMN public.filing_record.scheme IS 'class=C0';
COMMENT ON COLUMN public.filing_record.period IS 'class=C0';
COMMENT ON COLUMN public.filing_record.filed_on IS 'class=S';
COMMENT ON COLUMN public.filing_record.acknowledgement_no IS 'class=C1';
COMMENT ON COLUMN public.filing_record.document_id IS 'class=S';
COMMENT ON COLUMN public.filing_record.approval_request_id IS 'class=S';
COMMENT ON COLUMN public.filing_record.retention_class IS 'class=S';
COMMENT ON COLUMN public.filing_record.created_at IS 'class=S';
COMMENT ON COLUMN public.filing_record.updated_at IS 'class=S';
COMMENT ON TABLE public.filing_record IS 'domain=pay;source=doc';

-- gratuity_accrual_balance: Running per-employee gratuity liability, read (not recomputed) by final settlement at exit.
CREATE TABLE public.gratuity_accrual_balance (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    as_of_period                    date NOT NULL,
    accrued_amount                  numeric(14,2) NOT NULL,
    gratuity_wage_base              numeric(14,2) NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.gratuity_accrual_balance.id IS 'class=S';
COMMENT ON COLUMN public.gratuity_accrual_balance.tenant_id IS 'class=S';
COMMENT ON COLUMN public.gratuity_accrual_balance.employee_id IS 'class=S';
COMMENT ON COLUMN public.gratuity_accrual_balance.as_of_period IS 'class=S';
COMMENT ON COLUMN public.gratuity_accrual_balance.accrued_amount IS 'class=C2';
COMMENT ON COLUMN public.gratuity_accrual_balance.gratuity_wage_base IS 'class=C2';
COMMENT ON COLUMN public.gratuity_accrual_balance.created_at IS 'class=S';
COMMENT ON COLUMN public.gratuity_accrual_balance.updated_at IS 'class=S';
COMMENT ON TABLE public.gratuity_accrual_balance IS 'domain=pay;source=doc;pack=IN';

-- contractor_invoice: Global and contractor invoices routed through local payment rails.
CREATE TABLE public.contractor_invoice (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    contractor_employee_id          uuid NOT NULL,
    legal_entity_id                 uuid NOT NULL,
    period                          text NOT NULL,
    amount                          numeric(14,2) NOT NULL,
    currency                        text NOT NULL,
    status                          text NOT NULL,
    approval_request_id             uuid,
    paid_at                         timestamptz,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.contractor_invoice.id IS 'class=S';
COMMENT ON COLUMN public.contractor_invoice.tenant_id IS 'class=S';
COMMENT ON COLUMN public.contractor_invoice.contractor_employee_id IS 'class=S';
COMMENT ON COLUMN public.contractor_invoice.legal_entity_id IS 'class=S';
COMMENT ON COLUMN public.contractor_invoice.period IS 'class=C0';
COMMENT ON COLUMN public.contractor_invoice.amount IS 'class=C2';
COMMENT ON COLUMN public.contractor_invoice.currency IS 'class=C0';
COMMENT ON COLUMN public.contractor_invoice.status IS 'class=S';
COMMENT ON COLUMN public.contractor_invoice.approval_request_id IS 'class=S';
COMMENT ON COLUMN public.contractor_invoice.paid_at IS 'class=S';
COMMENT ON COLUMN public.contractor_invoice.created_at IS 'class=S';
COMMENT ON COLUMN public.contractor_invoice.updated_at IS 'class=S';
COMMENT ON TABLE public.contractor_invoice IS 'domain=pay;source=graph';

-- benefit_plan: Plans offered per entity and plan year (group health in India, medical and 401k in the US).
CREATE TABLE public.benefit_plan (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    legal_entity_id                 uuid NOT NULL,
    plan_type                       text NOT NULL,
    carrier                         text NOT NULL,
    plan_year                       integer NOT NULL,
    employer_contribution           numeric(14,2) NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.benefit_plan.id IS 'class=S';
COMMENT ON COLUMN public.benefit_plan.tenant_id IS 'class=S';
COMMENT ON COLUMN public.benefit_plan.legal_entity_id IS 'class=S';
COMMENT ON COLUMN public.benefit_plan.plan_type IS 'class=C0';
COMMENT ON COLUMN public.benefit_plan.carrier IS 'class=C0';
COMMENT ON COLUMN public.benefit_plan.plan_year IS 'class=C0';
COMMENT ON COLUMN public.benefit_plan.employer_contribution IS 'class=C0';
COMMENT ON COLUMN public.benefit_plan.created_at IS 'class=S';
COMMENT ON COLUMN public.benefit_plan.updated_at IS 'class=S';
COMMENT ON TABLE public.benefit_plan IS 'domain=ben;source=graph';

-- benefit_election: What the employee chose, effective-dated, and when it reached the carrier.
CREATE TABLE public.benefit_election (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    benefit_plan_id                 uuid NOT NULL,
    coverage_tier                   text NOT NULL,
    employee_cost                   numeric(14,2) NOT NULL,
    life_event_id                   uuid,
    effective_from                  date NOT NULL,
    effective_to                    date,
    carrier_sent_at                 timestamptz,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.benefit_election.id IS 'class=S';
COMMENT ON COLUMN public.benefit_election.tenant_id IS 'class=S';
COMMENT ON COLUMN public.benefit_election.employee_id IS 'class=S';
COMMENT ON COLUMN public.benefit_election.benefit_plan_id IS 'class=S';
COMMENT ON COLUMN public.benefit_election.coverage_tier IS 'class=C2';
COMMENT ON COLUMN public.benefit_election.employee_cost IS 'class=C2';
COMMENT ON COLUMN public.benefit_election.life_event_id IS 'class=S';
COMMENT ON COLUMN public.benefit_election.effective_from IS 'class=S';
COMMENT ON COLUMN public.benefit_election.effective_to IS 'class=S';
COMMENT ON COLUMN public.benefit_election.carrier_sent_at IS 'class=S';
COMMENT ON COLUMN public.benefit_election.created_at IS 'class=S';
COMMENT ON COLUMN public.benefit_election.updated_at IS 'class=S';
COMMENT ON TABLE public.benefit_election IS 'domain=ben;source=graph';

-- dependent: Covered family members. Restricted PII about people who are not employees.
CREATE TABLE public.dependent (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    full_name                       text NOT NULL,
    relationship                    text NOT NULL,
    date_of_birth                   date NOT NULL,
    covered_plan_ids                jsonb NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.dependent.id IS 'class=S';
COMMENT ON COLUMN public.dependent.tenant_id IS 'class=S';
COMMENT ON COLUMN public.dependent.employee_id IS 'class=S';
COMMENT ON COLUMN public.dependent.full_name IS 'class=C3';
COMMENT ON COLUMN public.dependent.relationship IS 'class=C3';
COMMENT ON COLUMN public.dependent.date_of_birth IS 'class=C3';
COMMENT ON COLUMN public.dependent.covered_plan_ids IS 'class=C2';
COMMENT ON COLUMN public.dependent.created_at IS 'class=S';
COMMENT ON COLUMN public.dependent.updated_at IS 'class=S';
COMMENT ON TABLE public.dependent IS 'domain=ben;source=graph';

-- life_event: Qualifying life events. The event type itself (divorce, birth) is special category.
CREATE TABLE public.life_event (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    event_type                      text NOT NULL,
    event_date                      date NOT NULL,
    evidence_document_id            uuid,
    status                          text NOT NULL,
    window_closes_at                date NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.life_event.id IS 'class=S';
COMMENT ON COLUMN public.life_event.tenant_id IS 'class=S';
COMMENT ON COLUMN public.life_event.employee_id IS 'class=S';
COMMENT ON COLUMN public.life_event.event_type IS 'class=C4';
COMMENT ON COLUMN public.life_event.event_date IS 'class=C3';
COMMENT ON COLUMN public.life_event.evidence_document_id IS 'class=S';
COMMENT ON COLUMN public.life_event.status IS 'class=S';
COMMENT ON COLUMN public.life_event.window_closes_at IS 'class=S';
COMMENT ON COLUMN public.life_event.created_at IS 'class=S';
COMMENT ON COLUMN public.life_event.updated_at IS 'class=S';
COMMENT ON TABLE public.life_event IS 'domain=ben;source=graph';

-- cobra_event: COBRA qualifying events and the statutory notice timeline.
CREATE TABLE public.cobra_event (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    qualifying_event                text NOT NULL,
    event_date                      date NOT NULL,
    notice_due_at                   date NOT NULL,
    notice_sent_at                  timestamptz,
    election_status                 text NOT NULL,
    approval_request_id             uuid,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.cobra_event.id IS 'class=S';
COMMENT ON COLUMN public.cobra_event.tenant_id IS 'class=S';
COMMENT ON COLUMN public.cobra_event.employee_id IS 'class=S';
COMMENT ON COLUMN public.cobra_event.qualifying_event IS 'class=C2';
COMMENT ON COLUMN public.cobra_event.event_date IS 'class=S';
COMMENT ON COLUMN public.cobra_event.notice_due_at IS 'class=S';
COMMENT ON COLUMN public.cobra_event.notice_sent_at IS 'class=S';
COMMENT ON COLUMN public.cobra_event.election_status IS 'class=S';
COMMENT ON COLUMN public.cobra_event.approval_request_id IS 'class=S';
COMMENT ON COLUMN public.cobra_event.created_at IS 'class=S';
COMMENT ON COLUMN public.cobra_event.updated_at IS 'class=S';
COMMENT ON TABLE public.cobra_event IS 'domain=ben;source=graph;pack=US';

-- time_punch: Raw punches. Geo is restricted and optional.
CREATE TABLE public.time_punch (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    punched_at                      timestamptz NOT NULL,
    kind                            text NOT NULL,
    source                          text NOT NULL,
    geo_point                       text,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.time_punch.id IS 'class=S';
COMMENT ON COLUMN public.time_punch.tenant_id IS 'class=S';
COMMENT ON COLUMN public.time_punch.employee_id IS 'class=S';
COMMENT ON COLUMN public.time_punch.punched_at IS 'class=C1';
COMMENT ON COLUMN public.time_punch.kind IS 'class=S';
COMMENT ON COLUMN public.time_punch.source IS 'class=S';
COMMENT ON COLUMN public.time_punch.geo_point IS 'class=C3';
COMMENT ON COLUMN public.time_punch.created_at IS 'class=S';
COMMENT ON COLUMN public.time_punch.updated_at IS 'class=S';
COMMENT ON TABLE public.time_punch IS 'domain=time;source=graph';

-- timecard: Approved hours per period, the hand-off from time to payroll.
CREATE TABLE public.timecard (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    period_start                    date NOT NULL,
    period_end                      date NOT NULL,
    regular_hours                   numeric(14,2) NOT NULL,
    overtime_hours                  numeric(14,2) NOT NULL,
    status                          text NOT NULL,
    approved_by_user_id             uuid,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.timecard.id IS 'class=S';
COMMENT ON COLUMN public.timecard.tenant_id IS 'class=S';
COMMENT ON COLUMN public.timecard.employee_id IS 'class=S';
COMMENT ON COLUMN public.timecard.period_start IS 'class=S';
COMMENT ON COLUMN public.timecard.period_end IS 'class=S';
COMMENT ON COLUMN public.timecard.regular_hours IS 'class=C2';
COMMENT ON COLUMN public.timecard.overtime_hours IS 'class=C2';
COMMENT ON COLUMN public.timecard.status IS 'class=S';
COMMENT ON COLUMN public.timecard.approved_by_user_id IS 'class=S';
COMMENT ON COLUMN public.timecard.created_at IS 'class=S';
COMMENT ON COLUMN public.timecard.updated_at IS 'class=S';
COMMENT ON TABLE public.timecard IS 'domain=time;source=graph';

-- leave_policy: Leave types and accrual rules per entity.
CREATE TABLE public.leave_policy (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    legal_entity_id                 uuid NOT NULL,
    leave_type                      text NOT NULL,
    accrual_rule                    jsonb NOT NULL,
    carry_forward_cap               numeric(14,2) NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.leave_policy.id IS 'class=S';
COMMENT ON COLUMN public.leave_policy.tenant_id IS 'class=S';
COMMENT ON COLUMN public.leave_policy.legal_entity_id IS 'class=S';
COMMENT ON COLUMN public.leave_policy.leave_type IS 'class=C0';
COMMENT ON COLUMN public.leave_policy.accrual_rule IS 'class=C0';
COMMENT ON COLUMN public.leave_policy.carry_forward_cap IS 'class=C0';
COMMENT ON COLUMN public.leave_policy.created_at IS 'class=S';
COMMENT ON COLUMN public.leave_policy.updated_at IS 'class=S';
COMMENT ON TABLE public.leave_policy IS 'domain=time;source=graph';

-- leave_balance: Accrued balance per policy, also read by final settlement for encashment.
CREATE TABLE public.leave_balance (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    leave_policy_id                 uuid NOT NULL,
    balance_days                    numeric(14,2) NOT NULL,
    as_of                           date NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.leave_balance.id IS 'class=S';
COMMENT ON COLUMN public.leave_balance.tenant_id IS 'class=S';
COMMENT ON COLUMN public.leave_balance.employee_id IS 'class=S';
COMMENT ON COLUMN public.leave_balance.leave_policy_id IS 'class=S';
COMMENT ON COLUMN public.leave_balance.balance_days IS 'class=C2';
COMMENT ON COLUMN public.leave_balance.as_of IS 'class=S';
COMMENT ON COLUMN public.leave_balance.created_at IS 'class=S';
COMMENT ON COLUMN public.leave_balance.updated_at IS 'class=S';
COMMENT ON TABLE public.leave_balance IS 'domain=time;source=graph';

-- leave_request: Dates are visible to managers; the medical or family reason is special category and hidden from them.
CREATE TABLE public.leave_request (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    leave_policy_id                 uuid NOT NULL,
    start_date                      date NOT NULL,
    end_date                        date NOT NULL,
    status                          text NOT NULL,
    reason_detail                   text,
    fmla_designation                text,
    approval_request_id             uuid,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.leave_request.id IS 'class=S';
COMMENT ON COLUMN public.leave_request.tenant_id IS 'class=S';
COMMENT ON COLUMN public.leave_request.employee_id IS 'class=S';
COMMENT ON COLUMN public.leave_request.leave_policy_id IS 'class=S';
COMMENT ON COLUMN public.leave_request.start_date IS 'class=C1';
COMMENT ON COLUMN public.leave_request.end_date IS 'class=C1';
COMMENT ON COLUMN public.leave_request.status IS 'class=S';
COMMENT ON COLUMN public.leave_request.reason_detail IS 'class=C4';
COMMENT ON COLUMN public.leave_request.fmla_designation IS 'class=C4;pack=US';
COMMENT ON COLUMN public.leave_request.approval_request_id IS 'class=S';
COMMENT ON COLUMN public.leave_request.created_at IS 'class=S';
COMMENT ON COLUMN public.leave_request.updated_at IS 'class=S';
COMMENT ON TABLE public.leave_request IS 'domain=time;source=graph';

-- compensation_event: A proposed pay change (merit, promotion, adjustment, bonus). Approval writes a new employment_record version rather than editing the old one.
CREATE TABLE public.compensation_event (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    event_type                      text NOT NULL,
    cycle_ref                       text NOT NULL,
    proposed_amount                 numeric(14,2) NOT NULL,
    comp_band_id                    uuid,
    out_of_band                     boolean NOT NULL,
    proposed_by_user_id             uuid NOT NULL,
    approval_request_id             uuid,
    resulting_record_id             uuid,
    effective_date                  date NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.compensation_event.id IS 'class=S';
COMMENT ON COLUMN public.compensation_event.tenant_id IS 'class=S';
COMMENT ON COLUMN public.compensation_event.employee_id IS 'class=S';
COMMENT ON COLUMN public.compensation_event.event_type IS 'class=S';
COMMENT ON COLUMN public.compensation_event.cycle_ref IS 'class=C0';
COMMENT ON COLUMN public.compensation_event.proposed_amount IS 'class=C2';
COMMENT ON COLUMN public.compensation_event.comp_band_id IS 'class=S';
COMMENT ON COLUMN public.compensation_event.out_of_band IS 'class=S';
COMMENT ON COLUMN public.compensation_event.proposed_by_user_id IS 'class=S';
COMMENT ON COLUMN public.compensation_event.approval_request_id IS 'class=S';
COMMENT ON COLUMN public.compensation_event.resulting_record_id IS 'class=S';
COMMENT ON COLUMN public.compensation_event.effective_date IS 'class=S';
COMMENT ON COLUMN public.compensation_event.created_at IS 'class=S';
COMMENT ON COLUMN public.compensation_event.updated_at IS 'class=S';
COMMENT ON TABLE public.compensation_event IS 'domain=comp;source=gap';

-- equity_grant: Options, RSUs and Indian ESOPs, priced against the valuation in force on the grant date.
CREATE TABLE public.equity_grant (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    grant_type                      text NOT NULL,
    shares                          numeric(14,2) NOT NULL,
    strike_price                    numeric(14,2) NOT NULL,
    grant_date                      date NOT NULL,
    valuation_409a_id               uuid,
    board_approved_at               date,
    approval_request_id             uuid,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.equity_grant.id IS 'class=S';
COMMENT ON COLUMN public.equity_grant.tenant_id IS 'class=S';
COMMENT ON COLUMN public.equity_grant.employee_id IS 'class=S';
COMMENT ON COLUMN public.equity_grant.grant_type IS 'class=C2';
COMMENT ON COLUMN public.equity_grant.shares IS 'class=C2';
COMMENT ON COLUMN public.equity_grant.strike_price IS 'class=C2';
COMMENT ON COLUMN public.equity_grant.grant_date IS 'class=S';
COMMENT ON COLUMN public.equity_grant.valuation_409a_id IS 'class=S';
COMMENT ON COLUMN public.equity_grant.board_approved_at IS 'class=S';
COMMENT ON COLUMN public.equity_grant.approval_request_id IS 'class=S';
COMMENT ON COLUMN public.equity_grant.created_at IS 'class=S';
COMMENT ON COLUMN public.equity_grant.updated_at IS 'class=S';
COMMENT ON TABLE public.equity_grant IS 'domain=comp;source=gap';

-- vesting_event: Scheduled and realised vesting tranches.
CREATE TABLE public.vesting_event (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    equity_grant_id                 uuid NOT NULL,
    vest_date                       date NOT NULL,
    shares_vested                   numeric(14,2) NOT NULL,
    status                          text NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.vesting_event.id IS 'class=S';
COMMENT ON COLUMN public.vesting_event.tenant_id IS 'class=S';
COMMENT ON COLUMN public.vesting_event.equity_grant_id IS 'class=S';
COMMENT ON COLUMN public.vesting_event.vest_date IS 'class=S';
COMMENT ON COLUMN public.vesting_event.shares_vested IS 'class=C2';
COMMENT ON COLUMN public.vesting_event.status IS 'class=S';
COMMENT ON COLUMN public.vesting_event.created_at IS 'class=S';
COMMENT ON COLUMN public.vesting_event.updated_at IS 'class=S';
COMMENT ON TABLE public.vesting_event IS 'domain=comp;source=gap';

-- option_exercise: Exercises with FMV and withholding, an irreversible worker.
CREATE TABLE public.option_exercise (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    equity_grant_id                 uuid NOT NULL,
    exercised_at                    timestamptz NOT NULL,
    shares                          numeric(14,2) NOT NULL,
    fmv_at_exercise                 numeric(14,2) NOT NULL,
    tax_withheld                    numeric(14,2) NOT NULL,
    status                          text NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.option_exercise.id IS 'class=S';
COMMENT ON COLUMN public.option_exercise.tenant_id IS 'class=S';
COMMENT ON COLUMN public.option_exercise.equity_grant_id IS 'class=S';
COMMENT ON COLUMN public.option_exercise.exercised_at IS 'class=S';
COMMENT ON COLUMN public.option_exercise.shares IS 'class=C2';
COMMENT ON COLUMN public.option_exercise.fmv_at_exercise IS 'class=C2';
COMMENT ON COLUMN public.option_exercise.tax_withheld IS 'class=C2';
COMMENT ON COLUMN public.option_exercise.status IS 'class=S';
COMMENT ON COLUMN public.option_exercise.created_at IS 'class=S';
COMMENT ON COLUMN public.option_exercise.updated_at IS 'class=S';
COMMENT ON TABLE public.option_exercise IS 'domain=comp;source=graph';

-- valuation_409a: US 409A, or the India Rule 11UA FMV report used for ESOP perquisite tax. Stale valuations trip the 409A gate.
CREATE TABLE public.valuation_409a (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    legal_entity_id                 uuid NOT NULL,
    valuation_date                  date NOT NULL,
    fmv_per_share                   numeric(14,2) NOT NULL,
    provider                        text NOT NULL,
    expires_on                      date NOT NULL,
    trigger_event                   text,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.valuation_409a.id IS 'class=S';
COMMENT ON COLUMN public.valuation_409a.tenant_id IS 'class=S';
COMMENT ON COLUMN public.valuation_409a.legal_entity_id IS 'class=S';
COMMENT ON COLUMN public.valuation_409a.valuation_date IS 'class=S';
COMMENT ON COLUMN public.valuation_409a.fmv_per_share IS 'class=C2';
COMMENT ON COLUMN public.valuation_409a.provider IS 'class=C0';
COMMENT ON COLUMN public.valuation_409a.expires_on IS 'class=S';
COMMENT ON COLUMN public.valuation_409a.trigger_event IS 'class=C1';
COMMENT ON COLUMN public.valuation_409a.created_at IS 'class=S';
COMMENT ON COLUMN public.valuation_409a.updated_at IS 'class=S';
COMMENT ON TABLE public.valuation_409a IS 'domain=comp;source=graph';

-- review_cycle: A review period and its calibration status.
CREATE TABLE public.review_cycle (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    name                            text NOT NULL,
    opens_at                        date NOT NULL,
    closes_at                       date NOT NULL,
    calibration_status              text NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.review_cycle.id IS 'class=S';
COMMENT ON COLUMN public.review_cycle.tenant_id IS 'class=S';
COMMENT ON COLUMN public.review_cycle.name IS 'class=C0';
COMMENT ON COLUMN public.review_cycle.opens_at IS 'class=S';
COMMENT ON COLUMN public.review_cycle.closes_at IS 'class=S';
COMMENT ON COLUMN public.review_cycle.calibration_status IS 'class=S';
COMMENT ON COLUMN public.review_cycle.created_at IS 'class=S';
COMMENT ON COLUMN public.review_cycle.updated_at IS 'class=S';
COMMENT ON TABLE public.review_cycle IS 'domain=perf;source=graph';

-- performance_review: Self assessment, manager rating, and the calibrated rating that feeds merit.
CREATE TABLE public.performance_review (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    review_cycle_id                 uuid NOT NULL,
    employee_id                     uuid NOT NULL,
    reviewer_employee_id            uuid NOT NULL,
    self_assessment                 text,
    manager_rating                  numeric(14,2),
    calibrated_rating               numeric(14,2),
    submitted_at                    timestamptz,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.performance_review.id IS 'class=S';
COMMENT ON COLUMN public.performance_review.tenant_id IS 'class=S';
COMMENT ON COLUMN public.performance_review.review_cycle_id IS 'class=S';
COMMENT ON COLUMN public.performance_review.employee_id IS 'class=S';
COMMENT ON COLUMN public.performance_review.reviewer_employee_id IS 'class=S';
COMMENT ON COLUMN public.performance_review.self_assessment IS 'class=C2';
COMMENT ON COLUMN public.performance_review.manager_rating IS 'class=C2';
COMMENT ON COLUMN public.performance_review.calibrated_rating IS 'class=C2';
COMMENT ON COLUMN public.performance_review.submitted_at IS 'class=S';
COMMENT ON COLUMN public.performance_review.created_at IS 'class=S';
COMMENT ON COLUMN public.performance_review.updated_at IS 'class=S';
COMMENT ON TABLE public.performance_review IS 'domain=perf;source=graph';

-- pip: Performance plans are tracked by an agent, never initiated by one.
CREATE TABLE public.pip (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    initiated_by_user_id            uuid NOT NULL,
    plan_document_id                uuid NOT NULL,
    milestones                      jsonb NOT NULL,
    outcome                         text,
    started_at                      date NOT NULL,
    ends_at                         date NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.pip.id IS 'class=S';
COMMENT ON COLUMN public.pip.tenant_id IS 'class=S';
COMMENT ON COLUMN public.pip.employee_id IS 'class=S';
COMMENT ON COLUMN public.pip.initiated_by_user_id IS 'class=S';
COMMENT ON COLUMN public.pip.plan_document_id IS 'class=S';
COMMENT ON COLUMN public.pip.milestones IS 'class=C2';
COMMENT ON COLUMN public.pip.outcome IS 'class=C2';
COMMENT ON COLUMN public.pip.started_at IS 'class=S';
COMMENT ON COLUMN public.pip.ends_at IS 'class=S';
COMMENT ON COLUMN public.pip.created_at IS 'class=S';
COMMENT ON COLUMN public.pip.updated_at IS 'class=S';
COMMENT ON TABLE public.pip IS 'domain=perf;source=graph';

-- course: Course catalogue with jurisdiction rules (POSH in India, state harassment training in the US).
CREATE TABLE public.course (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    title                           text NOT NULL,
    jurisdiction_rule               text NOT NULL,
    is_mandatory                    boolean NOT NULL,
    validity_months                 integer,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.course.id IS 'class=S';
COMMENT ON COLUMN public.course.tenant_id IS 'class=S';
COMMENT ON COLUMN public.course.title IS 'class=C0';
COMMENT ON COLUMN public.course.jurisdiction_rule IS 'class=C0';
COMMENT ON COLUMN public.course.is_mandatory IS 'class=S';
COMMENT ON COLUMN public.course.validity_months IS 'class=C0';
COMMENT ON COLUMN public.course.created_at IS 'class=S';
COMMENT ON COLUMN public.course.updated_at IS 'class=S';
COMMENT ON TABLE public.course IS 'domain=learn;source=graph';

-- training_assignment: training_record in the 32-table ERD: assigned courses, deadlines and completion.
CREATE TABLE public.training_assignment (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    course_id                       uuid NOT NULL,
    assigned_reason                 text NOT NULL,
    due_at                          date NOT NULL,
    completed_at                    timestamptz,
    score                           numeric(14,2),
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.training_assignment.id IS 'class=S';
COMMENT ON COLUMN public.training_assignment.tenant_id IS 'class=S';
COMMENT ON COLUMN public.training_assignment.employee_id IS 'class=S';
COMMENT ON COLUMN public.training_assignment.course_id IS 'class=S';
COMMENT ON COLUMN public.training_assignment.assigned_reason IS 'class=S';
COMMENT ON COLUMN public.training_assignment.due_at IS 'class=S';
COMMENT ON COLUMN public.training_assignment.completed_at IS 'class=S';
COMMENT ON COLUMN public.training_assignment.score IS 'class=C2';
COMMENT ON COLUMN public.training_assignment.created_at IS 'class=S';
COMMENT ON COLUMN public.training_assignment.updated_at IS 'class=S';
COMMENT ON TABLE public.training_assignment IS 'domain=learn;source=gap';

-- certification: Licences and certifications with expiry; role-critical ones hard-stop.
CREATE TABLE public.certification (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    name                            text NOT NULL,
    issuer                          text NOT NULL,
    issued_on                       date NOT NULL,
    expires_on                      date,
    role_critical                   boolean NOT NULL,
    document_id                     uuid,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.certification.id IS 'class=S';
COMMENT ON COLUMN public.certification.tenant_id IS 'class=S';
COMMENT ON COLUMN public.certification.employee_id IS 'class=S';
COMMENT ON COLUMN public.certification.name IS 'class=C1';
COMMENT ON COLUMN public.certification.issuer IS 'class=C1';
COMMENT ON COLUMN public.certification.issued_on IS 'class=S';
COMMENT ON COLUMN public.certification.expires_on IS 'class=S';
COMMENT ON COLUMN public.certification.role_critical IS 'class=S';
COMMENT ON COLUMN public.certification.document_id IS 'class=S';
COMMENT ON COLUMN public.certification.created_at IS 'class=S';
COMMENT ON COLUMN public.certification.updated_at IS 'class=S';
COMMENT ON TABLE public.certification IS 'domain=learn;source=graph';

-- expense: Employee expenses checked against policy and routed by amount.
CREATE TABLE public.expense (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    amount                          numeric(14,2) NOT NULL,
    category                        text NOT NULL,
    receipt_document_id             uuid,
    policy_flags                    jsonb NOT NULL,
    approval_request_id             uuid,
    reimbursed_at                   timestamptz,
    gl_journal_entry_id             uuid,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.expense.id IS 'class=S';
COMMENT ON COLUMN public.expense.tenant_id IS 'class=S';
COMMENT ON COLUMN public.expense.employee_id IS 'class=S';
COMMENT ON COLUMN public.expense.amount IS 'class=C2';
COMMENT ON COLUMN public.expense.category IS 'class=C0';
COMMENT ON COLUMN public.expense.receipt_document_id IS 'class=S';
COMMENT ON COLUMN public.expense.policy_flags IS 'class=S';
COMMENT ON COLUMN public.expense.approval_request_id IS 'class=S';
COMMENT ON COLUMN public.expense.reimbursed_at IS 'class=S';
COMMENT ON COLUMN public.expense.gl_journal_entry_id IS 'class=S';
COMMENT ON COLUMN public.expense.created_at IS 'class=S';
COMMENT ON COLUMN public.expense.updated_at IS 'class=S';
COMMENT ON TABLE public.expense IS 'domain=fin;source=graph';

-- corporate_card: Card limits set per role.
CREATE TABLE public.corporate_card (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    last4                           text NOT NULL,
    spend_limit                     numeric(14,2) NOT NULL,
    status                          text NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.corporate_card.id IS 'class=S';
COMMENT ON COLUMN public.corporate_card.tenant_id IS 'class=S';
COMMENT ON COLUMN public.corporate_card.employee_id IS 'class=S';
COMMENT ON COLUMN public.corporate_card.last4 IS 'class=C3;masked';
COMMENT ON COLUMN public.corporate_card.spend_limit IS 'class=C2';
COMMENT ON COLUMN public.corporate_card.status IS 'class=S';
COMMENT ON COLUMN public.corporate_card.created_at IS 'class=S';
COMMENT ON COLUMN public.corporate_card.updated_at IS 'class=S';
COMMENT ON TABLE public.corporate_card IS 'domain=fin;source=graph';

-- vendor_bill: Three-way match on vendor bills, gated above materiality.
CREATE TABLE public.vendor_bill (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    legal_entity_id                 uuid NOT NULL,
    vendor_name                     text NOT NULL,
    amount                          numeric(14,2) NOT NULL,
    po_ref                          text,
    match_status                    text NOT NULL,
    approval_request_id             uuid,
    paid_at                         timestamptz,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.vendor_bill.id IS 'class=S';
COMMENT ON COLUMN public.vendor_bill.tenant_id IS 'class=S';
COMMENT ON COLUMN public.vendor_bill.legal_entity_id IS 'class=S';
COMMENT ON COLUMN public.vendor_bill.vendor_name IS 'class=C0';
COMMENT ON COLUMN public.vendor_bill.amount IS 'class=C0';
COMMENT ON COLUMN public.vendor_bill.po_ref IS 'class=C0';
COMMENT ON COLUMN public.vendor_bill.match_status IS 'class=S';
COMMENT ON COLUMN public.vendor_bill.approval_request_id IS 'class=S';
COMMENT ON COLUMN public.vendor_bill.paid_at IS 'class=S';
COMMENT ON COLUMN public.vendor_bill.created_at IS 'class=S';
COMMENT ON COLUMN public.vendor_bill.updated_at IS 'class=S';
COMMENT ON TABLE public.vendor_bill IS 'domain=fin;source=graph';

-- gl_journal_entry: Ledger postings. Payroll posts at cost-centre grain, never per employee, so finance staff never infer an individual’s pay from the GL.
CREATE TABLE public.gl_journal_entry (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    legal_entity_id                 uuid NOT NULL,
    source_table                    text NOT NULL,
    source_id                       uuid NOT NULL,
    period                          text NOT NULL,
    cost_center_code                text NOT NULL,
    debit_account                   text NOT NULL,
    credit_account                  text NOT NULL,
    amount                          numeric(14,2) NOT NULL,
    posted_at                       timestamptz,
    approval_request_id             uuid,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.gl_journal_entry.id IS 'class=S';
COMMENT ON COLUMN public.gl_journal_entry.tenant_id IS 'class=S';
COMMENT ON COLUMN public.gl_journal_entry.legal_entity_id IS 'class=S';
COMMENT ON COLUMN public.gl_journal_entry.source_table IS 'class=S';
COMMENT ON COLUMN public.gl_journal_entry.source_id IS 'class=S';
COMMENT ON COLUMN public.gl_journal_entry.period IS 'class=C0';
COMMENT ON COLUMN public.gl_journal_entry.cost_center_code IS 'class=C0';
COMMENT ON COLUMN public.gl_journal_entry.debit_account IS 'class=C0';
COMMENT ON COLUMN public.gl_journal_entry.credit_account IS 'class=C0';
COMMENT ON COLUMN public.gl_journal_entry.amount IS 'class=C1';
COMMENT ON COLUMN public.gl_journal_entry.posted_at IS 'class=S';
COMMENT ON COLUMN public.gl_journal_entry.approval_request_id IS 'class=S';
COMMENT ON COLUMN public.gl_journal_entry.created_at IS 'class=S';
COMMENT ON COLUMN public.gl_journal_entry.updated_at IS 'class=S';
COMMENT ON TABLE public.gl_journal_entry IS 'domain=fin;source=graph';

-- er_case: Complaints logged and routed by agents, never adjudicated by them. Founder sees that a case exists but not its content, since in a small company the founder may be the subject.
CREATE TABLE public.er_case (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    complainant_employee_id         uuid NOT NULL,
    subject_employee_id             uuid,
    category                        text NOT NULL,
    status                          text NOT NULL,
    intake_at                       timestamptz NOT NULL,
    assigned_investigator_user_id   uuid,
    outcome                         text,
    legal_hold_id                   uuid,
    approval_request_id             uuid,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.er_case.id IS 'class=S';
COMMENT ON COLUMN public.er_case.tenant_id IS 'class=S';
COMMENT ON COLUMN public.er_case.complainant_employee_id IS 'class=S';
COMMENT ON COLUMN public.er_case.subject_employee_id IS 'class=S';
COMMENT ON COLUMN public.er_case.category IS 'class=C4';
COMMENT ON COLUMN public.er_case.status IS 'class=S';
COMMENT ON COLUMN public.er_case.intake_at IS 'class=S';
COMMENT ON COLUMN public.er_case.assigned_investigator_user_id IS 'class=S';
COMMENT ON COLUMN public.er_case.outcome IS 'class=C4';
COMMENT ON COLUMN public.er_case.legal_hold_id IS 'class=S';
COMMENT ON COLUMN public.er_case.approval_request_id IS 'class=S';
COMMENT ON COLUMN public.er_case.created_at IS 'class=S';
COMMENT ON COLUMN public.er_case.updated_at IS 'class=S';
COMMENT ON TABLE public.er_case IS 'domain=er;source=graph';

-- er_case_note: Investigation notes, encrypted and append-only. Readable only by the assigned investigator role.
CREATE TABLE public.er_case_note (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    er_case_id                      uuid NOT NULL,
    author_user_id                  uuid NOT NULL,
    note_body                       bytea NOT NULL,
    visibility                      text NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.er_case_note.id IS 'class=S';
COMMENT ON COLUMN public.er_case_note.tenant_id IS 'class=S';
COMMENT ON COLUMN public.er_case_note.er_case_id IS 'class=S';
COMMENT ON COLUMN public.er_case_note.author_user_id IS 'class=S';
COMMENT ON COLUMN public.er_case_note.note_body IS 'class=C4;enc=pgcrypto';
COMMENT ON COLUMN public.er_case_note.visibility IS 'class=S';
COMMENT ON COLUMN public.er_case_note.created_at IS 'class=S';
COMMENT ON TABLE public.er_case_note IS 'domain=er;source=new';

-- termination: The exit event every downstream domain reacts to (IT deprovisioning, final pay, COBRA, equity).
CREATE TABLE public.termination (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    termination_type                text NOT NULL,
    reason_code                     text NOT NULL,
    notice_date                     date NOT NULL,
    last_working_day                date NOT NULL,
    initiated_by_user_id            uuid NOT NULL,
    rehire_eligible                 text,
    exit_interview_at               timestamptz,
    approval_request_id             uuid,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.termination.id IS 'class=S';
COMMENT ON COLUMN public.termination.tenant_id IS 'class=S';
COMMENT ON COLUMN public.termination.employee_id IS 'class=S';
COMMENT ON COLUMN public.termination.termination_type IS 'class=C2';
COMMENT ON COLUMN public.termination.reason_code IS 'class=C2';
COMMENT ON COLUMN public.termination.notice_date IS 'class=C1';
COMMENT ON COLUMN public.termination.last_working_day IS 'class=C1';
COMMENT ON COLUMN public.termination.initiated_by_user_id IS 'class=S';
COMMENT ON COLUMN public.termination.rehire_eligible IS 'class=C2';
COMMENT ON COLUMN public.termination.exit_interview_at IS 'class=C1';
COMMENT ON COLUMN public.termination.approval_request_id IS 'class=S';
COMMENT ON COLUMN public.termination.created_at IS 'class=S';
COMMENT ON COLUMN public.termination.updated_at IS 'class=S';
COMMENT ON TABLE public.termination IS 'domain=er;source=graph';

-- final_settlement: Full and final: pending wages, gratuity from the running balance, encashment and recoveries, released through the same disbursal worker as payroll.
CREATE TABLE public.final_settlement (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid DEFAULT app.tenant_id() NOT NULL,
    employee_id                     uuid NOT NULL,
    termination_id                  uuid NOT NULL,
    pending_wages                   numeric(14,2) NOT NULL,
    gratuity_payout                 numeric(14,2) NOT NULL,
    leave_encashment                numeric(14,2) NOT NULL,
    recoveries                      numeric(14,2) NOT NULL,
    total_settlement                numeric(14,2) NOT NULL,
    approval_request_id             uuid NOT NULL,
    disbursed_at                    timestamptz,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN public.final_settlement.id IS 'class=S';
COMMENT ON COLUMN public.final_settlement.tenant_id IS 'class=S';
COMMENT ON COLUMN public.final_settlement.employee_id IS 'class=S';
COMMENT ON COLUMN public.final_settlement.termination_id IS 'class=S';
COMMENT ON COLUMN public.final_settlement.pending_wages IS 'class=C2';
COMMENT ON COLUMN public.final_settlement.gratuity_payout IS 'class=C2;pack=IN';
COMMENT ON COLUMN public.final_settlement.leave_encashment IS 'class=C2';
COMMENT ON COLUMN public.final_settlement.recoveries IS 'class=C2';
COMMENT ON COLUMN public.final_settlement.total_settlement IS 'class=C2;derived';
COMMENT ON COLUMN public.final_settlement.approval_request_id IS 'class=S';
COMMENT ON COLUMN public.final_settlement.disbursed_at IS 'class=S';
COMMENT ON COLUMN public.final_settlement.created_at IS 'class=S';
COMMENT ON COLUMN public.final_settlement.updated_at IS 'class=S';
COMMENT ON TABLE public.final_settlement IS 'domain=er;source=doc';

-- Foreign keys (second pass; the model has cycles)
ALTER TABLE public.tenant ADD CONSTRAINT tenant_founder_user_id_fkey FOREIGN KEY (founder_user_id) REFERENCES public.app_user(id);
ALTER TABLE public.legal_entity ADD CONSTRAINT legal_entity_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.department ADD CONSTRAINT department_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.department ADD CONSTRAINT department_parent_department_id_fkey FOREIGN KEY (parent_department_id) REFERENCES public.department(id);
ALTER TABLE public.department ADD CONSTRAINT department_head_employee_id_fkey FOREIGN KEY (head_employee_id) REFERENCES public.employee(id);
ALTER TABLE public.location ADD CONSTRAINT location_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.location ADD CONSTRAINT location_legal_entity_id_fkey FOREIGN KEY (legal_entity_id) REFERENCES public.legal_entity(id);
ALTER TABLE public.app_user ADD CONSTRAINT app_user_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.app_user ADD CONSTRAINT app_user_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.role_assignment ADD CONSTRAINT role_assignment_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.role_assignment ADD CONSTRAINT role_assignment_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.app_user(id);
ALTER TABLE public.role_assignment ADD CONSTRAINT role_assignment_granted_by_user_id_fkey FOREIGN KEY (granted_by_user_id) REFERENCES public.app_user(id);
ALTER TABLE public.tenant_compliance_config ADD CONSTRAINT tenant_compliance_config_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.approval_request ADD CONSTRAINT approval_request_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.approval_request ADD CONSTRAINT approval_request_resolved_by_user_id_fkey FOREIGN KEY (resolved_by_user_id) REFERENCES public.app_user(id);
ALTER TABLE public.approval_request ADD CONSTRAINT approval_request_requested_by_user_id_fkey FOREIGN KEY (requested_by_user_id) REFERENCES public.app_user(id);
ALTER TABLE public.approval_request ADD CONSTRAINT approval_request_requested_by_agent_run_id_fkey FOREIGN KEY (requested_by_agent_run_id) REFERENCES public.agent_task_run(id);
ALTER TABLE public.agent_task_run ADD CONSTRAINT agent_task_run_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.agent_task_run ADD CONSTRAINT agent_task_run_approval_request_id_fkey FOREIGN KEY (approval_request_id) REFERENCES public.approval_request(id);
ALTER TABLE public.document ADD CONSTRAINT document_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.document ADD CONSTRAINT document_retention_class_fkey FOREIGN KEY (retention_class) REFERENCES public.retention_policy(id);
ALTER TABLE public.document ADD CONSTRAINT document_consent_record_id_fkey FOREIGN KEY (consent_record_id) REFERENCES public.consent_record(id);
ALTER TABLE public.consent_record ADD CONSTRAINT consent_record_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.consent_record ADD CONSTRAINT consent_record_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.data_subject_request ADD CONSTRAINT data_subject_request_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.data_subject_request ADD CONSTRAINT data_subject_request_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.audit_log ADD CONSTRAINT audit_log_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.audit_log ADD CONSTRAINT audit_log_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.app_user(id);
ALTER TABLE public.audit_log ADD CONSTRAINT audit_log_agent_task_run_id_fkey FOREIGN KEY (agent_task_run_id) REFERENCES public.agent_task_run(id);
ALTER TABLE public.legal_hold ADD CONSTRAINT legal_hold_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.legal_hold ADD CONSTRAINT legal_hold_placed_by_user_id_fkey FOREIGN KEY (placed_by_user_id) REFERENCES public.app_user(id);
ALTER TABLE public.employee ADD CONSTRAINT employee_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.employee ADD CONSTRAINT employee_legal_entity_id_fkey FOREIGN KEY (legal_entity_id) REFERENCES public.legal_entity(id);
ALTER TABLE public.employee ADD CONSTRAINT employee_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.department(id);
ALTER TABLE public.employee ADD CONSTRAINT employee_location_id_fkey FOREIGN KEY (location_id) REFERENCES public.location(id);
ALTER TABLE public.employee ADD CONSTRAINT employee_position_id_fkey FOREIGN KEY (position_id) REFERENCES public.position(id);
ALTER TABLE public.employment_record ADD CONSTRAINT employment_record_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.employment_record ADD CONSTRAINT employment_record_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.employment_record ADD CONSTRAINT employment_record_job_profile_id_fkey FOREIGN KEY (job_profile_id) REFERENCES public.job_profile(id);
ALTER TABLE public.employment_record ADD CONSTRAINT employment_record_comp_band_id_fkey FOREIGN KEY (comp_band_id) REFERENCES public.comp_band(id);
ALTER TABLE public.position ADD CONSTRAINT position_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.position ADD CONSTRAINT position_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.department(id);
ALTER TABLE public.position ADD CONSTRAINT position_job_profile_id_fkey FOREIGN KEY (job_profile_id) REFERENCES public.job_profile(id);
ALTER TABLE public.position ADD CONSTRAINT position_current_employee_id_fkey FOREIGN KEY (current_employee_id) REFERENCES public.employee(id);
ALTER TABLE public.job_profile ADD CONSTRAINT job_profile_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.comp_band ADD CONSTRAINT comp_band_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.comp_band ADD CONSTRAINT comp_band_job_profile_id_fkey FOREIGN KEY (job_profile_id) REFERENCES public.job_profile(id);
ALTER TABLE public.comp_band ADD CONSTRAINT comp_band_location_id_fkey FOREIGN KEY (location_id) REFERENCES public.location(id);
ALTER TABLE public.reporting_line ADD CONSTRAINT reporting_line_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.reporting_line ADD CONSTRAINT reporting_line_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.reporting_line ADD CONSTRAINT reporting_line_manager_employee_id_fkey FOREIGN KEY (manager_employee_id) REFERENCES public.employee(id);
ALTER TABLE public.emergency_contact ADD CONSTRAINT emergency_contact_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.emergency_contact ADD CONSTRAINT emergency_contact_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.work_authorization ADD CONSTRAINT work_authorization_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.work_authorization ADD CONSTRAINT work_authorization_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.self_identification ADD CONSTRAINT self_identification_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.self_identification ADD CONSTRAINT self_identification_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.threshold_obligation ADD CONSTRAINT threshold_obligation_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.threshold_obligation ADD CONSTRAINT threshold_obligation_legal_entity_id_fkey FOREIGN KEY (legal_entity_id) REFERENCES public.legal_entity(id);
ALTER TABLE public.threshold_obligation ADD CONSTRAINT threshold_obligation_approval_request_id_fkey FOREIGN KEY (approval_request_id) REFERENCES public.approval_request(id);
ALTER TABLE public.skill ADD CONSTRAINT skill_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.employee_skill ADD CONSTRAINT employee_skill_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.employee_skill ADD CONSTRAINT employee_skill_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.employee_skill ADD CONSTRAINT employee_skill_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skill(id);
ALTER TABLE public.job_requisition ADD CONSTRAINT job_requisition_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.job_requisition ADD CONSTRAINT job_requisition_position_id_fkey FOREIGN KEY (position_id) REFERENCES public.position(id);
ALTER TABLE public.job_requisition ADD CONSTRAINT job_requisition_hiring_manager_id_fkey FOREIGN KEY (hiring_manager_id) REFERENCES public.employee(id);
ALTER TABLE public.job_requisition ADD CONSTRAINT job_requisition_approval_request_id_fkey FOREIGN KEY (approval_request_id) REFERENCES public.approval_request(id);
ALTER TABLE public.job_posting ADD CONSTRAINT job_posting_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.job_posting ADD CONSTRAINT job_posting_requisition_id_fkey FOREIGN KEY (requisition_id) REFERENCES public.job_requisition(id);
ALTER TABLE public.candidate ADD CONSTRAINT candidate_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.candidate ADD CONSTRAINT candidate_converted_employee_id_fkey FOREIGN KEY (converted_employee_id) REFERENCES public.employee(id);
ALTER TABLE public.application ADD CONSTRAINT application_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.application ADD CONSTRAINT application_candidate_id_fkey FOREIGN KEY (candidate_id) REFERENCES public.candidate(id);
ALTER TABLE public.application ADD CONSTRAINT application_requisition_id_fkey FOREIGN KEY (requisition_id) REFERENCES public.job_requisition(id);
ALTER TABLE public.screening_result ADD CONSTRAINT screening_result_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.screening_result ADD CONSTRAINT screening_result_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.application(id);
ALTER TABLE public.screening_result ADD CONSTRAINT screening_result_aedt_audit_id_fkey FOREIGN KEY (aedt_audit_id) REFERENCES public.aedt_audit(id);
ALTER TABLE public.screening_result ADD CONSTRAINT screening_result_human_reviewer_user_id_fkey FOREIGN KEY (human_reviewer_user_id) REFERENCES public.app_user(id);
ALTER TABLE public.aedt_audit ADD CONSTRAINT aedt_audit_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.interview ADD CONSTRAINT interview_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.interview ADD CONSTRAINT interview_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.application(id);
ALTER TABLE public.interview ADD CONSTRAINT interview_interviewer_employee_id_fkey FOREIGN KEY (interviewer_employee_id) REFERENCES public.employee(id);
ALTER TABLE public.background_check ADD CONSTRAINT background_check_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.background_check ADD CONSTRAINT background_check_candidate_id_fkey FOREIGN KEY (candidate_id) REFERENCES public.candidate(id);
ALTER TABLE public.offer ADD CONSTRAINT offer_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.offer ADD CONSTRAINT offer_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.application(id);
ALTER TABLE public.offer ADD CONSTRAINT offer_comp_band_id_fkey FOREIGN KEY (comp_band_id) REFERENCES public.comp_band(id);
ALTER TABLE public.offer ADD CONSTRAINT offer_approval_request_id_fkey FOREIGN KEY (approval_request_id) REFERENCES public.approval_request(id);
ALTER TABLE public.offer ADD CONSTRAINT offer_offer_document_id_fkey FOREIGN KEY (offer_document_id) REFERENCES public.document(id);
ALTER TABLE public.checklist ADD CONSTRAINT checklist_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.checklist ADD CONSTRAINT checklist_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.checklist_task ADD CONSTRAINT checklist_task_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.checklist_task ADD CONSTRAINT checklist_task_checklist_id_fkey FOREIGN KEY (checklist_id) REFERENCES public.checklist(id);
ALTER TABLE public.checklist_task ADD CONSTRAINT checklist_task_assignee_user_id_fkey FOREIGN KEY (assignee_user_id) REFERENCES public.app_user(id);
ALTER TABLE public.access_role_template ADD CONSTRAINT access_role_template_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.access_role_template ADD CONSTRAINT access_role_template_job_profile_id_fkey FOREIGN KEY (job_profile_id) REFERENCES public.job_profile(id);
ALTER TABLE public.access_role_template ADD CONSTRAINT access_role_template_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.department(id);
ALTER TABLE public.identity_account ADD CONSTRAINT identity_account_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.identity_account ADD CONSTRAINT identity_account_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.identity_account ADD CONSTRAINT identity_account_approval_request_id_fkey FOREIGN KEY (approval_request_id) REFERENCES public.approval_request(id);
ALTER TABLE public.app_access_grant ADD CONSTRAINT app_access_grant_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.app_access_grant ADD CONSTRAINT app_access_grant_identity_account_id_fkey FOREIGN KEY (identity_account_id) REFERENCES public.identity_account(id);
ALTER TABLE public.app_access_grant ADD CONSTRAINT app_access_grant_template_id_fkey FOREIGN KEY (template_id) REFERENCES public.access_role_template(id);
ALTER TABLE public.app_access_grant ADD CONSTRAINT app_access_grant_approval_request_id_fkey FOREIGN KEY (approval_request_id) REFERENCES public.approval_request(id);
ALTER TABLE public.device ADD CONSTRAINT device_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.device_assignment ADD CONSTRAINT device_assignment_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.device_assignment ADD CONSTRAINT device_assignment_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.device(id);
ALTER TABLE public.device_assignment ADD CONSTRAINT device_assignment_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.payroll_profile ADD CONSTRAINT payroll_profile_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.payroll_profile ADD CONSTRAINT payroll_profile_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.payroll_run ADD CONSTRAINT payroll_run_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.payroll_run ADD CONSTRAINT payroll_run_legal_entity_id_fkey FOREIGN KEY (legal_entity_id) REFERENCES public.legal_entity(id);
ALTER TABLE public.payroll_run ADD CONSTRAINT payroll_run_approval_request_id_fkey FOREIGN KEY (approval_request_id) REFERENCES public.approval_request(id);
ALTER TABLE public.payroll_run ADD CONSTRAINT payroll_run_retention_class_fkey FOREIGN KEY (retention_class) REFERENCES public.retention_policy(id);
ALTER TABLE public.payslip ADD CONSTRAINT payslip_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.payslip ADD CONSTRAINT payslip_payroll_run_id_fkey FOREIGN KEY (payroll_run_id) REFERENCES public.payroll_run(id);
ALTER TABLE public.payslip ADD CONSTRAINT payslip_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.payslip ADD CONSTRAINT payslip_employment_record_id_fkey FOREIGN KEY (employment_record_id) REFERENCES public.employment_record(id);
ALTER TABLE public.payslip ADD CONSTRAINT payslip_retention_class_fkey FOREIGN KEY (retention_class) REFERENCES public.retention_policy(id);
ALTER TABLE public.payslip_line ADD CONSTRAINT payslip_line_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.payslip_line ADD CONSTRAINT payslip_line_payslip_id_fkey FOREIGN KEY (payslip_id) REFERENCES public.payslip(id);
ALTER TABLE public.payslip_line ADD CONSTRAINT payslip_line_rule_id_fkey FOREIGN KEY (rule_id) REFERENCES public.statutory_rate_rule(id);
ALTER TABLE public.garnishment_order ADD CONSTRAINT garnishment_order_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.garnishment_order ADD CONSTRAINT garnishment_order_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.filing_record ADD CONSTRAINT filing_record_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.filing_record ADD CONSTRAINT filing_record_legal_entity_id_fkey FOREIGN KEY (legal_entity_id) REFERENCES public.legal_entity(id);
ALTER TABLE public.filing_record ADD CONSTRAINT filing_record_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.document(id);
ALTER TABLE public.filing_record ADD CONSTRAINT filing_record_approval_request_id_fkey FOREIGN KEY (approval_request_id) REFERENCES public.approval_request(id);
ALTER TABLE public.filing_record ADD CONSTRAINT filing_record_retention_class_fkey FOREIGN KEY (retention_class) REFERENCES public.retention_policy(id);
ALTER TABLE public.gratuity_accrual_balance ADD CONSTRAINT gratuity_accrual_balance_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.gratuity_accrual_balance ADD CONSTRAINT gratuity_accrual_balance_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.contractor_invoice ADD CONSTRAINT contractor_invoice_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.contractor_invoice ADD CONSTRAINT contractor_invoice_contractor_employee_id_fkey FOREIGN KEY (contractor_employee_id) REFERENCES public.employee(id);
ALTER TABLE public.contractor_invoice ADD CONSTRAINT contractor_invoice_legal_entity_id_fkey FOREIGN KEY (legal_entity_id) REFERENCES public.legal_entity(id);
ALTER TABLE public.contractor_invoice ADD CONSTRAINT contractor_invoice_approval_request_id_fkey FOREIGN KEY (approval_request_id) REFERENCES public.approval_request(id);
ALTER TABLE public.benefit_plan ADD CONSTRAINT benefit_plan_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.benefit_plan ADD CONSTRAINT benefit_plan_legal_entity_id_fkey FOREIGN KEY (legal_entity_id) REFERENCES public.legal_entity(id);
ALTER TABLE public.benefit_election ADD CONSTRAINT benefit_election_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.benefit_election ADD CONSTRAINT benefit_election_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.benefit_election ADD CONSTRAINT benefit_election_benefit_plan_id_fkey FOREIGN KEY (benefit_plan_id) REFERENCES public.benefit_plan(id);
ALTER TABLE public.benefit_election ADD CONSTRAINT benefit_election_life_event_id_fkey FOREIGN KEY (life_event_id) REFERENCES public.life_event(id);
ALTER TABLE public.dependent ADD CONSTRAINT dependent_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.dependent ADD CONSTRAINT dependent_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.life_event ADD CONSTRAINT life_event_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.life_event ADD CONSTRAINT life_event_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.life_event ADD CONSTRAINT life_event_evidence_document_id_fkey FOREIGN KEY (evidence_document_id) REFERENCES public.document(id);
ALTER TABLE public.cobra_event ADD CONSTRAINT cobra_event_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.cobra_event ADD CONSTRAINT cobra_event_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.cobra_event ADD CONSTRAINT cobra_event_approval_request_id_fkey FOREIGN KEY (approval_request_id) REFERENCES public.approval_request(id);
ALTER TABLE public.time_punch ADD CONSTRAINT time_punch_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.time_punch ADD CONSTRAINT time_punch_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.timecard ADD CONSTRAINT timecard_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.timecard ADD CONSTRAINT timecard_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.timecard ADD CONSTRAINT timecard_approved_by_user_id_fkey FOREIGN KEY (approved_by_user_id) REFERENCES public.app_user(id);
ALTER TABLE public.leave_policy ADD CONSTRAINT leave_policy_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.leave_policy ADD CONSTRAINT leave_policy_legal_entity_id_fkey FOREIGN KEY (legal_entity_id) REFERENCES public.legal_entity(id);
ALTER TABLE public.leave_balance ADD CONSTRAINT leave_balance_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.leave_balance ADD CONSTRAINT leave_balance_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.leave_balance ADD CONSTRAINT leave_balance_leave_policy_id_fkey FOREIGN KEY (leave_policy_id) REFERENCES public.leave_policy(id);
ALTER TABLE public.leave_request ADD CONSTRAINT leave_request_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.leave_request ADD CONSTRAINT leave_request_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.leave_request ADD CONSTRAINT leave_request_leave_policy_id_fkey FOREIGN KEY (leave_policy_id) REFERENCES public.leave_policy(id);
ALTER TABLE public.leave_request ADD CONSTRAINT leave_request_approval_request_id_fkey FOREIGN KEY (approval_request_id) REFERENCES public.approval_request(id);
ALTER TABLE public.compensation_event ADD CONSTRAINT compensation_event_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.compensation_event ADD CONSTRAINT compensation_event_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.compensation_event ADD CONSTRAINT compensation_event_comp_band_id_fkey FOREIGN KEY (comp_band_id) REFERENCES public.comp_band(id);
ALTER TABLE public.compensation_event ADD CONSTRAINT compensation_event_proposed_by_user_id_fkey FOREIGN KEY (proposed_by_user_id) REFERENCES public.app_user(id);
ALTER TABLE public.compensation_event ADD CONSTRAINT compensation_event_approval_request_id_fkey FOREIGN KEY (approval_request_id) REFERENCES public.approval_request(id);
ALTER TABLE public.compensation_event ADD CONSTRAINT compensation_event_resulting_record_id_fkey FOREIGN KEY (resulting_record_id) REFERENCES public.employment_record(id);
ALTER TABLE public.equity_grant ADD CONSTRAINT equity_grant_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.equity_grant ADD CONSTRAINT equity_grant_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.equity_grant ADD CONSTRAINT equity_grant_valuation_409a_id_fkey FOREIGN KEY (valuation_409a_id) REFERENCES public.valuation_409a(id);
ALTER TABLE public.equity_grant ADD CONSTRAINT equity_grant_approval_request_id_fkey FOREIGN KEY (approval_request_id) REFERENCES public.approval_request(id);
ALTER TABLE public.vesting_event ADD CONSTRAINT vesting_event_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.vesting_event ADD CONSTRAINT vesting_event_equity_grant_id_fkey FOREIGN KEY (equity_grant_id) REFERENCES public.equity_grant(id);
ALTER TABLE public.option_exercise ADD CONSTRAINT option_exercise_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.option_exercise ADD CONSTRAINT option_exercise_equity_grant_id_fkey FOREIGN KEY (equity_grant_id) REFERENCES public.equity_grant(id);
ALTER TABLE public.valuation_409a ADD CONSTRAINT valuation_409a_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.valuation_409a ADD CONSTRAINT valuation_409a_legal_entity_id_fkey FOREIGN KEY (legal_entity_id) REFERENCES public.legal_entity(id);
ALTER TABLE public.review_cycle ADD CONSTRAINT review_cycle_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.performance_review ADD CONSTRAINT performance_review_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.performance_review ADD CONSTRAINT performance_review_review_cycle_id_fkey FOREIGN KEY (review_cycle_id) REFERENCES public.review_cycle(id);
ALTER TABLE public.performance_review ADD CONSTRAINT performance_review_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.performance_review ADD CONSTRAINT performance_review_reviewer_employee_id_fkey FOREIGN KEY (reviewer_employee_id) REFERENCES public.employee(id);
ALTER TABLE public.pip ADD CONSTRAINT pip_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.pip ADD CONSTRAINT pip_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.pip ADD CONSTRAINT pip_initiated_by_user_id_fkey FOREIGN KEY (initiated_by_user_id) REFERENCES public.app_user(id);
ALTER TABLE public.pip ADD CONSTRAINT pip_plan_document_id_fkey FOREIGN KEY (plan_document_id) REFERENCES public.document(id);
ALTER TABLE public.course ADD CONSTRAINT course_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.training_assignment ADD CONSTRAINT training_assignment_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.training_assignment ADD CONSTRAINT training_assignment_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.training_assignment ADD CONSTRAINT training_assignment_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.course(id);
ALTER TABLE public.certification ADD CONSTRAINT certification_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.certification ADD CONSTRAINT certification_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.certification ADD CONSTRAINT certification_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.document(id);
ALTER TABLE public.expense ADD CONSTRAINT expense_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.expense ADD CONSTRAINT expense_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.expense ADD CONSTRAINT expense_receipt_document_id_fkey FOREIGN KEY (receipt_document_id) REFERENCES public.document(id);
ALTER TABLE public.expense ADD CONSTRAINT expense_approval_request_id_fkey FOREIGN KEY (approval_request_id) REFERENCES public.approval_request(id);
ALTER TABLE public.expense ADD CONSTRAINT expense_gl_journal_entry_id_fkey FOREIGN KEY (gl_journal_entry_id) REFERENCES public.gl_journal_entry(id);
ALTER TABLE public.corporate_card ADD CONSTRAINT corporate_card_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.corporate_card ADD CONSTRAINT corporate_card_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.vendor_bill ADD CONSTRAINT vendor_bill_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.vendor_bill ADD CONSTRAINT vendor_bill_legal_entity_id_fkey FOREIGN KEY (legal_entity_id) REFERENCES public.legal_entity(id);
ALTER TABLE public.vendor_bill ADD CONSTRAINT vendor_bill_approval_request_id_fkey FOREIGN KEY (approval_request_id) REFERENCES public.approval_request(id);
ALTER TABLE public.gl_journal_entry ADD CONSTRAINT gl_journal_entry_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.gl_journal_entry ADD CONSTRAINT gl_journal_entry_legal_entity_id_fkey FOREIGN KEY (legal_entity_id) REFERENCES public.legal_entity(id);
ALTER TABLE public.gl_journal_entry ADD CONSTRAINT gl_journal_entry_approval_request_id_fkey FOREIGN KEY (approval_request_id) REFERENCES public.approval_request(id);
ALTER TABLE public.er_case ADD CONSTRAINT er_case_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.er_case ADD CONSTRAINT er_case_complainant_employee_id_fkey FOREIGN KEY (complainant_employee_id) REFERENCES public.employee(id);
ALTER TABLE public.er_case ADD CONSTRAINT er_case_subject_employee_id_fkey FOREIGN KEY (subject_employee_id) REFERENCES public.employee(id);
ALTER TABLE public.er_case ADD CONSTRAINT er_case_assigned_investigator_user_id_fkey FOREIGN KEY (assigned_investigator_user_id) REFERENCES public.app_user(id);
ALTER TABLE public.er_case ADD CONSTRAINT er_case_legal_hold_id_fkey FOREIGN KEY (legal_hold_id) REFERENCES public.legal_hold(id);
ALTER TABLE public.er_case ADD CONSTRAINT er_case_approval_request_id_fkey FOREIGN KEY (approval_request_id) REFERENCES public.approval_request(id);
ALTER TABLE public.er_case_note ADD CONSTRAINT er_case_note_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.er_case_note ADD CONSTRAINT er_case_note_er_case_id_fkey FOREIGN KEY (er_case_id) REFERENCES public.er_case(id);
ALTER TABLE public.er_case_note ADD CONSTRAINT er_case_note_author_user_id_fkey FOREIGN KEY (author_user_id) REFERENCES public.app_user(id);
ALTER TABLE public.termination ADD CONSTRAINT termination_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.termination ADD CONSTRAINT termination_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.termination ADD CONSTRAINT termination_initiated_by_user_id_fkey FOREIGN KEY (initiated_by_user_id) REFERENCES public.app_user(id);
ALTER TABLE public.termination ADD CONSTRAINT termination_approval_request_id_fkey FOREIGN KEY (approval_request_id) REFERENCES public.approval_request(id);
ALTER TABLE public.final_settlement ADD CONSTRAINT final_settlement_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenant(id);
ALTER TABLE public.final_settlement ADD CONSTRAINT final_settlement_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employee(id);
ALTER TABLE public.final_settlement ADD CONSTRAINT final_settlement_termination_id_fkey FOREIGN KEY (termination_id) REFERENCES public.termination(id);
ALTER TABLE public.final_settlement ADD CONSTRAINT final_settlement_approval_request_id_fkey FOREIGN KEY (approval_request_id) REFERENCES public.approval_request(id);

-- Indexes
CREATE INDEX tenant_founder_user_id_idx ON public.tenant (founder_user_id);
CREATE INDEX legal_entity_tenant_idx ON public.legal_entity (tenant_id);
CREATE INDEX department_tenant_idx ON public.department (tenant_id);
CREATE INDEX department_parent_department_id_idx ON public.department (parent_department_id);
CREATE INDEX department_head_employee_id_idx ON public.department (head_employee_id);
CREATE INDEX location_tenant_idx ON public.location (tenant_id);
CREATE INDEX location_legal_entity_id_idx ON public.location (legal_entity_id);
CREATE INDEX app_user_tenant_employee_id_idx ON public.app_user (tenant_id, employee_id);
CREATE INDEX role_assignment_tenant_idx ON public.role_assignment (tenant_id);
CREATE INDEX role_assignment_user_id_idx ON public.role_assignment (user_id);
CREATE INDEX role_assignment_granted_by_user_id_idx ON public.role_assignment (granted_by_user_id);
CREATE INDEX tenant_compliance_config_tenant_idx ON public.tenant_compliance_config (tenant_id);
CREATE INDEX approval_request_tenant_idx ON public.approval_request (tenant_id);
CREATE INDEX approval_request_resolved_by_user_id_idx ON public.approval_request (resolved_by_user_id);
CREATE INDEX approval_request_requested_by_user_id_idx ON public.approval_request (requested_by_user_id);
CREATE INDEX approval_request_requested_by_agent_run_id_idx ON public.approval_request (requested_by_agent_run_id);
CREATE INDEX agent_task_run_tenant_idx ON public.agent_task_run (tenant_id);
CREATE INDEX agent_task_run_approval_request_id_idx ON public.agent_task_run (approval_request_id);
CREATE INDEX document_tenant_idx ON public.document (tenant_id);
CREATE INDEX document_retention_class_idx ON public.document (retention_class);
CREATE INDEX document_consent_record_id_idx ON public.document (consent_record_id);
CREATE INDEX consent_record_tenant_employee_id_idx ON public.consent_record (tenant_id, employee_id);
CREATE INDEX data_subject_request_tenant_employee_id_idx ON public.data_subject_request (tenant_id, employee_id);
CREATE INDEX audit_log_tenant_idx ON public.audit_log (tenant_id);
CREATE INDEX audit_log_actor_user_id_idx ON public.audit_log (actor_user_id);
CREATE INDEX audit_log_agent_task_run_id_idx ON public.audit_log (agent_task_run_id);
CREATE INDEX legal_hold_tenant_idx ON public.legal_hold (tenant_id);
CREATE INDEX legal_hold_placed_by_user_id_idx ON public.legal_hold (placed_by_user_id);
CREATE INDEX employee_tenant_idx ON public.employee (tenant_id);
CREATE INDEX employee_legal_entity_id_idx ON public.employee (legal_entity_id);
CREATE INDEX employee_department_id_idx ON public.employee (department_id);
CREATE INDEX employee_location_id_idx ON public.employee (location_id);
CREATE INDEX employee_position_id_idx ON public.employee (position_id);
CREATE INDEX employment_record_tenant_employee_id_idx ON public.employment_record (tenant_id, employee_id);
CREATE INDEX employment_record_job_profile_id_idx ON public.employment_record (job_profile_id);
CREATE INDEX employment_record_comp_band_id_idx ON public.employment_record (comp_band_id);
CREATE INDEX position_tenant_idx ON public.position (tenant_id);
CREATE INDEX position_department_id_idx ON public.position (department_id);
CREATE INDEX position_job_profile_id_idx ON public.position (job_profile_id);
CREATE INDEX position_current_employee_id_idx ON public.position (current_employee_id);
CREATE INDEX job_profile_tenant_idx ON public.job_profile (tenant_id);
CREATE INDEX comp_band_tenant_idx ON public.comp_band (tenant_id);
CREATE INDEX comp_band_job_profile_id_idx ON public.comp_band (job_profile_id);
CREATE INDEX comp_band_location_id_idx ON public.comp_band (location_id);
CREATE INDEX reporting_line_tenant_employee_id_idx ON public.reporting_line (tenant_id, employee_id);
CREATE INDEX reporting_line_manager_employee_id_idx ON public.reporting_line (manager_employee_id);
CREATE INDEX emergency_contact_tenant_employee_id_idx ON public.emergency_contact (tenant_id, employee_id);
CREATE INDEX work_authorization_tenant_employee_id_idx ON public.work_authorization (tenant_id, employee_id);
CREATE INDEX self_identification_tenant_employee_id_idx ON public.self_identification (tenant_id, employee_id);
CREATE INDEX threshold_obligation_tenant_idx ON public.threshold_obligation (tenant_id);
CREATE INDEX threshold_obligation_legal_entity_id_idx ON public.threshold_obligation (legal_entity_id);
CREATE INDEX threshold_obligation_approval_request_id_idx ON public.threshold_obligation (approval_request_id);
CREATE INDEX skill_tenant_idx ON public.skill (tenant_id);
CREATE INDEX employee_skill_tenant_employee_id_idx ON public.employee_skill (tenant_id, employee_id);
CREATE INDEX employee_skill_skill_id_idx ON public.employee_skill (skill_id);
CREATE INDEX job_requisition_tenant_hiring_manager_id_idx ON public.job_requisition (tenant_id, hiring_manager_id);
CREATE INDEX job_requisition_position_id_idx ON public.job_requisition (position_id);
CREATE INDEX job_requisition_approval_request_id_idx ON public.job_requisition (approval_request_id);
CREATE INDEX job_posting_tenant_idx ON public.job_posting (tenant_id);
CREATE INDEX job_posting_requisition_id_idx ON public.job_posting (requisition_id);
CREATE INDEX candidate_tenant_converted_employee_id_idx ON public.candidate (tenant_id, converted_employee_id);
CREATE INDEX application_tenant_idx ON public.application (tenant_id);
CREATE INDEX application_candidate_id_idx ON public.application (candidate_id);
CREATE INDEX application_requisition_id_idx ON public.application (requisition_id);
CREATE INDEX screening_result_tenant_idx ON public.screening_result (tenant_id);
CREATE INDEX screening_result_application_id_idx ON public.screening_result (application_id);
CREATE INDEX screening_result_aedt_audit_id_idx ON public.screening_result (aedt_audit_id);
CREATE INDEX screening_result_human_reviewer_user_id_idx ON public.screening_result (human_reviewer_user_id);
CREATE INDEX aedt_audit_tenant_idx ON public.aedt_audit (tenant_id);
CREATE INDEX interview_tenant_interviewer_employee_id_idx ON public.interview (tenant_id, interviewer_employee_id);
CREATE INDEX interview_application_id_idx ON public.interview (application_id);
CREATE INDEX background_check_tenant_idx ON public.background_check (tenant_id);
CREATE INDEX background_check_candidate_id_idx ON public.background_check (candidate_id);
CREATE INDEX offer_tenant_idx ON public.offer (tenant_id);
CREATE INDEX offer_application_id_idx ON public.offer (application_id);
CREATE INDEX offer_comp_band_id_idx ON public.offer (comp_band_id);
CREATE INDEX offer_approval_request_id_idx ON public.offer (approval_request_id);
CREATE INDEX offer_offer_document_id_idx ON public.offer (offer_document_id);
CREATE INDEX checklist_tenant_employee_id_idx ON public.checklist (tenant_id, employee_id);
CREATE INDEX checklist_task_tenant_idx ON public.checklist_task (tenant_id);
CREATE INDEX checklist_task_checklist_id_idx ON public.checklist_task (checklist_id);
CREATE INDEX checklist_task_assignee_user_id_idx ON public.checklist_task (assignee_user_id);
CREATE INDEX access_role_template_tenant_idx ON public.access_role_template (tenant_id);
CREATE INDEX access_role_template_job_profile_id_idx ON public.access_role_template (job_profile_id);
CREATE INDEX access_role_template_department_id_idx ON public.access_role_template (department_id);
CREATE INDEX identity_account_tenant_employee_id_idx ON public.identity_account (tenant_id, employee_id);
CREATE INDEX identity_account_approval_request_id_idx ON public.identity_account (approval_request_id);
CREATE INDEX app_access_grant_tenant_idx ON public.app_access_grant (tenant_id);
CREATE INDEX app_access_grant_identity_account_id_idx ON public.app_access_grant (identity_account_id);
CREATE INDEX app_access_grant_template_id_idx ON public.app_access_grant (template_id);
CREATE INDEX app_access_grant_approval_request_id_idx ON public.app_access_grant (approval_request_id);
CREATE INDEX device_tenant_idx ON public.device (tenant_id);
CREATE INDEX device_assignment_tenant_employee_id_idx ON public.device_assignment (tenant_id, employee_id);
CREATE INDEX device_assignment_device_id_idx ON public.device_assignment (device_id);
CREATE INDEX payroll_profile_tenant_employee_id_idx ON public.payroll_profile (tenant_id, employee_id);
CREATE INDEX payroll_run_tenant_idx ON public.payroll_run (tenant_id);
CREATE INDEX payroll_run_legal_entity_id_idx ON public.payroll_run (legal_entity_id);
CREATE INDEX payroll_run_approval_request_id_idx ON public.payroll_run (approval_request_id);
CREATE INDEX payroll_run_retention_class_idx ON public.payroll_run (retention_class);
CREATE INDEX payslip_tenant_employee_id_idx ON public.payslip (tenant_id, employee_id);
CREATE INDEX payslip_payroll_run_id_idx ON public.payslip (payroll_run_id);
CREATE INDEX payslip_employment_record_id_idx ON public.payslip (employment_record_id);
CREATE INDEX payslip_retention_class_idx ON public.payslip (retention_class);
CREATE INDEX payslip_line_tenant_idx ON public.payslip_line (tenant_id);
CREATE INDEX payslip_line_payslip_id_idx ON public.payslip_line (payslip_id);
CREATE INDEX payslip_line_rule_id_idx ON public.payslip_line (rule_id);
CREATE INDEX garnishment_order_tenant_employee_id_idx ON public.garnishment_order (tenant_id, employee_id);
CREATE INDEX filing_record_tenant_idx ON public.filing_record (tenant_id);
CREATE INDEX filing_record_legal_entity_id_idx ON public.filing_record (legal_entity_id);
CREATE INDEX filing_record_document_id_idx ON public.filing_record (document_id);
CREATE INDEX filing_record_approval_request_id_idx ON public.filing_record (approval_request_id);
CREATE INDEX filing_record_retention_class_idx ON public.filing_record (retention_class);
CREATE INDEX gratuity_accrual_balance_tenant_employee_id_idx ON public.gratuity_accrual_balance (tenant_id, employee_id);
CREATE INDEX contractor_invoice_tenant_contractor_employee_id_idx ON public.contractor_invoice (tenant_id, contractor_employee_id);
CREATE INDEX contractor_invoice_legal_entity_id_idx ON public.contractor_invoice (legal_entity_id);
CREATE INDEX contractor_invoice_approval_request_id_idx ON public.contractor_invoice (approval_request_id);
CREATE INDEX benefit_plan_tenant_idx ON public.benefit_plan (tenant_id);
CREATE INDEX benefit_plan_legal_entity_id_idx ON public.benefit_plan (legal_entity_id);
CREATE INDEX benefit_election_tenant_employee_id_idx ON public.benefit_election (tenant_id, employee_id);
CREATE INDEX benefit_election_benefit_plan_id_idx ON public.benefit_election (benefit_plan_id);
CREATE INDEX benefit_election_life_event_id_idx ON public.benefit_election (life_event_id);
CREATE INDEX dependent_tenant_employee_id_idx ON public.dependent (tenant_id, employee_id);
CREATE INDEX life_event_tenant_employee_id_idx ON public.life_event (tenant_id, employee_id);
CREATE INDEX life_event_evidence_document_id_idx ON public.life_event (evidence_document_id);
CREATE INDEX cobra_event_tenant_employee_id_idx ON public.cobra_event (tenant_id, employee_id);
CREATE INDEX cobra_event_approval_request_id_idx ON public.cobra_event (approval_request_id);
CREATE INDEX time_punch_tenant_employee_id_idx ON public.time_punch (tenant_id, employee_id);
CREATE INDEX timecard_tenant_employee_id_idx ON public.timecard (tenant_id, employee_id);
CREATE INDEX timecard_approved_by_user_id_idx ON public.timecard (approved_by_user_id);
CREATE INDEX leave_policy_tenant_idx ON public.leave_policy (tenant_id);
CREATE INDEX leave_policy_legal_entity_id_idx ON public.leave_policy (legal_entity_id);
CREATE INDEX leave_balance_tenant_employee_id_idx ON public.leave_balance (tenant_id, employee_id);
CREATE INDEX leave_balance_leave_policy_id_idx ON public.leave_balance (leave_policy_id);
CREATE INDEX leave_request_tenant_employee_id_idx ON public.leave_request (tenant_id, employee_id);
CREATE INDEX leave_request_leave_policy_id_idx ON public.leave_request (leave_policy_id);
CREATE INDEX leave_request_approval_request_id_idx ON public.leave_request (approval_request_id);
CREATE INDEX compensation_event_tenant_employee_id_idx ON public.compensation_event (tenant_id, employee_id);
CREATE INDEX compensation_event_comp_band_id_idx ON public.compensation_event (comp_band_id);
CREATE INDEX compensation_event_proposed_by_user_id_idx ON public.compensation_event (proposed_by_user_id);
CREATE INDEX compensation_event_approval_request_id_idx ON public.compensation_event (approval_request_id);
CREATE INDEX compensation_event_resulting_record_id_idx ON public.compensation_event (resulting_record_id);
CREATE INDEX equity_grant_tenant_employee_id_idx ON public.equity_grant (tenant_id, employee_id);
CREATE INDEX equity_grant_valuation_409a_id_idx ON public.equity_grant (valuation_409a_id);
CREATE INDEX equity_grant_approval_request_id_idx ON public.equity_grant (approval_request_id);
CREATE INDEX vesting_event_tenant_idx ON public.vesting_event (tenant_id);
CREATE INDEX vesting_event_equity_grant_id_idx ON public.vesting_event (equity_grant_id);
CREATE INDEX option_exercise_tenant_idx ON public.option_exercise (tenant_id);
CREATE INDEX option_exercise_equity_grant_id_idx ON public.option_exercise (equity_grant_id);
CREATE INDEX valuation_409a_tenant_idx ON public.valuation_409a (tenant_id);
CREATE INDEX valuation_409a_legal_entity_id_idx ON public.valuation_409a (legal_entity_id);
CREATE INDEX review_cycle_tenant_idx ON public.review_cycle (tenant_id);
CREATE INDEX performance_review_tenant_employee_id_idx ON public.performance_review (tenant_id, employee_id);
CREATE INDEX performance_review_review_cycle_id_idx ON public.performance_review (review_cycle_id);
CREATE INDEX performance_review_reviewer_employee_id_idx ON public.performance_review (reviewer_employee_id);
CREATE INDEX pip_tenant_employee_id_idx ON public.pip (tenant_id, employee_id);
CREATE INDEX pip_initiated_by_user_id_idx ON public.pip (initiated_by_user_id);
CREATE INDEX pip_plan_document_id_idx ON public.pip (plan_document_id);
CREATE INDEX course_tenant_idx ON public.course (tenant_id);
CREATE INDEX training_assignment_tenant_employee_id_idx ON public.training_assignment (tenant_id, employee_id);
CREATE INDEX training_assignment_course_id_idx ON public.training_assignment (course_id);
CREATE INDEX certification_tenant_employee_id_idx ON public.certification (tenant_id, employee_id);
CREATE INDEX certification_document_id_idx ON public.certification (document_id);
CREATE INDEX expense_tenant_employee_id_idx ON public.expense (tenant_id, employee_id);
CREATE INDEX expense_receipt_document_id_idx ON public.expense (receipt_document_id);
CREATE INDEX expense_approval_request_id_idx ON public.expense (approval_request_id);
CREATE INDEX expense_gl_journal_entry_id_idx ON public.expense (gl_journal_entry_id);
CREATE INDEX corporate_card_tenant_employee_id_idx ON public.corporate_card (tenant_id, employee_id);
CREATE INDEX vendor_bill_tenant_idx ON public.vendor_bill (tenant_id);
CREATE INDEX vendor_bill_legal_entity_id_idx ON public.vendor_bill (legal_entity_id);
CREATE INDEX vendor_bill_approval_request_id_idx ON public.vendor_bill (approval_request_id);
CREATE INDEX gl_journal_entry_tenant_idx ON public.gl_journal_entry (tenant_id);
CREATE INDEX gl_journal_entry_legal_entity_id_idx ON public.gl_journal_entry (legal_entity_id);
CREATE INDEX gl_journal_entry_approval_request_id_idx ON public.gl_journal_entry (approval_request_id);
CREATE INDEX er_case_tenant_complainant_employee_id_idx ON public.er_case (tenant_id, complainant_employee_id);
CREATE INDEX er_case_subject_employee_id_idx ON public.er_case (subject_employee_id);
CREATE INDEX er_case_assigned_investigator_user_id_idx ON public.er_case (assigned_investigator_user_id);
CREATE INDEX er_case_legal_hold_id_idx ON public.er_case (legal_hold_id);
CREATE INDEX er_case_approval_request_id_idx ON public.er_case (approval_request_id);
CREATE INDEX er_case_note_tenant_idx ON public.er_case_note (tenant_id);
CREATE INDEX er_case_note_er_case_id_idx ON public.er_case_note (er_case_id);
CREATE INDEX er_case_note_author_user_id_idx ON public.er_case_note (author_user_id);
CREATE INDEX termination_tenant_employee_id_idx ON public.termination (tenant_id, employee_id);
CREATE INDEX termination_initiated_by_user_id_idx ON public.termination (initiated_by_user_id);
CREATE INDEX termination_approval_request_id_idx ON public.termination (approval_request_id);
CREATE INDEX final_settlement_tenant_employee_id_idx ON public.final_settlement (tenant_id, employee_id);
CREATE INDEX final_settlement_termination_id_idx ON public.final_settlement (termination_id);
CREATE INDEX final_settlement_approval_request_id_idx ON public.final_settlement (approval_request_id);

-- Triggers
CREATE TRIGGER tenant_touch BEFORE UPDATE ON public.tenant FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER legal_entity_touch BEFORE UPDATE ON public.legal_entity FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER department_touch BEFORE UPDATE ON public.department FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER location_touch BEFORE UPDATE ON public.location FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER app_user_touch BEFORE UPDATE ON public.app_user FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER role_assignment_touch BEFORE UPDATE ON public.role_assignment FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER tenant_compliance_config_touch BEFORE UPDATE ON public.tenant_compliance_config FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER approval_request_touch BEFORE UPDATE ON public.approval_request FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER agent_task_run_touch BEFORE UPDATE ON public.agent_task_run FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER document_touch BEFORE UPDATE ON public.document FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER consent_record_touch BEFORE UPDATE ON public.consent_record FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER data_subject_request_touch BEFORE UPDATE ON public.data_subject_request FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON public.audit_log FOR EACH ROW EXECUTE FUNCTION app.reject_mutation();
CREATE TRIGGER legal_hold_touch BEFORE UPDATE ON public.legal_hold FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER retention_policy_touch BEFORE UPDATE ON public.retention_policy FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER pt_slab_rule_touch BEFORE UPDATE ON public.pt_slab_rule FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER statutory_rate_rule_touch BEFORE UPDATE ON public.statutory_rate_rule FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER employee_touch BEFORE UPDATE ON public.employee FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER employment_record_touch BEFORE UPDATE ON public.employment_record FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER position_touch BEFORE UPDATE ON public.position FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER job_profile_touch BEFORE UPDATE ON public.job_profile FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER comp_band_touch BEFORE UPDATE ON public.comp_band FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER reporting_line_touch BEFORE UPDATE ON public.reporting_line FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER emergency_contact_touch BEFORE UPDATE ON public.emergency_contact FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER work_authorization_touch BEFORE UPDATE ON public.work_authorization FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER self_identification_touch BEFORE UPDATE ON public.self_identification FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER threshold_obligation_touch BEFORE UPDATE ON public.threshold_obligation FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER skill_touch BEFORE UPDATE ON public.skill FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER employee_skill_touch BEFORE UPDATE ON public.employee_skill FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER job_requisition_touch BEFORE UPDATE ON public.job_requisition FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER job_posting_touch BEFORE UPDATE ON public.job_posting FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER candidate_touch BEFORE UPDATE ON public.candidate FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER application_touch BEFORE UPDATE ON public.application FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER screening_result_touch BEFORE UPDATE ON public.screening_result FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER aedt_audit_touch BEFORE UPDATE ON public.aedt_audit FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER interview_touch BEFORE UPDATE ON public.interview FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER background_check_touch BEFORE UPDATE ON public.background_check FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER offer_touch BEFORE UPDATE ON public.offer FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER checklist_touch BEFORE UPDATE ON public.checklist FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER checklist_task_touch BEFORE UPDATE ON public.checklist_task FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER access_role_template_touch BEFORE UPDATE ON public.access_role_template FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER identity_account_touch BEFORE UPDATE ON public.identity_account FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER app_access_grant_touch BEFORE UPDATE ON public.app_access_grant FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER device_touch BEFORE UPDATE ON public.device FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER device_assignment_touch BEFORE UPDATE ON public.device_assignment FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER payroll_profile_touch BEFORE UPDATE ON public.payroll_profile FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER payroll_run_touch BEFORE UPDATE ON public.payroll_run FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER payslip_touch BEFORE UPDATE ON public.payslip FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER payslip_line_touch BEFORE UPDATE ON public.payslip_line FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER garnishment_order_touch BEFORE UPDATE ON public.garnishment_order FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER filing_record_touch BEFORE UPDATE ON public.filing_record FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER gratuity_accrual_balance_touch BEFORE UPDATE ON public.gratuity_accrual_balance FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER contractor_invoice_touch BEFORE UPDATE ON public.contractor_invoice FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER benefit_plan_touch BEFORE UPDATE ON public.benefit_plan FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER benefit_election_touch BEFORE UPDATE ON public.benefit_election FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER dependent_touch BEFORE UPDATE ON public.dependent FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER life_event_touch BEFORE UPDATE ON public.life_event FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER cobra_event_touch BEFORE UPDATE ON public.cobra_event FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER time_punch_touch BEFORE UPDATE ON public.time_punch FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER timecard_touch BEFORE UPDATE ON public.timecard FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER leave_policy_touch BEFORE UPDATE ON public.leave_policy FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER leave_balance_touch BEFORE UPDATE ON public.leave_balance FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER leave_request_touch BEFORE UPDATE ON public.leave_request FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER compensation_event_touch BEFORE UPDATE ON public.compensation_event FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER equity_grant_touch BEFORE UPDATE ON public.equity_grant FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER vesting_event_touch BEFORE UPDATE ON public.vesting_event FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER option_exercise_touch BEFORE UPDATE ON public.option_exercise FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER valuation_409a_touch BEFORE UPDATE ON public.valuation_409a FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER review_cycle_touch BEFORE UPDATE ON public.review_cycle FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER performance_review_touch BEFORE UPDATE ON public.performance_review FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER pip_touch BEFORE UPDATE ON public.pip FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER course_touch BEFORE UPDATE ON public.course FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER training_assignment_touch BEFORE UPDATE ON public.training_assignment FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER certification_touch BEFORE UPDATE ON public.certification FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER expense_touch BEFORE UPDATE ON public.expense FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER corporate_card_touch BEFORE UPDATE ON public.corporate_card FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER vendor_bill_touch BEFORE UPDATE ON public.vendor_bill FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER gl_journal_entry_touch BEFORE UPDATE ON public.gl_journal_entry FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER er_case_touch BEFORE UPDATE ON public.er_case FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER er_case_note_append_only BEFORE UPDATE OR DELETE ON public.er_case_note FOR EACH ROW EXECUTE FUNCTION app.reject_mutation();
CREATE TRIGGER termination_touch BEFORE UPDATE ON public.termination FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
CREATE TRIGGER final_settlement_touch BEFORE UPDATE ON public.final_settlement FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
