-- GENERATED from model/daydor_model.json + model/extensions.json. Do not edit by hand.
-- Row-level security, column grants and masked views.

-- tenant
ALTER TABLE public.tenant ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tenant FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_self ON public.tenant USING (id = app.tenant_id() OR app.is_daydor_staff());
GRANT SELECT (id, legal_name, cin, primary_state_code, status, founder_user_id, data_residency_region, plan_tier, created_at, updated_at) ON public.tenant TO daydor_admin;
GRANT INSERT (legal_name, cin, primary_state_code, status, founder_user_id, data_residency_region, plan_tier) ON public.tenant TO daydor_admin;
GRANT UPDATE (legal_name, cin, primary_state_code, status, founder_user_id, data_residency_region, plan_tier) ON public.tenant TO daydor_admin;
GRANT SELECT (id, legal_name, cin, primary_state_code, status, founder_user_id, data_residency_region, plan_tier, created_at, updated_at) ON public.tenant TO daydor_ops;
GRANT SELECT (id, legal_name, cin, primary_state_code, status, founder_user_id, data_residency_region, plan_tier, created_at, updated_at) ON public.tenant TO tenant_founder;
GRANT SELECT (id, legal_name, cin, primary_state_code, status, founder_user_id, data_residency_region, plan_tier, created_at, updated_at) ON public.tenant TO tenant_hr;
GRANT SELECT (id, legal_name, cin, primary_state_code, status, founder_user_id, data_residency_region, plan_tier, created_at, updated_at) ON public.tenant TO external_auditor;
GRANT SELECT (id, legal_name, cin, primary_state_code, status, founder_user_id, data_residency_region, plan_tier, created_at, updated_at) ON public.tenant TO agent_runtime;

-- legal_entity
ALTER TABLE public.legal_entity ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.legal_entity FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.legal_entity
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, name, country_code, entity_type, employer_registrations, is_eor_partner, created_at, updated_at) ON public.legal_entity TO daydor_admin;
GRANT SELECT (id, tenant_id, name, country_code, entity_type, employer_registrations, is_eor_partner, created_at, updated_at) ON public.legal_entity TO daydor_ops;
GRANT INSERT (name, country_code, entity_type, employer_registrations, is_eor_partner) ON public.legal_entity TO daydor_ops;
GRANT UPDATE (name, country_code, entity_type, employer_registrations, is_eor_partner) ON public.legal_entity TO daydor_ops;
GRANT SELECT (id, tenant_id, name, country_code, entity_type, employer_registrations, is_eor_partner, created_at, updated_at) ON public.legal_entity TO tenant_founder;
GRANT INSERT (name, country_code, entity_type, employer_registrations, is_eor_partner) ON public.legal_entity TO tenant_founder;
GRANT UPDATE (name, country_code, entity_type, employer_registrations, is_eor_partner) ON public.legal_entity TO tenant_founder;
GRANT SELECT (id, tenant_id, name, country_code, entity_type, employer_registrations, is_eor_partner, created_at, updated_at) ON public.legal_entity TO tenant_hr;
GRANT SELECT (id, tenant_id, name, country_code, entity_type, employer_registrations, is_eor_partner, created_at, updated_at) ON public.legal_entity TO tenant_payroll;
GRANT SELECT (id, tenant_id, name, country_code, entity_type, employer_registrations, is_eor_partner, created_at, updated_at) ON public.legal_entity TO external_auditor;
GRANT SELECT (id, tenant_id, name, country_code, entity_type, employer_registrations, is_eor_partner, created_at, updated_at) ON public.legal_entity TO agent_runtime;

-- department
ALTER TABLE public.department ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.department FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.department
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, name, parent_department_id, head_employee_id, cost_center_code, created_at, updated_at) ON public.department TO daydor_admin;
GRANT SELECT (id, tenant_id, name, parent_department_id, head_employee_id, cost_center_code, created_at, updated_at) ON public.department TO daydor_ops;
GRANT INSERT (name, parent_department_id, head_employee_id, cost_center_code) ON public.department TO daydor_ops;
GRANT UPDATE (name, parent_department_id, head_employee_id, cost_center_code) ON public.department TO daydor_ops;
GRANT SELECT (id, tenant_id, name, parent_department_id, head_employee_id, cost_center_code, created_at, updated_at) ON public.department TO tenant_founder;
GRANT INSERT (name, parent_department_id, head_employee_id, cost_center_code) ON public.department TO tenant_founder;
GRANT UPDATE (name, parent_department_id, head_employee_id, cost_center_code) ON public.department TO tenant_founder;
GRANT SELECT (id, tenant_id, name, parent_department_id, head_employee_id, cost_center_code, created_at, updated_at) ON public.department TO tenant_hr;
GRANT INSERT (name, parent_department_id, head_employee_id, cost_center_code) ON public.department TO tenant_hr;
GRANT UPDATE (name, parent_department_id, head_employee_id, cost_center_code) ON public.department TO tenant_hr;
GRANT SELECT (id, tenant_id, name, parent_department_id, head_employee_id, cost_center_code, created_at, updated_at) ON public.department TO tenant_payroll;
GRANT SELECT (id, tenant_id, name, parent_department_id, head_employee_id, cost_center_code, created_at, updated_at) ON public.department TO tenant_it;
GRANT SELECT (id, tenant_id, name, parent_department_id, head_employee_id, cost_center_code, created_at, updated_at) ON public.department TO tenant_manager;
GRANT SELECT (id, tenant_id, name, parent_department_id, head_employee_id, cost_center_code, created_at, updated_at) ON public.department TO tenant_employee;
GRANT SELECT (id, tenant_id, name, parent_department_id, head_employee_id, cost_center_code, created_at, updated_at) ON public.department TO external_auditor;
GRANT SELECT (id, tenant_id, name, parent_department_id, head_employee_id, cost_center_code, created_at, updated_at) ON public.department TO agent_runtime;

-- location
ALTER TABLE public.location ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.location FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.location
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, name, country_code, state_code, is_remote, legal_entity_id, created_at, updated_at) ON public.location TO daydor_admin;
GRANT SELECT (id, tenant_id, name, country_code, state_code, is_remote, legal_entity_id, created_at, updated_at) ON public.location TO daydor_ops;
GRANT INSERT (name, country_code, state_code, is_remote, legal_entity_id) ON public.location TO daydor_ops;
GRANT UPDATE (name, country_code, state_code, is_remote, legal_entity_id) ON public.location TO daydor_ops;
GRANT SELECT (id, tenant_id, name, country_code, state_code, is_remote, legal_entity_id, created_at, updated_at) ON public.location TO tenant_founder;
GRANT INSERT (name, country_code, state_code, is_remote, legal_entity_id) ON public.location TO tenant_founder;
GRANT UPDATE (name, country_code, state_code, is_remote, legal_entity_id) ON public.location TO tenant_founder;
GRANT SELECT (id, tenant_id, name, country_code, state_code, is_remote, legal_entity_id, created_at, updated_at) ON public.location TO tenant_hr;
GRANT INSERT (name, country_code, state_code, is_remote, legal_entity_id) ON public.location TO tenant_hr;
GRANT UPDATE (name, country_code, state_code, is_remote, legal_entity_id) ON public.location TO tenant_hr;
GRANT SELECT (id, tenant_id, name, country_code, state_code, is_remote, legal_entity_id, created_at, updated_at) ON public.location TO tenant_payroll;
GRANT SELECT (id, tenant_id, name, country_code, state_code, is_remote, legal_entity_id, created_at, updated_at) ON public.location TO tenant_it;
GRANT SELECT (id, tenant_id, name, country_code, state_code, is_remote, legal_entity_id, created_at, updated_at) ON public.location TO tenant_manager;
GRANT SELECT (id, tenant_id, name, country_code, state_code, is_remote, legal_entity_id, created_at, updated_at) ON public.location TO tenant_employee;
GRANT SELECT (id, tenant_id, name, country_code, state_code, is_remote, legal_entity_id, created_at, updated_at) ON public.location TO external_auditor;
GRANT SELECT (id, tenant_id, name, country_code, state_code, is_remote, legal_entity_id, created_at, updated_at) ON public.location TO agent_runtime;

-- app_user
ALTER TABLE public.app_user ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.app_user FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.app_user
    USING (tenant_id = app.tenant_id() OR (tenant_id IS NULL AND app.is_daydor_staff()))
    WITH CHECK (tenant_id = app.tenant_id() OR (tenant_id IS NULL AND app.is_daydor_staff()));
CREATE POLICY person_scope ON public.app_user AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, email, role, employee_id, is_active, mfa_enrolled, last_login_at, created_at, updated_at) ON public.app_user TO daydor_admin;
GRANT INSERT (role, employee_id, is_active, mfa_enrolled, last_login_at) ON public.app_user TO daydor_admin;
GRANT UPDATE (role, employee_id, is_active, mfa_enrolled, last_login_at) ON public.app_user TO daydor_admin;
GRANT SELECT (id, tenant_id, email, role, employee_id, is_active, mfa_enrolled, last_login_at, created_at, updated_at) ON public.app_user TO daydor_ops;
GRANT INSERT (email, role, employee_id, is_active, mfa_enrolled, last_login_at) ON public.app_user TO daydor_ops;
GRANT UPDATE (email, role, employee_id, is_active, mfa_enrolled, last_login_at) ON public.app_user TO daydor_ops;
GRANT SELECT (id, tenant_id, email, role, employee_id, is_active, mfa_enrolled, last_login_at, created_at, updated_at) ON public.app_user TO tenant_founder;
GRANT INSERT (email, role, employee_id, is_active, mfa_enrolled, last_login_at) ON public.app_user TO tenant_founder;
GRANT UPDATE (email, role, employee_id, is_active, mfa_enrolled, last_login_at) ON public.app_user TO tenant_founder;
GRANT SELECT (id, tenant_id, email, role, employee_id, is_active, mfa_enrolled, last_login_at, created_at, updated_at) ON public.app_user TO tenant_hr;
GRANT SELECT (id, tenant_id, email, role, employee_id, is_active, mfa_enrolled, last_login_at, created_at, updated_at) ON public.app_user TO tenant_it;
GRANT INSERT (role, employee_id, is_active, mfa_enrolled, last_login_at) ON public.app_user TO tenant_it;
GRANT UPDATE (role, employee_id, is_active, mfa_enrolled, last_login_at) ON public.app_user TO tenant_it;
GRANT SELECT (id, tenant_id, email, role, employee_id, is_active, mfa_enrolled, last_login_at, created_at, updated_at) ON public.app_user TO tenant_employee;
GRANT SELECT (id, tenant_id, email, role, employee_id, is_active, mfa_enrolled, last_login_at, created_at, updated_at) ON public.app_user TO external_auditor;
GRANT SELECT (id, tenant_id, email, role, employee_id, is_active, mfa_enrolled, last_login_at, created_at, updated_at) ON public.app_user TO agent_runtime;

-- role_assignment
ALTER TABLE public.role_assignment ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.role_assignment FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.role_assignment
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, user_id, role, scope_type, scope_id, granted_by_user_id, valid_from, valid_to, purpose, created_at, updated_at) ON public.role_assignment TO daydor_admin;
GRANT INSERT (user_id, role, scope_type, scope_id, granted_by_user_id, valid_from, valid_to, purpose) ON public.role_assignment TO daydor_admin;
GRANT UPDATE (user_id, role, scope_type, scope_id, granted_by_user_id, valid_from, valid_to, purpose) ON public.role_assignment TO daydor_admin;
GRANT SELECT (id, tenant_id, user_id, role, scope_type, scope_id, granted_by_user_id, valid_from, valid_to, purpose, created_at, updated_at) ON public.role_assignment TO daydor_ops;
GRANT INSERT (user_id, role, scope_type, scope_id, granted_by_user_id, valid_from, valid_to, purpose) ON public.role_assignment TO daydor_ops;
GRANT UPDATE (user_id, role, scope_type, scope_id, granted_by_user_id, valid_from, valid_to, purpose) ON public.role_assignment TO daydor_ops;
GRANT SELECT (id, tenant_id, user_id, role, scope_type, scope_id, granted_by_user_id, valid_from, valid_to, purpose, created_at, updated_at) ON public.role_assignment TO tenant_founder;
GRANT INSERT (user_id, role, scope_type, scope_id, granted_by_user_id, valid_from, valid_to, purpose) ON public.role_assignment TO tenant_founder;
GRANT UPDATE (user_id, role, scope_type, scope_id, granted_by_user_id, valid_from, valid_to, purpose) ON public.role_assignment TO tenant_founder;
GRANT SELECT (id, tenant_id, user_id, role, scope_type, scope_id, granted_by_user_id, valid_from, valid_to, purpose, created_at, updated_at) ON public.role_assignment TO tenant_hr;
GRANT SELECT (id, tenant_id, user_id, role, scope_type, scope_id, granted_by_user_id, valid_from, valid_to, purpose, created_at, updated_at) ON public.role_assignment TO tenant_it;
GRANT SELECT (id, tenant_id, user_id, role, scope_type, scope_id, granted_by_user_id, valid_from, valid_to, purpose, created_at, updated_at) ON public.role_assignment TO tenant_employee;
GRANT SELECT (id, tenant_id, user_id, role, scope_type, scope_id, granted_by_user_id, valid_from, valid_to, purpose, created_at, updated_at) ON public.role_assignment TO external_auditor;
GRANT SELECT (id, tenant_id, user_id, role, scope_type, scope_id, granted_by_user_id, valid_from, valid_to, purpose, created_at, updated_at) ON public.role_assignment TO agent_runtime;

-- tenant_compliance_config
ALTER TABLE public.tenant_compliance_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tenant_compliance_config FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.tenant_compliance_config
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, settings, manager_can_view_comp, approver_overrides, feature_flags, created_at, updated_at) ON public.tenant_compliance_config TO daydor_admin;
GRANT SELECT (id, tenant_id, settings, manager_can_view_comp, approver_overrides, feature_flags, created_at, updated_at) ON public.tenant_compliance_config TO daydor_ops;
GRANT INSERT (settings, manager_can_view_comp, approver_overrides, feature_flags) ON public.tenant_compliance_config TO daydor_ops;
GRANT UPDATE (settings, manager_can_view_comp, approver_overrides, feature_flags) ON public.tenant_compliance_config TO daydor_ops;
GRANT SELECT (id, tenant_id, settings, manager_can_view_comp, approver_overrides, feature_flags, created_at, updated_at) ON public.tenant_compliance_config TO tenant_founder;
GRANT INSERT (settings, manager_can_view_comp, approver_overrides, feature_flags) ON public.tenant_compliance_config TO tenant_founder;
GRANT UPDATE (settings, manager_can_view_comp, approver_overrides, feature_flags) ON public.tenant_compliance_config TO tenant_founder;
GRANT SELECT (id, tenant_id, settings, manager_can_view_comp, approver_overrides, feature_flags, created_at, updated_at) ON public.tenant_compliance_config TO tenant_hr;
GRANT SELECT (id, tenant_id, settings, manager_can_view_comp, approver_overrides, feature_flags, created_at, updated_at) ON public.tenant_compliance_config TO tenant_payroll;
GRANT SELECT (id, tenant_id, settings, manager_can_view_comp, approver_overrides, feature_flags, created_at, updated_at) ON public.tenant_compliance_config TO external_auditor;
GRANT SELECT (id, tenant_id, settings, manager_can_view_comp, approver_overrides, feature_flags, created_at, updated_at) ON public.tenant_compliance_config TO agent_runtime;

-- approval_request
ALTER TABLE public.approval_request ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.approval_request FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.approval_request
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, gate_type, subject_table, subject_id, required_approver_role, status, resolved_by_user_id, resolved_at, escalated_at, deadline_at, idempotency_key, requested_by_user_id, requested_by_agent_run_id, decision_note, created_at, updated_at) ON public.approval_request TO daydor_ops;
GRANT INSERT (gate_type, subject_table, subject_id, required_approver_role, status, resolved_by_user_id, resolved_at, escalated_at, deadline_at, idempotency_key, requested_by_user_id, requested_by_agent_run_id, decision_note) ON public.approval_request TO daydor_ops;
GRANT UPDATE (gate_type, subject_table, subject_id, required_approver_role, status, resolved_by_user_id, resolved_at, escalated_at, deadline_at, idempotency_key, requested_by_user_id, requested_by_agent_run_id, decision_note) ON public.approval_request TO daydor_ops;
GRANT SELECT (id, tenant_id, gate_type, subject_table, subject_id, required_approver_role, status, resolved_by_user_id, resolved_at, escalated_at, deadline_at, idempotency_key, requested_by_user_id, requested_by_agent_run_id, decision_note, created_at, updated_at) ON public.approval_request TO tenant_founder;
GRANT INSERT (gate_type, subject_table, subject_id, required_approver_role, status, resolved_by_user_id, resolved_at, escalated_at, deadline_at, idempotency_key, requested_by_user_id, requested_by_agent_run_id, decision_note) ON public.approval_request TO tenant_founder;
GRANT UPDATE (gate_type, subject_table, subject_id, required_approver_role, status, resolved_by_user_id, resolved_at, escalated_at, deadline_at, idempotency_key, requested_by_user_id, requested_by_agent_run_id, decision_note) ON public.approval_request TO tenant_founder;
GRANT SELECT (id, tenant_id, gate_type, subject_table, subject_id, required_approver_role, status, resolved_by_user_id, resolved_at, escalated_at, deadline_at, idempotency_key, requested_by_user_id, requested_by_agent_run_id, decision_note, created_at, updated_at) ON public.approval_request TO tenant_hr;
GRANT INSERT (gate_type, subject_table, subject_id, required_approver_role, status, resolved_by_user_id, resolved_at, escalated_at, deadline_at, idempotency_key, requested_by_user_id, requested_by_agent_run_id, decision_note) ON public.approval_request TO tenant_hr;
GRANT UPDATE (gate_type, subject_table, subject_id, required_approver_role, status, resolved_by_user_id, resolved_at, escalated_at, deadline_at, idempotency_key, requested_by_user_id, requested_by_agent_run_id, decision_note) ON public.approval_request TO tenant_hr;
GRANT SELECT (id, tenant_id, gate_type, subject_table, subject_id, required_approver_role, status, resolved_by_user_id, resolved_at, escalated_at, deadline_at, idempotency_key, requested_by_user_id, requested_by_agent_run_id, decision_note, created_at, updated_at) ON public.approval_request TO tenant_payroll;
GRANT INSERT (gate_type, subject_table, subject_id, required_approver_role, status, resolved_by_user_id, resolved_at, escalated_at, deadline_at, idempotency_key, requested_by_user_id, requested_by_agent_run_id, decision_note) ON public.approval_request TO tenant_payroll;
GRANT UPDATE (gate_type, subject_table, subject_id, required_approver_role, status, resolved_by_user_id, resolved_at, escalated_at, deadline_at, idempotency_key, requested_by_user_id, requested_by_agent_run_id, decision_note) ON public.approval_request TO tenant_payroll;
GRANT SELECT (id, tenant_id, gate_type, subject_table, subject_id, required_approver_role, status, resolved_by_user_id, resolved_at, escalated_at, deadline_at, idempotency_key, requested_by_user_id, requested_by_agent_run_id, decision_note, created_at, updated_at) ON public.approval_request TO tenant_it;
GRANT SELECT (id, tenant_id, gate_type, subject_table, subject_id, required_approver_role, status, resolved_by_user_id, resolved_at, escalated_at, deadline_at, idempotency_key, requested_by_user_id, requested_by_agent_run_id, decision_note, created_at, updated_at) ON public.approval_request TO tenant_manager;
GRANT SELECT (id, tenant_id, gate_type, subject_table, subject_id, required_approver_role, status, resolved_by_user_id, resolved_at, escalated_at, deadline_at, idempotency_key, requested_by_user_id, requested_by_agent_run_id, decision_note, created_at, updated_at) ON public.approval_request TO tenant_employee;
GRANT SELECT (id, tenant_id, gate_type, subject_table, subject_id, required_approver_role, status, resolved_by_user_id, resolved_at, escalated_at, deadline_at, idempotency_key, requested_by_user_id, requested_by_agent_run_id, decision_note, created_at, updated_at) ON public.approval_request TO external_auditor;
GRANT SELECT (id, tenant_id, gate_type, subject_table, subject_id, required_approver_role, status, resolved_by_user_id, resolved_at, escalated_at, deadline_at, idempotency_key, requested_by_user_id, requested_by_agent_run_id, decision_note, created_at, updated_at) ON public.approval_request TO agent_runtime;
GRANT INSERT (gate_type, subject_table, subject_id, required_approver_role, status, resolved_by_user_id, resolved_at, escalated_at, deadline_at, idempotency_key, requested_by_user_id, requested_by_agent_run_id, decision_note) ON public.approval_request TO agent_runtime;
GRANT UPDATE (gate_type, subject_table, subject_id, required_approver_role, status, resolved_by_user_id, resolved_at, escalated_at, deadline_at, idempotency_key, requested_by_user_id, requested_by_agent_run_id, decision_note) ON public.approval_request TO agent_runtime;

-- agent_task_run
ALTER TABLE public.agent_task_run ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_task_run FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.agent_task_run
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, worker_name, domain, status, idempotency_key, approval_request_id, started_at, finished_at, error_code, created_at, updated_at) ON public.agent_task_run TO daydor_admin;
GRANT SELECT (id, tenant_id, worker_name, domain, status, idempotency_key, approval_request_id, input_ref, started_at, finished_at, error_code, created_at, updated_at) ON public.agent_task_run TO daydor_ops;
GRANT SELECT (id, tenant_id, worker_name, domain, status, idempotency_key, approval_request_id, input_ref, started_at, finished_at, error_code, created_at, updated_at) ON public.agent_task_run TO external_auditor;
GRANT SELECT (id, tenant_id, worker_name, domain, status, idempotency_key, approval_request_id, input_ref, started_at, finished_at, error_code, created_at, updated_at) ON public.agent_task_run TO agent_runtime;
GRANT INSERT (worker_name, domain, status, idempotency_key, approval_request_id, input_ref, started_at, finished_at, error_code) ON public.agent_task_run TO agent_runtime;
GRANT UPDATE (worker_name, domain, status, idempotency_key, approval_request_id, input_ref, started_at, finished_at, error_code) ON public.agent_task_run TO agent_runtime;
CREATE VIEW public.agent_task_run_masked WITH (security_barrier) AS SELECT
    id,
    tenant_id,
    worker_name,
    domain,
    status,
    idempotency_key,
    approval_request_id,
    (CASE WHEN app.current_app_role() IN ('daydor_ops', 'external_auditor', 'agent_runtime') THEN input_ref WHEN app.current_app_role() IN ('tenant_founder', 'tenant_hr', 'tenant_payroll', 'tenant_it') THEN CASE WHEN input_ref IS NULL THEN NULL ELSE '****' || right(input_ref::text, 4) END ELSE NULL END)::text AS input_ref,
    started_at,
    finished_at,
    error_code,
    created_at,
    updated_at
FROM public.agent_task_run;
GRANT SELECT ON public.agent_task_run_masked TO tenant_founder, tenant_hr, tenant_payroll, tenant_it;

-- document
ALTER TABLE public.document ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.document
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, subject_type, subject_id, document_class, retention_class, consent_record_id, signed_at, created_at, updated_at) ON public.document TO daydor_ops;
GRANT INSERT (subject_type, subject_id, document_class, retention_class, consent_record_id, signed_at) ON public.document TO daydor_ops;
GRANT UPDATE (subject_type, subject_id, document_class, retention_class, consent_record_id, signed_at) ON public.document TO daydor_ops;
GRANT SELECT (id, tenant_id, subject_type, subject_id, document_class, retention_class, consent_record_id, signed_at, created_at, updated_at) ON public.document TO tenant_founder;
GRANT SELECT (id, tenant_id, subject_type, subject_id, document_class, storage_ref, retention_class, consent_record_id, signed_at, created_at, updated_at) ON public.document TO tenant_hr;
GRANT INSERT (subject_type, subject_id, document_class, storage_ref, retention_class, consent_record_id, signed_at) ON public.document TO tenant_hr;
GRANT UPDATE (subject_type, subject_id, document_class, storage_ref, retention_class, consent_record_id, signed_at) ON public.document TO tenant_hr;
GRANT SELECT (id, tenant_id, subject_type, subject_id, document_class, storage_ref, retention_class, consent_record_id, signed_at, created_at, updated_at) ON public.document TO tenant_employee;
GRANT SELECT (id, tenant_id, subject_type, subject_id, document_class, retention_class, consent_record_id, signed_at, created_at, updated_at) ON public.document TO external_auditor;
GRANT SELECT (id, tenant_id, subject_type, subject_id, document_class, storage_ref, retention_class, consent_record_id, signed_at, created_at, updated_at) ON public.document TO agent_runtime;
GRANT INSERT (subject_type, subject_id, document_class, storage_ref, retention_class, consent_record_id, signed_at) ON public.document TO agent_runtime;
GRANT UPDATE (subject_type, subject_id, document_class, storage_ref, retention_class, consent_record_id, signed_at) ON public.document TO agent_runtime;
CREATE VIEW public.document_masked WITH (security_barrier) AS SELECT
    id,
    tenant_id,
    subject_type,
    subject_id,
    document_class,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'tenant_employee', 'agent_runtime') THEN storage_ref WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_payroll', 'external_auditor') THEN CASE WHEN storage_ref IS NULL THEN NULL ELSE '****' || right(storage_ref::text, 4) END ELSE NULL END)::text AS storage_ref,
    retention_class,
    consent_record_id,
    signed_at,
    created_at,
    updated_at
FROM public.document;
GRANT SELECT ON public.document_masked TO daydor_ops, tenant_founder, tenant_payroll, external_auditor;

-- consent_record
ALTER TABLE public.consent_record ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.consent_record FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.consent_record
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.consent_record AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, data_category, purpose, status, granted_at, withdrawn_at, consent_artifact_ref, created_at, updated_at) ON public.consent_record TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, data_category, purpose, status, granted_at, withdrawn_at, consent_artifact_ref, created_at, updated_at) ON public.consent_record TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, data_category, purpose, status, granted_at, withdrawn_at, consent_artifact_ref, created_at, updated_at) ON public.consent_record TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, data_category, purpose, status, granted_at, withdrawn_at, consent_artifact_ref, created_at, updated_at) ON public.consent_record TO tenant_payroll;
GRANT SELECT (id, tenant_id, employee_id, data_category, purpose, status, granted_at, withdrawn_at, consent_artifact_ref, created_at, updated_at) ON public.consent_record TO tenant_employee;
GRANT INSERT (employee_id, data_category, purpose, status, granted_at, withdrawn_at, consent_artifact_ref) ON public.consent_record TO tenant_employee;
GRANT UPDATE (employee_id, data_category, purpose, status, granted_at, withdrawn_at, consent_artifact_ref) ON public.consent_record TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, data_category, purpose, status, granted_at, withdrawn_at, consent_artifact_ref, created_at, updated_at) ON public.consent_record TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, data_category, purpose, status, granted_at, withdrawn_at, consent_artifact_ref, created_at, updated_at) ON public.consent_record TO agent_runtime;

-- data_subject_request
ALTER TABLE public.data_subject_request ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.data_subject_request FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.data_subject_request
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.data_subject_request AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, request_type, status, received_at, due_at, resolution_notes, created_at, updated_at) ON public.data_subject_request TO daydor_ops;
GRANT INSERT (employee_id, request_type, status, received_at, resolution_notes) ON public.data_subject_request TO daydor_ops;
GRANT UPDATE (employee_id, request_type, status, received_at, resolution_notes) ON public.data_subject_request TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, request_type, status, received_at, due_at, resolution_notes, created_at, updated_at) ON public.data_subject_request TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, request_type, status, received_at, due_at, resolution_notes, created_at, updated_at) ON public.data_subject_request TO tenant_hr;
GRANT INSERT (employee_id, request_type, status, received_at, resolution_notes) ON public.data_subject_request TO tenant_hr;
GRANT UPDATE (employee_id, request_type, status, received_at, resolution_notes) ON public.data_subject_request TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, request_type, status, received_at, due_at, resolution_notes, created_at, updated_at) ON public.data_subject_request TO tenant_employee;
GRANT INSERT (employee_id, request_type, status, received_at) ON public.data_subject_request TO tenant_employee;
GRANT UPDATE (employee_id, request_type, status, received_at) ON public.data_subject_request TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, request_type, status, received_at, due_at, resolution_notes, created_at, updated_at) ON public.data_subject_request TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, request_type, status, received_at, due_at, resolution_notes, created_at, updated_at) ON public.data_subject_request TO agent_runtime;

-- audit_log
ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_log FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.audit_log
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, actor_user_id, actor_kind, agent_task_run_id, event_type, subject_table, subject_id, occurred_at, created_at) ON public.audit_log TO daydor_ops;
GRANT SELECT (id, tenant_id, actor_user_id, actor_kind, agent_task_run_id, event_type, subject_table, subject_id, occurred_at, created_at) ON public.audit_log TO tenant_founder;
GRANT SELECT (id, tenant_id, actor_user_id, actor_kind, agent_task_run_id, event_type, subject_table, subject_id, before_value, after_value, occurred_at, created_at) ON public.audit_log TO tenant_hr;
GRANT SELECT (id, tenant_id, actor_user_id, actor_kind, agent_task_run_id, event_type, subject_table, subject_id, occurred_at, created_at) ON public.audit_log TO external_auditor;
GRANT SELECT (id, tenant_id, actor_user_id, actor_kind, agent_task_run_id, event_type, subject_table, subject_id, before_value, after_value, occurred_at, created_at) ON public.audit_log TO agent_runtime;
GRANT INSERT (actor_user_id, actor_kind, agent_task_run_id, event_type, subject_table, subject_id, before_value, after_value, occurred_at) ON public.audit_log TO agent_runtime;
CREATE VIEW public.audit_log_masked WITH (security_barrier) AS SELECT
    id,
    tenant_id,
    actor_user_id,
    actor_kind,
    agent_task_run_id,
    event_type,
    subject_table,
    subject_id,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'agent_runtime') THEN before_value WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_payroll', 'external_auditor') THEN NULL ELSE NULL END)::jsonb AS before_value,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'agent_runtime') THEN after_value WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_payroll', 'external_auditor') THEN NULL ELSE NULL END)::jsonb AS after_value,
    occurred_at,
    created_at
FROM public.audit_log;
GRANT SELECT ON public.audit_log_masked TO daydor_admin, daydor_ops, tenant_founder, tenant_payroll, tenant_it, external_auditor;

-- legal_hold
ALTER TABLE public.legal_hold ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.legal_hold FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.legal_hold
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, scope_type, scope_id, placed_by_user_id, placed_at, released_at, created_at, updated_at) ON public.legal_hold TO daydor_admin;
GRANT SELECT (id, tenant_id, scope_type, scope_id, reason, placed_by_user_id, placed_at, released_at, created_at, updated_at) ON public.legal_hold TO daydor_ops;
GRANT INSERT (scope_type, scope_id, reason, placed_by_user_id, placed_at, released_at) ON public.legal_hold TO daydor_ops;
GRANT UPDATE (scope_type, scope_id, reason, placed_by_user_id, placed_at, released_at) ON public.legal_hold TO daydor_ops;
GRANT SELECT (id, tenant_id, scope_type, scope_id, reason, placed_by_user_id, placed_at, released_at, created_at, updated_at) ON public.legal_hold TO tenant_founder;
GRANT INSERT (scope_type, scope_id, reason, placed_by_user_id, placed_at, released_at) ON public.legal_hold TO tenant_founder;
GRANT UPDATE (scope_type, scope_id, reason, placed_by_user_id, placed_at, released_at) ON public.legal_hold TO tenant_founder;
GRANT SELECT (id, tenant_id, scope_type, scope_id, reason, placed_by_user_id, placed_at, released_at, created_at, updated_at) ON public.legal_hold TO tenant_hr;
GRANT INSERT (scope_type, scope_id, reason, placed_by_user_id, placed_at, released_at) ON public.legal_hold TO tenant_hr;
GRANT UPDATE (scope_type, scope_id, reason, placed_by_user_id, placed_at, released_at) ON public.legal_hold TO tenant_hr;
GRANT SELECT (id, tenant_id, scope_type, scope_id, reason, placed_by_user_id, placed_at, released_at, created_at, updated_at) ON public.legal_hold TO external_auditor;
GRANT SELECT (id, tenant_id, scope_type, scope_id, reason, placed_by_user_id, placed_at, released_at, created_at, updated_at) ON public.legal_hold TO agent_runtime;

-- retention_policy
GRANT SELECT (id, retention_class, record_type, duration_months, anchor_field, legal_basis, jurisdiction, created_at, updated_at) ON public.retention_policy TO daydor_admin;
GRANT INSERT (retention_class, record_type, duration_months, anchor_field, legal_basis, jurisdiction) ON public.retention_policy TO daydor_admin;
GRANT UPDATE (retention_class, record_type, duration_months, anchor_field, legal_basis, jurisdiction) ON public.retention_policy TO daydor_admin;
GRANT SELECT (id, retention_class, record_type, duration_months, anchor_field, legal_basis, jurisdiction, created_at, updated_at) ON public.retention_policy TO daydor_ops;
GRANT SELECT (id, retention_class, record_type, duration_months, anchor_field, legal_basis, jurisdiction, created_at, updated_at) ON public.retention_policy TO tenant_founder;
GRANT SELECT (id, retention_class, record_type, duration_months, anchor_field, legal_basis, jurisdiction, created_at, updated_at) ON public.retention_policy TO tenant_hr;
GRANT SELECT (id, retention_class, record_type, duration_months, anchor_field, legal_basis, jurisdiction, created_at, updated_at) ON public.retention_policy TO tenant_payroll;
GRANT SELECT (id, retention_class, record_type, duration_months, anchor_field, legal_basis, jurisdiction, created_at, updated_at) ON public.retention_policy TO external_auditor;
GRANT SELECT (id, retention_class, record_type, duration_months, anchor_field, legal_basis, jurisdiction, created_at, updated_at) ON public.retention_policy TO agent_runtime;

-- pt_slab_rule
GRANT SELECT (id, state_code, effective_from, effective_to, slab_min, slab_max, monthly_amount, created_at, updated_at) ON public.pt_slab_rule TO daydor_admin;
GRANT INSERT (state_code, effective_from, effective_to, slab_min, slab_max, monthly_amount) ON public.pt_slab_rule TO daydor_admin;
GRANT UPDATE (state_code, effective_from, effective_to, slab_min, slab_max, monthly_amount) ON public.pt_slab_rule TO daydor_admin;
GRANT SELECT (id, state_code, effective_from, effective_to, slab_min, slab_max, monthly_amount, created_at, updated_at) ON public.pt_slab_rule TO daydor_ops;
GRANT SELECT (id, state_code, effective_from, effective_to, slab_min, slab_max, monthly_amount, created_at, updated_at) ON public.pt_slab_rule TO tenant_founder;
GRANT SELECT (id, state_code, effective_from, effective_to, slab_min, slab_max, monthly_amount, created_at, updated_at) ON public.pt_slab_rule TO tenant_hr;
GRANT SELECT (id, state_code, effective_from, effective_to, slab_min, slab_max, monthly_amount, created_at, updated_at) ON public.pt_slab_rule TO tenant_payroll;
GRANT SELECT (id, state_code, effective_from, effective_to, slab_min, slab_max, monthly_amount, created_at, updated_at) ON public.pt_slab_rule TO tenant_employee;
GRANT SELECT (id, state_code, effective_from, effective_to, slab_min, slab_max, monthly_amount, created_at, updated_at) ON public.pt_slab_rule TO external_auditor;
GRANT SELECT (id, state_code, effective_from, effective_to, slab_min, slab_max, monthly_amount, created_at, updated_at) ON public.pt_slab_rule TO agent_runtime;

-- statutory_rate_rule
GRANT SELECT (id, scheme, jurisdiction_code, effective_from, effective_to, wage_ceiling, employee_rate, employer_rate, created_at, updated_at) ON public.statutory_rate_rule TO daydor_admin;
GRANT INSERT (scheme, jurisdiction_code, effective_from, effective_to, wage_ceiling, employee_rate, employer_rate) ON public.statutory_rate_rule TO daydor_admin;
GRANT UPDATE (scheme, jurisdiction_code, effective_from, effective_to, wage_ceiling, employee_rate, employer_rate) ON public.statutory_rate_rule TO daydor_admin;
GRANT SELECT (id, scheme, jurisdiction_code, effective_from, effective_to, wage_ceiling, employee_rate, employer_rate, created_at, updated_at) ON public.statutory_rate_rule TO daydor_ops;
GRANT SELECT (id, scheme, jurisdiction_code, effective_from, effective_to, wage_ceiling, employee_rate, employer_rate, created_at, updated_at) ON public.statutory_rate_rule TO tenant_founder;
GRANT SELECT (id, scheme, jurisdiction_code, effective_from, effective_to, wage_ceiling, employee_rate, employer_rate, created_at, updated_at) ON public.statutory_rate_rule TO tenant_hr;
GRANT SELECT (id, scheme, jurisdiction_code, effective_from, effective_to, wage_ceiling, employee_rate, employer_rate, created_at, updated_at) ON public.statutory_rate_rule TO tenant_payroll;
GRANT SELECT (id, scheme, jurisdiction_code, effective_from, effective_to, wage_ceiling, employee_rate, employer_rate, created_at, updated_at) ON public.statutory_rate_rule TO tenant_employee;
GRANT SELECT (id, scheme, jurisdiction_code, effective_from, effective_to, wage_ceiling, employee_rate, employer_rate, created_at, updated_at) ON public.statutory_rate_rule TO external_auditor;
GRANT SELECT (id, scheme, jurisdiction_code, effective_from, effective_to, wage_ceiling, employee_rate, employer_rate, created_at, updated_at) ON public.statutory_rate_rule TO agent_runtime;

-- employee
ALTER TABLE public.employee ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.employee FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.employee
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.employee AS RESTRICTIVE
    USING (app.can_see_employee(id))
    WITH CHECK (app.can_see_employee(id));
GRANT SELECT (id, tenant_id, hire_event_id, full_name, work_email, employment_type, legal_entity_id, department_id, location_id, position_id, state_code, date_of_joining, date_of_exit, is_active, created_at, updated_at) ON public.employee TO daydor_ops;
GRANT INSERT (hire_event_id, full_name, work_email, employment_type, legal_entity_id, department_id, location_id, position_id, state_code, date_of_joining, date_of_exit, is_active) ON public.employee TO daydor_ops;
GRANT UPDATE (hire_event_id, full_name, work_email, employment_type, legal_entity_id, department_id, location_id, position_id, state_code, date_of_joining, date_of_exit, is_active) ON public.employee TO daydor_ops;
GRANT SELECT (id, tenant_id, hire_event_id, full_name, work_email, employment_type, legal_entity_id, department_id, location_id, position_id, state_code, date_of_joining, date_of_exit, is_active, created_at, updated_at) ON public.employee TO tenant_founder;
GRANT INSERT (hire_event_id, full_name, work_email, employment_type, legal_entity_id, department_id, location_id, position_id, state_code, date_of_joining, date_of_exit, is_active) ON public.employee TO tenant_founder;
GRANT UPDATE (hire_event_id, full_name, work_email, employment_type, legal_entity_id, department_id, location_id, position_id, state_code, date_of_joining, date_of_exit, is_active) ON public.employee TO tenant_founder;
GRANT SELECT (id, tenant_id, hire_event_id, full_name, work_email, employment_type, legal_entity_id, department_id, location_id, position_id, state_code, date_of_joining, date_of_exit, is_active, date_of_birth, personal_address, aadhaar_last4, created_at, updated_at) ON public.employee TO tenant_hr;
GRANT INSERT (hire_event_id, full_name, work_email, employment_type, legal_entity_id, department_id, location_id, position_id, state_code, date_of_joining, date_of_exit, is_active, date_of_birth, personal_address, aadhaar_last4) ON public.employee TO tenant_hr;
GRANT UPDATE (hire_event_id, full_name, work_email, employment_type, legal_entity_id, department_id, location_id, position_id, state_code, date_of_joining, date_of_exit, is_active, date_of_birth, personal_address, aadhaar_last4) ON public.employee TO tenant_hr;
GRANT SELECT (id, tenant_id, hire_event_id, full_name, work_email, employment_type, legal_entity_id, department_id, location_id, position_id, state_code, date_of_joining, date_of_exit, is_active, created_at, updated_at) ON public.employee TO tenant_payroll;
GRANT SELECT (id, tenant_id, hire_event_id, full_name, work_email, employment_type, legal_entity_id, department_id, location_id, position_id, state_code, date_of_joining, date_of_exit, is_active, created_at, updated_at) ON public.employee TO tenant_it;
GRANT SELECT (id, tenant_id, hire_event_id, full_name, work_email, employment_type, legal_entity_id, department_id, location_id, position_id, state_code, date_of_joining, date_of_exit, is_active, created_at, updated_at) ON public.employee TO tenant_manager;
GRANT SELECT (id, tenant_id, hire_event_id, full_name, work_email, employment_type, legal_entity_id, department_id, location_id, position_id, state_code, date_of_joining, date_of_exit, is_active, date_of_birth, personal_address, aadhaar_last4, created_at, updated_at) ON public.employee TO tenant_employee;
GRANT INSERT (hire_event_id, full_name, work_email, employment_type, legal_entity_id, department_id, location_id, position_id, state_code, date_of_joining, date_of_exit, is_active, date_of_birth, personal_address, aadhaar_last4) ON public.employee TO tenant_employee;
GRANT UPDATE (hire_event_id, full_name, work_email, employment_type, legal_entity_id, department_id, location_id, position_id, state_code, date_of_joining, date_of_exit, is_active, date_of_birth, personal_address, aadhaar_last4) ON public.employee TO tenant_employee;
GRANT SELECT (id, tenant_id, hire_event_id, full_name, work_email, employment_type, legal_entity_id, department_id, location_id, position_id, state_code, date_of_joining, date_of_exit, is_active, created_at, updated_at) ON public.employee TO external_auditor;
GRANT SELECT (id, tenant_id, hire_event_id, full_name, work_email, employment_type, legal_entity_id, department_id, location_id, position_id, state_code, date_of_joining, date_of_exit, is_active, date_of_birth, personal_address, aadhaar_last4, created_at, updated_at) ON public.employee TO agent_runtime;
GRANT INSERT (hire_event_id, full_name, work_email, employment_type, legal_entity_id, department_id, location_id, position_id, state_code, date_of_joining, date_of_exit, is_active, date_of_birth, personal_address, aadhaar_last4) ON public.employee TO agent_runtime;
GRANT UPDATE (hire_event_id, full_name, work_email, employment_type, legal_entity_id, department_id, location_id, position_id, state_code, date_of_joining, date_of_exit, is_active, date_of_birth, personal_address, aadhaar_last4) ON public.employee TO agent_runtime;
CREATE VIEW public.employee_masked WITH (security_barrier) AS SELECT
    id,
    tenant_id,
    hire_event_id,
    full_name,
    work_email,
    employment_type,
    legal_entity_id,
    department_id,
    location_id,
    position_id,
    state_code,
    date_of_joining,
    date_of_exit,
    is_active,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'tenant_employee', 'agent_runtime') THEN date_of_birth WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_payroll', 'external_auditor') THEN NULL ELSE NULL END)::date AS date_of_birth,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'tenant_employee', 'agent_runtime') THEN personal_address WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_payroll', 'external_auditor') THEN CASE WHEN personal_address IS NULL THEN NULL ELSE '****' || right(personal_address::text, 4) END ELSE NULL END)::text AS personal_address,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'tenant_employee', 'agent_runtime') THEN aadhaar_last4 WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_payroll', 'external_auditor') THEN CASE WHEN aadhaar_last4 IS NULL THEN NULL ELSE '****' || right(aadhaar_last4::text, 4) END ELSE NULL END)::text AS aadhaar_last4,
    (aadhaar_ekyc_ref IS NOT NULL) AS aadhaar_ekyc_ref_on_file,
    (pan_encrypted IS NOT NULL) AS pan_encrypted_on_file,
    (ssn_encrypted IS NOT NULL) AS ssn_encrypted_on_file,
    (bank_account_encrypted IS NOT NULL) AS bank_account_encrypted_on_file,
    created_at,
    updated_at
FROM public.employee;
GRANT SELECT ON public.employee_masked TO daydor_ops, tenant_founder, tenant_payroll, external_auditor;

-- employment_record
ALTER TABLE public.employment_record ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.employment_record FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.employment_record
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.employment_record AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, effective_from, effective_to, job_profile_id, comp_band_id, fte, ctc_annual, basic_da_monthly, other_allowances_json, wage_floor_compliant, tax_regime_election, flsa_status, created_at, updated_at) ON public.employment_record TO daydor_ops;
GRANT INSERT (employee_id, effective_from, effective_to, job_profile_id, comp_band_id, fte, ctc_annual, basic_da_monthly, other_allowances_json, wage_floor_compliant, tax_regime_election, flsa_status) ON public.employment_record TO daydor_ops;
GRANT UPDATE (employee_id, effective_from, effective_to, job_profile_id, comp_band_id, fte, ctc_annual, basic_da_monthly, other_allowances_json, wage_floor_compliant, tax_regime_election, flsa_status) ON public.employment_record TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, effective_from, effective_to, job_profile_id, comp_band_id, fte, ctc_annual, basic_da_monthly, other_allowances_json, wage_floor_compliant, tax_regime_election, flsa_status, created_at, updated_at) ON public.employment_record TO tenant_founder;
GRANT INSERT (employee_id, effective_from, effective_to, job_profile_id, comp_band_id, fte, ctc_annual, basic_da_monthly, other_allowances_json, wage_floor_compliant, tax_regime_election, flsa_status) ON public.employment_record TO tenant_founder;
GRANT UPDATE (employee_id, effective_from, effective_to, job_profile_id, comp_band_id, fte, ctc_annual, basic_da_monthly, other_allowances_json, wage_floor_compliant, tax_regime_election, flsa_status) ON public.employment_record TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, effective_from, effective_to, job_profile_id, comp_band_id, fte, ctc_annual, basic_da_monthly, other_allowances_json, wage_floor_compliant, tax_regime_election, flsa_status, created_at, updated_at) ON public.employment_record TO tenant_hr;
GRANT INSERT (employee_id, effective_from, effective_to, job_profile_id, comp_band_id, fte, ctc_annual, basic_da_monthly, other_allowances_json, wage_floor_compliant, tax_regime_election, flsa_status) ON public.employment_record TO tenant_hr;
GRANT UPDATE (employee_id, effective_from, effective_to, job_profile_id, comp_band_id, fte, ctc_annual, basic_da_monthly, other_allowances_json, wage_floor_compliant, tax_regime_election, flsa_status) ON public.employment_record TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, effective_from, effective_to, job_profile_id, comp_band_id, fte, ctc_annual, basic_da_monthly, other_allowances_json, wage_floor_compliant, tax_regime_election, flsa_status, created_at, updated_at) ON public.employment_record TO tenant_payroll;
GRANT SELECT (id, tenant_id, employee_id, effective_from, effective_to, job_profile_id, comp_band_id, fte, ctc_annual, basic_da_monthly, other_allowances_json, wage_floor_compliant, tax_regime_election, flsa_status, created_at, updated_at) ON public.employment_record TO tenant_manager;
GRANT SELECT (id, tenant_id, employee_id, effective_from, effective_to, job_profile_id, comp_band_id, fte, ctc_annual, basic_da_monthly, other_allowances_json, wage_floor_compliant, tax_regime_election, flsa_status, created_at, updated_at) ON public.employment_record TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, effective_from, effective_to, job_profile_id, comp_band_id, fte, ctc_annual, basic_da_monthly, other_allowances_json, wage_floor_compliant, tax_regime_election, flsa_status, created_at, updated_at) ON public.employment_record TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, effective_from, effective_to, job_profile_id, comp_band_id, fte, ctc_annual, basic_da_monthly, other_allowances_json, wage_floor_compliant, tax_regime_election, flsa_status, created_at, updated_at) ON public.employment_record TO agent_runtime;
GRANT INSERT (employee_id, effective_from, effective_to, job_profile_id, comp_band_id, fte, ctc_annual, basic_da_monthly, other_allowances_json, wage_floor_compliant, tax_regime_election, flsa_status) ON public.employment_record TO agent_runtime;
GRANT UPDATE (employee_id, effective_from, effective_to, job_profile_id, comp_band_id, fte, ctc_annual, basic_da_monthly, other_allowances_json, wage_floor_compliant, tax_regime_election, flsa_status) ON public.employment_record TO agent_runtime;

-- position
ALTER TABLE public.position ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.position FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.position
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, department_id, job_profile_id, status, budgeted_fte, budgeted_cost, current_employee_id, opened_at, closed_at, created_at, updated_at) ON public.position TO daydor_ops;
GRANT INSERT (department_id, job_profile_id, status, budgeted_fte, budgeted_cost, current_employee_id, opened_at, closed_at) ON public.position TO daydor_ops;
GRANT UPDATE (department_id, job_profile_id, status, budgeted_fte, budgeted_cost, current_employee_id, opened_at, closed_at) ON public.position TO daydor_ops;
GRANT SELECT (id, tenant_id, department_id, job_profile_id, status, budgeted_fte, budgeted_cost, current_employee_id, opened_at, closed_at, created_at, updated_at) ON public.position TO tenant_founder;
GRANT INSERT (department_id, job_profile_id, status, budgeted_fte, budgeted_cost, current_employee_id, opened_at, closed_at) ON public.position TO tenant_founder;
GRANT UPDATE (department_id, job_profile_id, status, budgeted_fte, budgeted_cost, current_employee_id, opened_at, closed_at) ON public.position TO tenant_founder;
GRANT SELECT (id, tenant_id, department_id, job_profile_id, status, budgeted_fte, budgeted_cost, current_employee_id, opened_at, closed_at, created_at, updated_at) ON public.position TO tenant_hr;
GRANT INSERT (department_id, job_profile_id, status, budgeted_fte, budgeted_cost, current_employee_id, opened_at, closed_at) ON public.position TO tenant_hr;
GRANT UPDATE (department_id, job_profile_id, status, budgeted_fte, budgeted_cost, current_employee_id, opened_at, closed_at) ON public.position TO tenant_hr;
GRANT SELECT (id, tenant_id, department_id, job_profile_id, status, budgeted_fte, budgeted_cost, current_employee_id, opened_at, closed_at, created_at, updated_at) ON public.position TO tenant_payroll;
GRANT SELECT (id, tenant_id, department_id, job_profile_id, status, budgeted_fte, budgeted_cost, current_employee_id, opened_at, closed_at, created_at, updated_at) ON public.position TO tenant_manager;
GRANT SELECT (id, tenant_id, department_id, job_profile_id, status, budgeted_fte, budgeted_cost, current_employee_id, opened_at, closed_at, created_at, updated_at) ON public.position TO external_auditor;
GRANT SELECT (id, tenant_id, department_id, job_profile_id, status, budgeted_fte, budgeted_cost, current_employee_id, opened_at, closed_at, created_at, updated_at) ON public.position TO agent_runtime;
GRANT INSERT (department_id, job_profile_id, status, budgeted_fte, budgeted_cost, current_employee_id, opened_at, closed_at) ON public.position TO agent_runtime;
GRANT UPDATE (department_id, job_profile_id, status, budgeted_fte, budgeted_cost, current_employee_id, opened_at, closed_at) ON public.position TO agent_runtime;

-- job_profile
ALTER TABLE public.job_profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.job_profile FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.job_profile
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, title, job_family, level, flsa_default, description, created_at, updated_at) ON public.job_profile TO daydor_ops;
GRANT INSERT (title, job_family, level, flsa_default, description) ON public.job_profile TO daydor_ops;
GRANT UPDATE (title, job_family, level, flsa_default, description) ON public.job_profile TO daydor_ops;
GRANT SELECT (id, tenant_id, title, job_family, level, flsa_default, description, created_at, updated_at) ON public.job_profile TO tenant_founder;
GRANT INSERT (title, job_family, level, flsa_default, description) ON public.job_profile TO tenant_founder;
GRANT UPDATE (title, job_family, level, flsa_default, description) ON public.job_profile TO tenant_founder;
GRANT SELECT (id, tenant_id, title, job_family, level, flsa_default, description, created_at, updated_at) ON public.job_profile TO tenant_hr;
GRANT INSERT (title, job_family, level, flsa_default, description) ON public.job_profile TO tenant_hr;
GRANT UPDATE (title, job_family, level, flsa_default, description) ON public.job_profile TO tenant_hr;
GRANT SELECT (id, tenant_id, title, job_family, level, flsa_default, description, created_at, updated_at) ON public.job_profile TO tenant_payroll;
GRANT SELECT (id, tenant_id, title, job_family, level, flsa_default, description, created_at, updated_at) ON public.job_profile TO tenant_manager;
GRANT SELECT (id, tenant_id, title, job_family, level, flsa_default, description, created_at, updated_at) ON public.job_profile TO tenant_employee;
GRANT SELECT (id, tenant_id, title, job_family, level, flsa_default, description, created_at, updated_at) ON public.job_profile TO external_auditor;
GRANT SELECT (id, tenant_id, title, job_family, level, flsa_default, description, created_at, updated_at) ON public.job_profile TO agent_runtime;

-- comp_band
ALTER TABLE public.comp_band ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.comp_band FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.comp_band
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, job_profile_id, location_id, currency, band_min, band_mid, band_max, effective_from, effective_to, created_at, updated_at) ON public.comp_band TO daydor_ops;
GRANT INSERT (job_profile_id, location_id, currency, band_min, band_mid, band_max, effective_from, effective_to) ON public.comp_band TO daydor_ops;
GRANT UPDATE (job_profile_id, location_id, currency, band_min, band_mid, band_max, effective_from, effective_to) ON public.comp_band TO daydor_ops;
GRANT SELECT (id, tenant_id, job_profile_id, location_id, currency, band_min, band_mid, band_max, effective_from, effective_to, created_at, updated_at) ON public.comp_band TO tenant_founder;
GRANT INSERT (job_profile_id, location_id, currency, band_min, band_mid, band_max, effective_from, effective_to) ON public.comp_band TO tenant_founder;
GRANT UPDATE (job_profile_id, location_id, currency, band_min, band_mid, band_max, effective_from, effective_to) ON public.comp_band TO tenant_founder;
GRANT SELECT (id, tenant_id, job_profile_id, location_id, currency, band_min, band_mid, band_max, effective_from, effective_to, created_at, updated_at) ON public.comp_band TO tenant_hr;
GRANT INSERT (job_profile_id, location_id, currency, band_min, band_mid, band_max, effective_from, effective_to) ON public.comp_band TO tenant_hr;
GRANT UPDATE (job_profile_id, location_id, currency, band_min, band_mid, band_max, effective_from, effective_to) ON public.comp_band TO tenant_hr;
GRANT SELECT (id, tenant_id, job_profile_id, location_id, currency, band_min, band_mid, band_max, effective_from, effective_to, created_at, updated_at) ON public.comp_band TO tenant_payroll;
GRANT SELECT (id, tenant_id, job_profile_id, location_id, currency, band_min, band_mid, band_max, effective_from, effective_to, created_at, updated_at) ON public.comp_band TO tenant_manager;
GRANT SELECT (id, tenant_id, job_profile_id, location_id, currency, band_min, band_mid, band_max, effective_from, effective_to, created_at, updated_at) ON public.comp_band TO external_auditor;
GRANT SELECT (id, tenant_id, job_profile_id, location_id, currency, band_min, band_mid, band_max, effective_from, effective_to, created_at, updated_at) ON public.comp_band TO agent_runtime;
CREATE VIEW public.comp_band_masked WITH (security_barrier) AS SELECT
    id,
    tenant_id,
    job_profile_id,
    location_id,
    (CASE WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_hr', 'tenant_payroll', 'tenant_manager', 'external_auditor', 'agent_runtime') THEN currency WHEN app.current_app_role() IN ('tenant_employee') THEN CASE WHEN currency IS NULL THEN NULL ELSE '****' || right(currency::text, 4) END ELSE NULL END)::text AS currency,
    (CASE WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_hr', 'tenant_payroll', 'tenant_manager', 'external_auditor', 'agent_runtime') THEN band_min WHEN app.current_app_role() IN ('tenant_employee') THEN NULL ELSE NULL END)::numeric(14,2) AS band_min,
    (CASE WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_hr', 'tenant_payroll', 'tenant_manager', 'external_auditor', 'agent_runtime') THEN band_mid WHEN app.current_app_role() IN ('tenant_employee') THEN NULL ELSE NULL END)::numeric(14,2) AS band_mid,
    (CASE WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_hr', 'tenant_payroll', 'tenant_manager', 'external_auditor', 'agent_runtime') THEN band_max WHEN app.current_app_role() IN ('tenant_employee') THEN NULL ELSE NULL END)::numeric(14,2) AS band_max,
    effective_from,
    effective_to,
    created_at,
    updated_at
FROM public.comp_band;
GRANT SELECT ON public.comp_band_masked TO tenant_employee;

-- reporting_line
ALTER TABLE public.reporting_line ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reporting_line FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.reporting_line
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.reporting_line AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, manager_employee_id, relation, effective_from, effective_to, created_at, updated_at) ON public.reporting_line TO daydor_ops;
GRANT INSERT (employee_id, manager_employee_id, relation, effective_from, effective_to) ON public.reporting_line TO daydor_ops;
GRANT UPDATE (employee_id, manager_employee_id, relation, effective_from, effective_to) ON public.reporting_line TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, manager_employee_id, relation, effective_from, effective_to, created_at, updated_at) ON public.reporting_line TO tenant_founder;
GRANT INSERT (employee_id, manager_employee_id, relation, effective_from, effective_to) ON public.reporting_line TO tenant_founder;
GRANT UPDATE (employee_id, manager_employee_id, relation, effective_from, effective_to) ON public.reporting_line TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, manager_employee_id, relation, effective_from, effective_to, created_at, updated_at) ON public.reporting_line TO tenant_hr;
GRANT INSERT (employee_id, manager_employee_id, relation, effective_from, effective_to) ON public.reporting_line TO tenant_hr;
GRANT UPDATE (employee_id, manager_employee_id, relation, effective_from, effective_to) ON public.reporting_line TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, manager_employee_id, relation, effective_from, effective_to, created_at, updated_at) ON public.reporting_line TO tenant_payroll;
GRANT SELECT (id, tenant_id, employee_id, manager_employee_id, relation, effective_from, effective_to, created_at, updated_at) ON public.reporting_line TO tenant_it;
GRANT SELECT (id, tenant_id, employee_id, manager_employee_id, relation, effective_from, effective_to, created_at, updated_at) ON public.reporting_line TO tenant_manager;
GRANT SELECT (id, tenant_id, employee_id, manager_employee_id, relation, effective_from, effective_to, created_at, updated_at) ON public.reporting_line TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, manager_employee_id, relation, effective_from, effective_to, created_at, updated_at) ON public.reporting_line TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, manager_employee_id, relation, effective_from, effective_to, created_at, updated_at) ON public.reporting_line TO agent_runtime;
GRANT INSERT (employee_id, manager_employee_id, relation, effective_from, effective_to) ON public.reporting_line TO agent_runtime;
GRANT UPDATE (employee_id, manager_employee_id, relation, effective_from, effective_to) ON public.reporting_line TO agent_runtime;

-- emergency_contact
ALTER TABLE public.emergency_contact ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.emergency_contact FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.emergency_contact
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.emergency_contact AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, contact_name, relationship, phone, priority, created_at, updated_at) ON public.emergency_contact TO tenant_hr;
GRANT INSERT (employee_id, contact_name, relationship, phone, priority) ON public.emergency_contact TO tenant_hr;
GRANT UPDATE (employee_id, contact_name, relationship, phone, priority) ON public.emergency_contact TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, contact_name, relationship, phone, priority, created_at, updated_at) ON public.emergency_contact TO tenant_employee;
GRANT INSERT (employee_id, contact_name, relationship, phone, priority) ON public.emergency_contact TO tenant_employee;
GRANT UPDATE (employee_id, contact_name, relationship, phone, priority) ON public.emergency_contact TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, contact_name, relationship, phone, priority, created_at, updated_at) ON public.emergency_contact TO agent_runtime;
GRANT INSERT (employee_id, contact_name, relationship, phone, priority) ON public.emergency_contact TO agent_runtime;
GRANT UPDATE (employee_id, contact_name, relationship, phone, priority) ON public.emergency_contact TO agent_runtime;
CREATE VIEW public.emergency_contact_masked WITH (security_barrier) AS SELECT
    id,
    tenant_id,
    employee_id,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'tenant_employee', 'agent_runtime') THEN contact_name WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder') THEN CASE WHEN contact_name IS NULL THEN NULL ELSE '****' || right(contact_name::text, 4) END ELSE NULL END)::text AS contact_name,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'tenant_employee', 'agent_runtime') THEN relationship WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder') THEN CASE WHEN relationship IS NULL THEN NULL ELSE '****' || right(relationship::text, 4) END ELSE NULL END)::text AS relationship,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'tenant_employee', 'agent_runtime') THEN phone WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder') THEN CASE WHEN phone IS NULL THEN NULL ELSE '****' || right(phone::text, 4) END ELSE NULL END)::text AS phone,
    priority,
    created_at,
    updated_at
FROM public.emergency_contact;
GRANT SELECT ON public.emergency_contact_masked TO daydor_ops, tenant_founder, tenant_manager;

-- work_authorization
ALTER TABLE public.work_authorization ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.work_authorization FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.work_authorization
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.work_authorization AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, i9_section2_completed_at, everify_status, next_action_due, created_at, updated_at) ON public.work_authorization TO daydor_ops;
GRANT INSERT (employee_id, i9_section2_completed_at, everify_status, next_action_due) ON public.work_authorization TO daydor_ops;
GRANT UPDATE (employee_id, i9_section2_completed_at, everify_status, next_action_due) ON public.work_authorization TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, auth_type, status, i9_section2_completed_at, everify_case_no, everify_status, expiration_date, sponsor_flag, renewal_case_status, next_action_due, created_at, updated_at) ON public.work_authorization TO tenant_hr;
GRANT INSERT (employee_id, auth_type, status, i9_section2_completed_at, everify_case_no, everify_status, expiration_date, sponsor_flag, renewal_case_status, next_action_due) ON public.work_authorization TO tenant_hr;
GRANT UPDATE (employee_id, auth_type, status, i9_section2_completed_at, everify_case_no, everify_status, expiration_date, sponsor_flag, renewal_case_status, next_action_due) ON public.work_authorization TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, auth_type, status, i9_section2_completed_at, everify_case_no, everify_status, expiration_date, sponsor_flag, renewal_case_status, next_action_due, created_at, updated_at) ON public.work_authorization TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, i9_section2_completed_at, everify_status, next_action_due, created_at, updated_at) ON public.work_authorization TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, auth_type, status, i9_section2_completed_at, everify_case_no, everify_status, expiration_date, sponsor_flag, renewal_case_status, next_action_due, created_at, updated_at) ON public.work_authorization TO agent_runtime;
GRANT INSERT (employee_id, auth_type, status, i9_section2_completed_at, everify_case_no, everify_status, expiration_date, sponsor_flag, renewal_case_status, next_action_due) ON public.work_authorization TO agent_runtime;
GRANT UPDATE (employee_id, auth_type, status, i9_section2_completed_at, everify_case_no, everify_status, expiration_date, sponsor_flag, renewal_case_status, next_action_due) ON public.work_authorization TO agent_runtime;
CREATE VIEW public.work_authorization_masked WITH (security_barrier) AS SELECT
    id,
    tenant_id,
    employee_id,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'tenant_employee', 'agent_runtime') THEN auth_type WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_payroll', 'external_auditor') THEN NULL ELSE NULL END)::text AS auth_type,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'tenant_employee', 'agent_runtime') THEN status WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_payroll', 'external_auditor') THEN NULL ELSE NULL END)::text AS status,
    (CASE WHEN app.current_app_role() IN ('daydor_ops', 'tenant_hr', 'tenant_employee', 'external_auditor', 'agent_runtime') THEN i9_section2_completed_at WHEN app.current_app_role() IN ('tenant_founder', 'tenant_payroll') THEN NULL ELSE NULL END)::timestamptz AS i9_section2_completed_at,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'tenant_employee', 'agent_runtime') THEN everify_case_no WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_payroll', 'external_auditor') THEN CASE WHEN everify_case_no IS NULL THEN NULL ELSE '****' || right(everify_case_no::text, 4) END ELSE NULL END)::text AS everify_case_no,
    (CASE WHEN app.current_app_role() IN ('daydor_ops', 'tenant_hr', 'tenant_employee', 'external_auditor', 'agent_runtime') THEN everify_status WHEN app.current_app_role() IN ('tenant_founder', 'tenant_payroll') THEN NULL ELSE NULL END)::text AS everify_status,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'tenant_employee', 'agent_runtime') THEN expiration_date WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_payroll', 'external_auditor') THEN NULL ELSE NULL END)::date AS expiration_date,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'tenant_employee', 'agent_runtime') THEN sponsor_flag WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_payroll', 'external_auditor') THEN NULL ELSE NULL END)::boolean AS sponsor_flag,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'tenant_employee', 'agent_runtime') THEN renewal_case_status WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_payroll', 'external_auditor') THEN NULL ELSE NULL END)::text AS renewal_case_status,
    (CASE WHEN app.current_app_role() IN ('daydor_ops', 'tenant_hr', 'tenant_employee', 'external_auditor', 'agent_runtime') THEN next_action_due WHEN app.current_app_role() IN ('tenant_founder', 'tenant_payroll') THEN NULL ELSE NULL END)::date AS next_action_due,
    created_at,
    updated_at
FROM public.work_authorization;
GRANT SELECT ON public.work_authorization_masked TO daydor_ops, tenant_founder, tenant_payroll, external_auditor;

-- self_identification
ALTER TABLE public.self_identification ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.self_identification FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.self_identification
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.self_identification AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, race_ethnicity, gender, veteran_status, disability_status, collection_context, collected_at, next_reoffer_due, created_at, updated_at) ON public.self_identification TO tenant_employee;
GRANT INSERT (employee_id, race_ethnicity, gender, veteran_status, disability_status, collection_context, collected_at, next_reoffer_due) ON public.self_identification TO tenant_employee;
GRANT UPDATE (employee_id, race_ethnicity, gender, veteran_status, disability_status, collection_context, collected_at, next_reoffer_due) ON public.self_identification TO tenant_employee;

-- threshold_obligation
ALTER TABLE public.threshold_obligation ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.threshold_obligation FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.threshold_obligation
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, legal_entity_id, scheme, headcount_at_check, threshold, applicable, crossed_at, registration_deadline, approval_request_id, created_at, updated_at) ON public.threshold_obligation TO daydor_ops;
GRANT INSERT (legal_entity_id, scheme, headcount_at_check, threshold, applicable, crossed_at, registration_deadline, approval_request_id) ON public.threshold_obligation TO daydor_ops;
GRANT UPDATE (legal_entity_id, scheme, headcount_at_check, threshold, applicable, crossed_at, registration_deadline, approval_request_id) ON public.threshold_obligation TO daydor_ops;
GRANT SELECT (id, tenant_id, legal_entity_id, scheme, headcount_at_check, threshold, applicable, crossed_at, registration_deadline, approval_request_id, created_at, updated_at) ON public.threshold_obligation TO tenant_founder;
GRANT INSERT (legal_entity_id, scheme, headcount_at_check, threshold, applicable, crossed_at, registration_deadline, approval_request_id) ON public.threshold_obligation TO tenant_founder;
GRANT UPDATE (legal_entity_id, scheme, headcount_at_check, threshold, applicable, crossed_at, registration_deadline, approval_request_id) ON public.threshold_obligation TO tenant_founder;
GRANT SELECT (id, tenant_id, legal_entity_id, scheme, headcount_at_check, threshold, applicable, crossed_at, registration_deadline, approval_request_id, created_at, updated_at) ON public.threshold_obligation TO tenant_hr;
GRANT INSERT (legal_entity_id, scheme, headcount_at_check, threshold, applicable, crossed_at, registration_deadline, approval_request_id) ON public.threshold_obligation TO tenant_hr;
GRANT UPDATE (legal_entity_id, scheme, headcount_at_check, threshold, applicable, crossed_at, registration_deadline, approval_request_id) ON public.threshold_obligation TO tenant_hr;
GRANT SELECT (id, tenant_id, legal_entity_id, scheme, headcount_at_check, threshold, applicable, crossed_at, registration_deadline, approval_request_id, created_at, updated_at) ON public.threshold_obligation TO tenant_payroll;
GRANT SELECT (id, tenant_id, legal_entity_id, scheme, headcount_at_check, threshold, applicable, crossed_at, registration_deadline, approval_request_id, created_at, updated_at) ON public.threshold_obligation TO external_auditor;
GRANT SELECT (id, tenant_id, legal_entity_id, scheme, headcount_at_check, threshold, applicable, crossed_at, registration_deadline, approval_request_id, created_at, updated_at) ON public.threshold_obligation TO agent_runtime;
GRANT INSERT (legal_entity_id, scheme, headcount_at_check, threshold, applicable, crossed_at, registration_deadline, approval_request_id) ON public.threshold_obligation TO agent_runtime;
GRANT UPDATE (legal_entity_id, scheme, headcount_at_check, threshold, applicable, crossed_at, registration_deadline, approval_request_id) ON public.threshold_obligation TO agent_runtime;

-- skill
ALTER TABLE public.skill ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.skill FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.skill
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, name, category, created_at, updated_at) ON public.skill TO daydor_ops;
GRANT INSERT (name, category) ON public.skill TO daydor_ops;
GRANT UPDATE (name, category) ON public.skill TO daydor_ops;
GRANT SELECT (id, tenant_id, name, category, created_at, updated_at) ON public.skill TO tenant_founder;
GRANT INSERT (name, category) ON public.skill TO tenant_founder;
GRANT UPDATE (name, category) ON public.skill TO tenant_founder;
GRANT SELECT (id, tenant_id, name, category, created_at, updated_at) ON public.skill TO tenant_hr;
GRANT INSERT (name, category) ON public.skill TO tenant_hr;
GRANT UPDATE (name, category) ON public.skill TO tenant_hr;
GRANT SELECT (id, tenant_id, name, category, created_at, updated_at) ON public.skill TO tenant_payroll;
GRANT SELECT (id, tenant_id, name, category, created_at, updated_at) ON public.skill TO tenant_it;
GRANT SELECT (id, tenant_id, name, category, created_at, updated_at) ON public.skill TO tenant_manager;
GRANT SELECT (id, tenant_id, name, category, created_at, updated_at) ON public.skill TO tenant_employee;
GRANT SELECT (id, tenant_id, name, category, created_at, updated_at) ON public.skill TO external_auditor;
GRANT SELECT (id, tenant_id, name, category, created_at, updated_at) ON public.skill TO agent_runtime;

-- employee_skill
ALTER TABLE public.employee_skill ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.employee_skill FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.employee_skill
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.employee_skill AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, skill_id, proficiency_level, source, last_updated, created_at, updated_at) ON public.employee_skill TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, skill_id, proficiency_level, source, last_updated, created_at, updated_at) ON public.employee_skill TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, skill_id, proficiency_level, source, last_updated, created_at, updated_at) ON public.employee_skill TO tenant_hr;
GRANT INSERT (employee_id, skill_id, proficiency_level, source, last_updated) ON public.employee_skill TO tenant_hr;
GRANT UPDATE (employee_id, skill_id, proficiency_level, source, last_updated) ON public.employee_skill TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, skill_id, proficiency_level, source, last_updated, created_at, updated_at) ON public.employee_skill TO tenant_manager;
GRANT INSERT (employee_id, skill_id, source, last_updated) ON public.employee_skill TO tenant_manager;
GRANT UPDATE (employee_id, skill_id, source, last_updated) ON public.employee_skill TO tenant_manager;
GRANT SELECT (id, tenant_id, employee_id, skill_id, proficiency_level, source, last_updated, created_at, updated_at) ON public.employee_skill TO tenant_employee;
GRANT INSERT (employee_id, skill_id, source, last_updated) ON public.employee_skill TO tenant_employee;
GRANT UPDATE (employee_id, skill_id, source, last_updated) ON public.employee_skill TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, skill_id, proficiency_level, source, last_updated, created_at, updated_at) ON public.employee_skill TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, skill_id, proficiency_level, source, last_updated, created_at, updated_at) ON public.employee_skill TO agent_runtime;
GRANT INSERT (employee_id, skill_id, proficiency_level, source, last_updated) ON public.employee_skill TO agent_runtime;
GRANT UPDATE (employee_id, skill_id, proficiency_level, source, last_updated) ON public.employee_skill TO agent_runtime;

-- job_requisition
ALTER TABLE public.job_requisition ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.job_requisition FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.job_requisition
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.job_requisition AS RESTRICTIVE
    USING (app.can_see_employee(hiring_manager_id))
    WITH CHECK (app.can_see_employee(hiring_manager_id));
GRANT SELECT (id, tenant_id, position_id, hiring_manager_id, status, target_start_date, approval_request_id, created_at, updated_at) ON public.job_requisition TO daydor_ops;
GRANT INSERT (position_id, hiring_manager_id, status, target_start_date, approval_request_id) ON public.job_requisition TO daydor_ops;
GRANT UPDATE (position_id, hiring_manager_id, status, target_start_date, approval_request_id) ON public.job_requisition TO daydor_ops;
GRANT SELECT (id, tenant_id, position_id, hiring_manager_id, status, target_start_date, approval_request_id, created_at, updated_at) ON public.job_requisition TO tenant_founder;
GRANT INSERT (position_id, hiring_manager_id, status, target_start_date, approval_request_id) ON public.job_requisition TO tenant_founder;
GRANT UPDATE (position_id, hiring_manager_id, status, target_start_date, approval_request_id) ON public.job_requisition TO tenant_founder;
GRANT SELECT (id, tenant_id, position_id, hiring_manager_id, status, target_start_date, approval_request_id, created_at, updated_at) ON public.job_requisition TO tenant_hr;
GRANT INSERT (position_id, hiring_manager_id, status, target_start_date, approval_request_id) ON public.job_requisition TO tenant_hr;
GRANT UPDATE (position_id, hiring_manager_id, status, target_start_date, approval_request_id) ON public.job_requisition TO tenant_hr;
GRANT SELECT (id, tenant_id, position_id, hiring_manager_id, status, target_start_date, approval_request_id, created_at, updated_at) ON public.job_requisition TO tenant_payroll;
GRANT SELECT (id, tenant_id, position_id, hiring_manager_id, status, target_start_date, approval_request_id, created_at, updated_at) ON public.job_requisition TO tenant_manager;
GRANT INSERT (position_id, hiring_manager_id, status, target_start_date, approval_request_id) ON public.job_requisition TO tenant_manager;
GRANT UPDATE (position_id, hiring_manager_id, status, target_start_date, approval_request_id) ON public.job_requisition TO tenant_manager;
GRANT SELECT (id, tenant_id, position_id, hiring_manager_id, status, target_start_date, approval_request_id, created_at, updated_at) ON public.job_requisition TO external_auditor;
GRANT SELECT (id, tenant_id, position_id, hiring_manager_id, status, target_start_date, approval_request_id, created_at, updated_at) ON public.job_requisition TO agent_runtime;
GRANT INSERT (position_id, hiring_manager_id, status, target_start_date, approval_request_id) ON public.job_requisition TO agent_runtime;
GRANT UPDATE (position_id, hiring_manager_id, status, target_start_date, approval_request_id) ON public.job_requisition TO agent_runtime;

-- job_posting
ALTER TABLE public.job_posting ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.job_posting FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.job_posting
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, requisition_id, channel, pay_range_min, pay_range_max, pay_transparency_checked, posted_at, closed_at, created_at, updated_at) ON public.job_posting TO daydor_ops;
GRANT INSERT (requisition_id, channel, pay_range_min, pay_range_max, pay_transparency_checked, posted_at, closed_at) ON public.job_posting TO daydor_ops;
GRANT UPDATE (requisition_id, channel, pay_range_min, pay_range_max, pay_transparency_checked, posted_at, closed_at) ON public.job_posting TO daydor_ops;
GRANT SELECT (id, tenant_id, requisition_id, channel, pay_range_min, pay_range_max, pay_transparency_checked, posted_at, closed_at, created_at, updated_at) ON public.job_posting TO tenant_founder;
GRANT INSERT (requisition_id, channel, pay_range_min, pay_range_max, pay_transparency_checked, posted_at, closed_at) ON public.job_posting TO tenant_founder;
GRANT UPDATE (requisition_id, channel, pay_range_min, pay_range_max, pay_transparency_checked, posted_at, closed_at) ON public.job_posting TO tenant_founder;
GRANT SELECT (id, tenant_id, requisition_id, channel, pay_range_min, pay_range_max, pay_transparency_checked, posted_at, closed_at, created_at, updated_at) ON public.job_posting TO tenant_hr;
GRANT INSERT (requisition_id, channel, pay_range_min, pay_range_max, pay_transparency_checked, posted_at, closed_at) ON public.job_posting TO tenant_hr;
GRANT UPDATE (requisition_id, channel, pay_range_min, pay_range_max, pay_transparency_checked, posted_at, closed_at) ON public.job_posting TO tenant_hr;
GRANT SELECT (id, tenant_id, requisition_id, channel, pay_range_min, pay_range_max, pay_transparency_checked, posted_at, closed_at, created_at, updated_at) ON public.job_posting TO tenant_manager;
GRANT SELECT (id, tenant_id, requisition_id, channel, pay_range_min, pay_range_max, pay_transparency_checked, posted_at, closed_at, created_at, updated_at) ON public.job_posting TO tenant_employee;
GRANT SELECT (id, tenant_id, requisition_id, channel, pay_range_min, pay_range_max, pay_transparency_checked, posted_at, closed_at, created_at, updated_at) ON public.job_posting TO external_auditor;
GRANT SELECT (id, tenant_id, requisition_id, channel, pay_range_min, pay_range_max, pay_transparency_checked, posted_at, closed_at, created_at, updated_at) ON public.job_posting TO agent_runtime;
GRANT INSERT (requisition_id, channel, pay_range_min, pay_range_max, pay_transparency_checked, posted_at, closed_at) ON public.job_posting TO agent_runtime;
GRANT UPDATE (requisition_id, channel, pay_range_min, pay_range_max, pay_transparency_checked, posted_at, closed_at) ON public.job_posting TO agent_runtime;

-- candidate
ALTER TABLE public.candidate ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.candidate FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.candidate
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.candidate AS RESTRICTIVE
    USING (app.can_see_employee(converted_employee_id))
    WITH CHECK (app.can_see_employee(converted_employee_id));
GRANT SELECT (id, tenant_id, full_name, email, source, retain_until, converted_employee_id, created_at, updated_at) ON public.candidate TO daydor_ops;
GRANT INSERT (full_name, email, source, retain_until, converted_employee_id) ON public.candidate TO daydor_ops;
GRANT UPDATE (full_name, email, source, retain_until, converted_employee_id) ON public.candidate TO daydor_ops;
GRANT SELECT (id, tenant_id, full_name, email, source, retain_until, converted_employee_id, created_at, updated_at) ON public.candidate TO tenant_founder;
GRANT INSERT (full_name, email, source, retain_until, converted_employee_id) ON public.candidate TO tenant_founder;
GRANT UPDATE (full_name, email, source, retain_until, converted_employee_id) ON public.candidate TO tenant_founder;
GRANT SELECT (id, tenant_id, full_name, email, phone, resume_ref, source, retain_until, converted_employee_id, created_at, updated_at) ON public.candidate TO tenant_hr;
GRANT INSERT (full_name, email, phone, resume_ref, source, retain_until, converted_employee_id) ON public.candidate TO tenant_hr;
GRANT UPDATE (full_name, email, phone, resume_ref, source, retain_until, converted_employee_id) ON public.candidate TO tenant_hr;
GRANT SELECT (id, tenant_id, full_name, email, source, retain_until, converted_employee_id, created_at, updated_at) ON public.candidate TO tenant_manager;
GRANT SELECT (id, tenant_id, full_name, email, source, retain_until, converted_employee_id, created_at, updated_at) ON public.candidate TO external_auditor;
GRANT SELECT (id, tenant_id, full_name, email, phone, resume_ref, source, retain_until, converted_employee_id, created_at, updated_at) ON public.candidate TO agent_runtime;
GRANT INSERT (full_name, email, phone, resume_ref, source, retain_until, converted_employee_id) ON public.candidate TO agent_runtime;
GRANT UPDATE (full_name, email, phone, resume_ref, source, retain_until, converted_employee_id) ON public.candidate TO agent_runtime;
CREATE VIEW public.candidate_masked WITH (security_barrier) AS SELECT
    id,
    tenant_id,
    full_name,
    email,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'agent_runtime') THEN phone WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'external_auditor') THEN CASE WHEN phone IS NULL THEN NULL ELSE '****' || right(phone::text, 4) END ELSE NULL END)::text AS phone,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'agent_runtime') THEN resume_ref WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'external_auditor') THEN CASE WHEN resume_ref IS NULL THEN NULL ELSE '****' || right(resume_ref::text, 4) END ELSE NULL END)::text AS resume_ref,
    source,
    retain_until,
    converted_employee_id,
    created_at,
    updated_at
FROM public.candidate;
GRANT SELECT ON public.candidate_masked TO daydor_ops, tenant_founder, external_auditor;

-- application
ALTER TABLE public.application ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.application FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.application
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, candidate_id, requisition_id, stage, stage_changed_at, rejection_reason_code, created_at, updated_at) ON public.application TO daydor_ops;
GRANT INSERT (candidate_id, requisition_id, stage, stage_changed_at, rejection_reason_code) ON public.application TO daydor_ops;
GRANT UPDATE (candidate_id, requisition_id, stage, stage_changed_at, rejection_reason_code) ON public.application TO daydor_ops;
GRANT SELECT (id, tenant_id, candidate_id, requisition_id, stage, stage_changed_at, rejection_reason_code, created_at, updated_at) ON public.application TO tenant_founder;
GRANT INSERT (candidate_id, requisition_id, stage, stage_changed_at, rejection_reason_code) ON public.application TO tenant_founder;
GRANT UPDATE (candidate_id, requisition_id, stage, stage_changed_at, rejection_reason_code) ON public.application TO tenant_founder;
GRANT SELECT (id, tenant_id, candidate_id, requisition_id, stage, stage_changed_at, rejection_reason_code, created_at, updated_at) ON public.application TO tenant_hr;
GRANT INSERT (candidate_id, requisition_id, stage, stage_changed_at, rejection_reason_code) ON public.application TO tenant_hr;
GRANT UPDATE (candidate_id, requisition_id, stage, stage_changed_at, rejection_reason_code) ON public.application TO tenant_hr;
GRANT SELECT (id, tenant_id, candidate_id, requisition_id, stage, stage_changed_at, rejection_reason_code, created_at, updated_at) ON public.application TO tenant_manager;
GRANT SELECT (id, tenant_id, candidate_id, requisition_id, stage, stage_changed_at, rejection_reason_code, created_at, updated_at) ON public.application TO external_auditor;
GRANT SELECT (id, tenant_id, candidate_id, requisition_id, stage, stage_changed_at, rejection_reason_code, created_at, updated_at) ON public.application TO agent_runtime;
GRANT INSERT (candidate_id, requisition_id, stage, stage_changed_at, rejection_reason_code) ON public.application TO agent_runtime;
GRANT UPDATE (candidate_id, requisition_id, stage, stage_changed_at, rejection_reason_code) ON public.application TO agent_runtime;

-- screening_result
ALTER TABLE public.screening_result ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.screening_result FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.screening_result
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, application_id, aedt_audit_id, tool_name, model_version, score, recommendation, candidate_notified_at, human_reviewer_user_id, human_override, created_at, updated_at) ON public.screening_result TO daydor_ops;
GRANT INSERT (application_id, aedt_audit_id, tool_name, model_version, score, recommendation, candidate_notified_at, human_reviewer_user_id, human_override) ON public.screening_result TO daydor_ops;
GRANT UPDATE (application_id, aedt_audit_id, tool_name, model_version, score, recommendation, candidate_notified_at, human_reviewer_user_id, human_override) ON public.screening_result TO daydor_ops;
GRANT SELECT (id, tenant_id, application_id, aedt_audit_id, tool_name, model_version, score, recommendation, candidate_notified_at, human_reviewer_user_id, human_override, created_at, updated_at) ON public.screening_result TO tenant_founder;
GRANT INSERT (application_id, aedt_audit_id, tool_name, model_version, score, recommendation, candidate_notified_at, human_reviewer_user_id, human_override) ON public.screening_result TO tenant_founder;
GRANT UPDATE (application_id, aedt_audit_id, tool_name, model_version, score, recommendation, candidate_notified_at, human_reviewer_user_id, human_override) ON public.screening_result TO tenant_founder;
GRANT SELECT (id, tenant_id, application_id, aedt_audit_id, tool_name, model_version, score, recommendation, candidate_notified_at, human_reviewer_user_id, human_override, created_at, updated_at) ON public.screening_result TO tenant_hr;
GRANT INSERT (application_id, aedt_audit_id, tool_name, model_version, score, recommendation, candidate_notified_at, human_reviewer_user_id, human_override) ON public.screening_result TO tenant_hr;
GRANT UPDATE (application_id, aedt_audit_id, tool_name, model_version, score, recommendation, candidate_notified_at, human_reviewer_user_id, human_override) ON public.screening_result TO tenant_hr;
GRANT SELECT (id, tenant_id, application_id, aedt_audit_id, tool_name, model_version, score, recommendation, candidate_notified_at, human_reviewer_user_id, human_override, created_at, updated_at) ON public.screening_result TO external_auditor;
GRANT SELECT (id, tenant_id, application_id, aedt_audit_id, tool_name, model_version, score, recommendation, candidate_notified_at, human_reviewer_user_id, human_override, created_at, updated_at) ON public.screening_result TO agent_runtime;
GRANT INSERT (application_id, aedt_audit_id, tool_name, model_version, score, recommendation, candidate_notified_at, human_reviewer_user_id, human_override) ON public.screening_result TO agent_runtime;
GRANT UPDATE (application_id, aedt_audit_id, tool_name, model_version, score, recommendation, candidate_notified_at, human_reviewer_user_id, human_override) ON public.screening_result TO agent_runtime;
CREATE VIEW public.screening_result_masked WITH (security_barrier) AS SELECT
    id,
    tenant_id,
    application_id,
    aedt_audit_id,
    (CASE WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_hr', 'external_auditor', 'agent_runtime') THEN tool_name WHEN app.current_app_role() IN ('tenant_manager') THEN CASE WHEN tool_name IS NULL THEN NULL ELSE '****' || right(tool_name::text, 4) END ELSE NULL END)::text AS tool_name,
    (CASE WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_hr', 'external_auditor', 'agent_runtime') THEN model_version WHEN app.current_app_role() IN ('tenant_manager') THEN CASE WHEN model_version IS NULL THEN NULL ELSE '****' || right(model_version::text, 4) END ELSE NULL END)::text AS model_version,
    (CASE WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_hr', 'external_auditor', 'agent_runtime') THEN score WHEN app.current_app_role() IN ('tenant_manager') THEN NULL ELSE NULL END)::numeric(14,2) AS score,
    (CASE WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_hr', 'external_auditor', 'agent_runtime') THEN recommendation WHEN app.current_app_role() IN ('tenant_manager') THEN NULL ELSE NULL END)::text AS recommendation,
    candidate_notified_at,
    human_reviewer_user_id,
    human_override,
    created_at,
    updated_at
FROM public.screening_result;
GRANT SELECT ON public.screening_result_masked TO tenant_manager;

-- aedt_audit
ALTER TABLE public.aedt_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.aedt_audit FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.aedt_audit
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, tool_name, auditor_firm, audit_date, expires_on, impact_ratio_summary, published_url, created_at, updated_at) ON public.aedt_audit TO daydor_ops;
GRANT INSERT (tool_name, auditor_firm, audit_date, expires_on, impact_ratio_summary, published_url) ON public.aedt_audit TO daydor_ops;
GRANT UPDATE (tool_name, auditor_firm, audit_date, expires_on, impact_ratio_summary, published_url) ON public.aedt_audit TO daydor_ops;
GRANT SELECT (id, tenant_id, tool_name, auditor_firm, audit_date, expires_on, impact_ratio_summary, published_url, created_at, updated_at) ON public.aedt_audit TO tenant_founder;
GRANT INSERT (tool_name, auditor_firm, audit_date, expires_on, impact_ratio_summary, published_url) ON public.aedt_audit TO tenant_founder;
GRANT UPDATE (tool_name, auditor_firm, audit_date, expires_on, impact_ratio_summary, published_url) ON public.aedt_audit TO tenant_founder;
GRANT SELECT (id, tenant_id, tool_name, auditor_firm, audit_date, expires_on, impact_ratio_summary, published_url, created_at, updated_at) ON public.aedt_audit TO tenant_hr;
GRANT INSERT (tool_name, auditor_firm, audit_date, expires_on, impact_ratio_summary, published_url) ON public.aedt_audit TO tenant_hr;
GRANT UPDATE (tool_name, auditor_firm, audit_date, expires_on, impact_ratio_summary, published_url) ON public.aedt_audit TO tenant_hr;
GRANT SELECT (id, tenant_id, tool_name, auditor_firm, audit_date, expires_on, impact_ratio_summary, published_url, created_at, updated_at) ON public.aedt_audit TO external_auditor;
GRANT SELECT (id, tenant_id, tool_name, auditor_firm, audit_date, expires_on, impact_ratio_summary, published_url, created_at, updated_at) ON public.aedt_audit TO agent_runtime;
GRANT INSERT (tool_name, auditor_firm, audit_date, expires_on, impact_ratio_summary, published_url) ON public.aedt_audit TO agent_runtime;
GRANT UPDATE (tool_name, auditor_firm, audit_date, expires_on, impact_ratio_summary, published_url) ON public.aedt_audit TO agent_runtime;

-- interview
ALTER TABLE public.interview ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.interview FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.interview
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.interview AS RESTRICTIVE
    USING (app.can_see_employee(interviewer_employee_id))
    WITH CHECK (app.can_see_employee(interviewer_employee_id));
GRANT SELECT (id, tenant_id, application_id, interviewer_employee_id, scheduled_at, scorecard, recommendation, created_at, updated_at) ON public.interview TO daydor_ops;
GRANT INSERT (application_id, interviewer_employee_id, scheduled_at, scorecard, recommendation) ON public.interview TO daydor_ops;
GRANT UPDATE (application_id, interviewer_employee_id, scheduled_at, scorecard, recommendation) ON public.interview TO daydor_ops;
GRANT SELECT (id, tenant_id, application_id, interviewer_employee_id, scheduled_at, scorecard, recommendation, created_at, updated_at) ON public.interview TO tenant_founder;
GRANT INSERT (application_id, interviewer_employee_id, scheduled_at, scorecard, recommendation) ON public.interview TO tenant_founder;
GRANT UPDATE (application_id, interviewer_employee_id, scheduled_at, scorecard, recommendation) ON public.interview TO tenant_founder;
GRANT SELECT (id, tenant_id, application_id, interviewer_employee_id, scheduled_at, scorecard, recommendation, created_at, updated_at) ON public.interview TO tenant_hr;
GRANT INSERT (application_id, interviewer_employee_id, scheduled_at, scorecard, recommendation) ON public.interview TO tenant_hr;
GRANT UPDATE (application_id, interviewer_employee_id, scheduled_at, scorecard, recommendation) ON public.interview TO tenant_hr;
GRANT SELECT (id, tenant_id, application_id, interviewer_employee_id, scheduled_at, scorecard, recommendation, created_at, updated_at) ON public.interview TO tenant_manager;
GRANT INSERT (application_id, interviewer_employee_id, scheduled_at) ON public.interview TO tenant_manager;
GRANT UPDATE (application_id, interviewer_employee_id, scheduled_at) ON public.interview TO tenant_manager;
GRANT SELECT (id, tenant_id, application_id, interviewer_employee_id, scheduled_at, scorecard, recommendation, created_at, updated_at) ON public.interview TO external_auditor;
GRANT SELECT (id, tenant_id, application_id, interviewer_employee_id, scheduled_at, scorecard, recommendation, created_at, updated_at) ON public.interview TO agent_runtime;
GRANT INSERT (application_id, interviewer_employee_id, scheduled_at, scorecard, recommendation) ON public.interview TO agent_runtime;
GRANT UPDATE (application_id, interviewer_employee_id, scheduled_at, scorecard, recommendation) ON public.interview TO agent_runtime;

-- background_check
ALTER TABLE public.background_check ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.background_check FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.background_check
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, candidate_id, vendor, ordered_at, status, adverse_action_stage, pre_adverse_notice_at, created_at, updated_at) ON public.background_check TO daydor_ops;
GRANT SELECT (id, tenant_id, candidate_id, vendor, ordered_at, status, findings_summary, adverse_action_stage, pre_adverse_notice_at, created_at, updated_at) ON public.background_check TO tenant_hr;
GRANT INSERT (candidate_id, vendor, ordered_at, status, adverse_action_stage, pre_adverse_notice_at) ON public.background_check TO tenant_hr;
GRANT UPDATE (candidate_id, vendor, ordered_at, status, adverse_action_stage, pre_adverse_notice_at) ON public.background_check TO tenant_hr;
GRANT SELECT (id, tenant_id, candidate_id, vendor, ordered_at, status, adverse_action_stage, pre_adverse_notice_at, created_at, updated_at) ON public.background_check TO external_auditor;
GRANT SELECT (id, tenant_id, candidate_id, vendor, ordered_at, status, adverse_action_stage, pre_adverse_notice_at, created_at, updated_at) ON public.background_check TO agent_runtime;
GRANT INSERT (candidate_id, vendor, ordered_at, status, adverse_action_stage, pre_adverse_notice_at) ON public.background_check TO agent_runtime;
GRANT UPDATE (candidate_id, vendor, ordered_at, status, adverse_action_stage, pre_adverse_notice_at) ON public.background_check TO agent_runtime;

-- offer
ALTER TABLE public.offer ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.offer FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.offer
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, application_id, comp_band_id, proposed_base, proposed_equity, within_band, approval_request_id, offer_document_id, sent_at, accepted_at, created_at, updated_at) ON public.offer TO daydor_ops;
GRANT INSERT (application_id, comp_band_id, proposed_base, proposed_equity, within_band, approval_request_id, offer_document_id, sent_at, accepted_at) ON public.offer TO daydor_ops;
GRANT UPDATE (application_id, comp_band_id, proposed_base, proposed_equity, within_band, approval_request_id, offer_document_id, sent_at, accepted_at) ON public.offer TO daydor_ops;
GRANT SELECT (id, tenant_id, application_id, comp_band_id, proposed_base, proposed_equity, within_band, approval_request_id, offer_document_id, sent_at, accepted_at, created_at, updated_at) ON public.offer TO tenant_founder;
GRANT INSERT (application_id, comp_band_id, proposed_base, proposed_equity, within_band, approval_request_id, offer_document_id, sent_at, accepted_at) ON public.offer TO tenant_founder;
GRANT UPDATE (application_id, comp_band_id, proposed_base, proposed_equity, within_band, approval_request_id, offer_document_id, sent_at, accepted_at) ON public.offer TO tenant_founder;
GRANT SELECT (id, tenant_id, application_id, comp_band_id, proposed_base, proposed_equity, within_band, approval_request_id, offer_document_id, sent_at, accepted_at, created_at, updated_at) ON public.offer TO tenant_hr;
GRANT INSERT (application_id, comp_band_id, proposed_base, proposed_equity, within_band, approval_request_id, offer_document_id, sent_at, accepted_at) ON public.offer TO tenant_hr;
GRANT UPDATE (application_id, comp_band_id, proposed_base, proposed_equity, within_band, approval_request_id, offer_document_id, sent_at, accepted_at) ON public.offer TO tenant_hr;
GRANT SELECT (id, tenant_id, application_id, comp_band_id, proposed_base, proposed_equity, within_band, approval_request_id, offer_document_id, sent_at, accepted_at, created_at, updated_at) ON public.offer TO tenant_payroll;
GRANT SELECT (id, tenant_id, application_id, comp_band_id, proposed_base, proposed_equity, within_band, approval_request_id, offer_document_id, sent_at, accepted_at, created_at, updated_at) ON public.offer TO tenant_manager;
GRANT SELECT (id, tenant_id, application_id, comp_band_id, proposed_base, proposed_equity, within_band, approval_request_id, offer_document_id, sent_at, accepted_at, created_at, updated_at) ON public.offer TO external_auditor;
GRANT SELECT (id, tenant_id, application_id, comp_band_id, proposed_base, proposed_equity, within_band, approval_request_id, offer_document_id, sent_at, accepted_at, created_at, updated_at) ON public.offer TO agent_runtime;
GRANT INSERT (application_id, comp_band_id, proposed_base, proposed_equity, within_band, approval_request_id, offer_document_id, sent_at, accepted_at) ON public.offer TO agent_runtime;
GRANT UPDATE (application_id, comp_band_id, proposed_base, proposed_equity, within_band, approval_request_id, offer_document_id, sent_at, accepted_at) ON public.offer TO agent_runtime;

-- checklist
ALTER TABLE public.checklist ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.checklist FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.checklist
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.checklist AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, kind, template_key, status, due_date, created_at, updated_at) ON public.checklist TO daydor_ops;
GRANT INSERT (employee_id, kind, template_key, status, due_date) ON public.checklist TO daydor_ops;
GRANT UPDATE (employee_id, kind, template_key, status, due_date) ON public.checklist TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, kind, template_key, status, due_date, created_at, updated_at) ON public.checklist TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, kind, template_key, status, due_date, created_at, updated_at) ON public.checklist TO tenant_hr;
GRANT INSERT (employee_id, kind, template_key, status, due_date) ON public.checklist TO tenant_hr;
GRANT UPDATE (employee_id, kind, template_key, status, due_date) ON public.checklist TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, kind, template_key, status, due_date, created_at, updated_at) ON public.checklist TO tenant_payroll;
GRANT SELECT (id, tenant_id, employee_id, kind, template_key, status, due_date, created_at, updated_at) ON public.checklist TO tenant_it;
GRANT INSERT (employee_id, kind, template_key, status, due_date) ON public.checklist TO tenant_it;
GRANT UPDATE (employee_id, kind, template_key, status, due_date) ON public.checklist TO tenant_it;
GRANT SELECT (id, tenant_id, employee_id, kind, template_key, status, due_date, created_at, updated_at) ON public.checklist TO tenant_manager;
GRANT INSERT (employee_id, kind, template_key, status, due_date) ON public.checklist TO tenant_manager;
GRANT UPDATE (employee_id, kind, template_key, status, due_date) ON public.checklist TO tenant_manager;
GRANT SELECT (id, tenant_id, employee_id, kind, template_key, status, due_date, created_at, updated_at) ON public.checklist TO tenant_employee;
GRANT INSERT (employee_id, kind, template_key, status, due_date) ON public.checklist TO tenant_employee;
GRANT UPDATE (employee_id, kind, template_key, status, due_date) ON public.checklist TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, kind, template_key, status, due_date, created_at, updated_at) ON public.checklist TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, kind, template_key, status, due_date, created_at, updated_at) ON public.checklist TO agent_runtime;
GRANT INSERT (employee_id, kind, template_key, status, due_date) ON public.checklist TO agent_runtime;
GRANT UPDATE (employee_id, kind, template_key, status, due_date) ON public.checklist TO agent_runtime;

-- checklist_task
ALTER TABLE public.checklist_task ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.checklist_task FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.checklist_task
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, checklist_id, owner_domain, assignee_user_id, title, status, due_at, completed_at, blocking, created_at, updated_at) ON public.checklist_task TO daydor_ops;
GRANT INSERT (checklist_id, owner_domain, assignee_user_id, title, status, due_at, completed_at, blocking) ON public.checklist_task TO daydor_ops;
GRANT UPDATE (checklist_id, owner_domain, assignee_user_id, title, status, due_at, completed_at, blocking) ON public.checklist_task TO daydor_ops;
GRANT SELECT (id, tenant_id, checklist_id, owner_domain, assignee_user_id, title, status, due_at, completed_at, blocking, created_at, updated_at) ON public.checklist_task TO tenant_founder;
GRANT SELECT (id, tenant_id, checklist_id, owner_domain, assignee_user_id, title, status, due_at, completed_at, blocking, created_at, updated_at) ON public.checklist_task TO tenant_hr;
GRANT INSERT (checklist_id, owner_domain, assignee_user_id, title, status, due_at, completed_at, blocking) ON public.checklist_task TO tenant_hr;
GRANT UPDATE (checklist_id, owner_domain, assignee_user_id, title, status, due_at, completed_at, blocking) ON public.checklist_task TO tenant_hr;
GRANT SELECT (id, tenant_id, checklist_id, owner_domain, assignee_user_id, title, status, due_at, completed_at, blocking, created_at, updated_at) ON public.checklist_task TO tenant_payroll;
GRANT SELECT (id, tenant_id, checklist_id, owner_domain, assignee_user_id, title, status, due_at, completed_at, blocking, created_at, updated_at) ON public.checklist_task TO tenant_it;
GRANT INSERT (checklist_id, owner_domain, assignee_user_id, title, status, due_at, completed_at, blocking) ON public.checklist_task TO tenant_it;
GRANT UPDATE (checklist_id, owner_domain, assignee_user_id, title, status, due_at, completed_at, blocking) ON public.checklist_task TO tenant_it;
GRANT SELECT (id, tenant_id, checklist_id, owner_domain, assignee_user_id, title, status, due_at, completed_at, blocking, created_at, updated_at) ON public.checklist_task TO tenant_manager;
GRANT INSERT (checklist_id, owner_domain, assignee_user_id, title, status, due_at, completed_at, blocking) ON public.checklist_task TO tenant_manager;
GRANT UPDATE (checklist_id, owner_domain, assignee_user_id, title, status, due_at, completed_at, blocking) ON public.checklist_task TO tenant_manager;
GRANT SELECT (id, tenant_id, checklist_id, owner_domain, assignee_user_id, title, status, due_at, completed_at, blocking, created_at, updated_at) ON public.checklist_task TO tenant_employee;
GRANT INSERT (checklist_id, owner_domain, assignee_user_id, title, status, due_at, completed_at, blocking) ON public.checklist_task TO tenant_employee;
GRANT UPDATE (checklist_id, owner_domain, assignee_user_id, title, status, due_at, completed_at, blocking) ON public.checklist_task TO tenant_employee;
GRANT SELECT (id, tenant_id, checklist_id, owner_domain, assignee_user_id, title, status, due_at, completed_at, blocking, created_at, updated_at) ON public.checklist_task TO external_auditor;
GRANT SELECT (id, tenant_id, checklist_id, owner_domain, assignee_user_id, title, status, due_at, completed_at, blocking, created_at, updated_at) ON public.checklist_task TO agent_runtime;
GRANT INSERT (checklist_id, owner_domain, assignee_user_id, title, status, due_at, completed_at, blocking) ON public.checklist_task TO agent_runtime;
GRANT UPDATE (checklist_id, owner_domain, assignee_user_id, title, status, due_at, completed_at, blocking) ON public.checklist_task TO agent_runtime;

-- access_role_template
ALTER TABLE public.access_role_template ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.access_role_template FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.access_role_template
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, job_profile_id, department_id, app_bundle, created_at, updated_at) ON public.access_role_template TO daydor_ops;
GRANT INSERT (job_profile_id, department_id, app_bundle) ON public.access_role_template TO daydor_ops;
GRANT UPDATE (job_profile_id, department_id, app_bundle) ON public.access_role_template TO daydor_ops;
GRANT SELECT (id, tenant_id, job_profile_id, department_id, app_bundle, created_at, updated_at) ON public.access_role_template TO tenant_founder;
GRANT SELECT (id, tenant_id, job_profile_id, department_id, app_bundle, created_at, updated_at) ON public.access_role_template TO tenant_hr;
GRANT SELECT (id, tenant_id, job_profile_id, department_id, app_bundle, created_at, updated_at) ON public.access_role_template TO tenant_it;
GRANT INSERT (job_profile_id, department_id, app_bundle) ON public.access_role_template TO tenant_it;
GRANT UPDATE (job_profile_id, department_id, app_bundle) ON public.access_role_template TO tenant_it;
GRANT SELECT (id, tenant_id, job_profile_id, department_id, app_bundle, created_at, updated_at) ON public.access_role_template TO tenant_manager;
GRANT SELECT (id, tenant_id, job_profile_id, department_id, app_bundle, created_at, updated_at) ON public.access_role_template TO tenant_employee;
GRANT SELECT (id, tenant_id, job_profile_id, department_id, app_bundle, created_at, updated_at) ON public.access_role_template TO external_auditor;
GRANT SELECT (id, tenant_id, job_profile_id, department_id, app_bundle, created_at, updated_at) ON public.access_role_template TO agent_runtime;

-- identity_account
ALTER TABLE public.identity_account ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.identity_account FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.identity_account
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.identity_account AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, directory_provider, external_id, status, provisioned_at, deprovisioned_at, approval_request_id, created_at, updated_at) ON public.identity_account TO daydor_ops;
GRANT INSERT (employee_id, directory_provider, external_id, status, provisioned_at, deprovisioned_at, approval_request_id) ON public.identity_account TO daydor_ops;
GRANT UPDATE (employee_id, directory_provider, external_id, status, provisioned_at, deprovisioned_at, approval_request_id) ON public.identity_account TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, directory_provider, external_id, status, provisioned_at, deprovisioned_at, approval_request_id, created_at, updated_at) ON public.identity_account TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, directory_provider, external_id, status, provisioned_at, deprovisioned_at, approval_request_id, created_at, updated_at) ON public.identity_account TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, directory_provider, external_id, status, provisioned_at, deprovisioned_at, approval_request_id, created_at, updated_at) ON public.identity_account TO tenant_it;
GRANT INSERT (employee_id, directory_provider, status, provisioned_at, deprovisioned_at, approval_request_id) ON public.identity_account TO tenant_it;
GRANT UPDATE (employee_id, directory_provider, status, provisioned_at, deprovisioned_at, approval_request_id) ON public.identity_account TO tenant_it;
GRANT SELECT (id, tenant_id, employee_id, directory_provider, external_id, status, provisioned_at, deprovisioned_at, approval_request_id, created_at, updated_at) ON public.identity_account TO tenant_manager;
GRANT SELECT (id, tenant_id, employee_id, directory_provider, external_id, status, provisioned_at, deprovisioned_at, approval_request_id, created_at, updated_at) ON public.identity_account TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, directory_provider, external_id, status, provisioned_at, deprovisioned_at, approval_request_id, created_at, updated_at) ON public.identity_account TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, directory_provider, external_id, status, provisioned_at, deprovisioned_at, approval_request_id, created_at, updated_at) ON public.identity_account TO agent_runtime;
GRANT INSERT (employee_id, directory_provider, external_id, status, provisioned_at, deprovisioned_at, approval_request_id) ON public.identity_account TO agent_runtime;
GRANT UPDATE (employee_id, directory_provider, external_id, status, provisioned_at, deprovisioned_at, approval_request_id) ON public.identity_account TO agent_runtime;

-- app_access_grant
ALTER TABLE public.app_access_grant ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.app_access_grant FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.app_access_grant
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, identity_account_id, app_name, permission_level, source, template_id, approval_request_id, granted_at, revoked_at, created_at, updated_at) ON public.app_access_grant TO daydor_ops;
GRANT INSERT (identity_account_id, app_name, permission_level, source, template_id, approval_request_id, granted_at, revoked_at) ON public.app_access_grant TO daydor_ops;
GRANT UPDATE (identity_account_id, app_name, permission_level, source, template_id, approval_request_id, granted_at, revoked_at) ON public.app_access_grant TO daydor_ops;
GRANT SELECT (id, tenant_id, identity_account_id, app_name, permission_level, source, template_id, approval_request_id, granted_at, revoked_at, created_at, updated_at) ON public.app_access_grant TO tenant_founder;
GRANT SELECT (id, tenant_id, identity_account_id, app_name, permission_level, source, template_id, approval_request_id, granted_at, revoked_at, created_at, updated_at) ON public.app_access_grant TO tenant_hr;
GRANT SELECT (id, tenant_id, identity_account_id, app_name, permission_level, source, template_id, approval_request_id, granted_at, revoked_at, created_at, updated_at) ON public.app_access_grant TO tenant_it;
GRANT INSERT (identity_account_id, app_name, permission_level, source, template_id, approval_request_id, granted_at, revoked_at) ON public.app_access_grant TO tenant_it;
GRANT UPDATE (identity_account_id, app_name, permission_level, source, template_id, approval_request_id, granted_at, revoked_at) ON public.app_access_grant TO tenant_it;
GRANT SELECT (id, tenant_id, identity_account_id, app_name, permission_level, source, template_id, approval_request_id, granted_at, revoked_at, created_at, updated_at) ON public.app_access_grant TO tenant_manager;
GRANT SELECT (id, tenant_id, identity_account_id, app_name, permission_level, source, template_id, approval_request_id, granted_at, revoked_at, created_at, updated_at) ON public.app_access_grant TO tenant_employee;
GRANT SELECT (id, tenant_id, identity_account_id, app_name, permission_level, source, template_id, approval_request_id, granted_at, revoked_at, created_at, updated_at) ON public.app_access_grant TO external_auditor;
GRANT SELECT (id, tenant_id, identity_account_id, app_name, permission_level, source, template_id, approval_request_id, granted_at, revoked_at, created_at, updated_at) ON public.app_access_grant TO agent_runtime;
GRANT INSERT (identity_account_id, app_name, permission_level, source, template_id, approval_request_id, granted_at, revoked_at) ON public.app_access_grant TO agent_runtime;
GRANT UPDATE (identity_account_id, app_name, permission_level, source, template_id, approval_request_id, granted_at, revoked_at) ON public.app_access_grant TO agent_runtime;

-- device
ALTER TABLE public.device ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.device FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.device
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, asset_tag, model, serial_no, status, purchase_cost, created_at, updated_at) ON public.device TO daydor_ops;
GRANT INSERT (asset_tag, model, serial_no, status, purchase_cost) ON public.device TO daydor_ops;
GRANT UPDATE (asset_tag, model, serial_no, status, purchase_cost) ON public.device TO daydor_ops;
GRANT SELECT (id, tenant_id, asset_tag, model, serial_no, status, purchase_cost, created_at, updated_at) ON public.device TO tenant_founder;
GRANT SELECT (id, tenant_id, asset_tag, model, serial_no, status, purchase_cost, created_at, updated_at) ON public.device TO tenant_hr;
GRANT SELECT (id, tenant_id, asset_tag, model, serial_no, status, purchase_cost, created_at, updated_at) ON public.device TO tenant_it;
GRANT INSERT (asset_tag, model, status, purchase_cost) ON public.device TO tenant_it;
GRANT UPDATE (asset_tag, model, status, purchase_cost) ON public.device TO tenant_it;
GRANT SELECT (id, tenant_id, asset_tag, model, serial_no, status, purchase_cost, created_at, updated_at) ON public.device TO tenant_manager;
GRANT SELECT (id, tenant_id, asset_tag, model, serial_no, status, purchase_cost, created_at, updated_at) ON public.device TO external_auditor;
GRANT SELECT (id, tenant_id, asset_tag, model, serial_no, status, purchase_cost, created_at, updated_at) ON public.device TO agent_runtime;
GRANT INSERT (asset_tag, model, serial_no, status, purchase_cost) ON public.device TO agent_runtime;
GRANT UPDATE (asset_tag, model, serial_no, status, purchase_cost) ON public.device TO agent_runtime;

-- device_assignment
ALTER TABLE public.device_assignment ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.device_assignment FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.device_assignment
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.device_assignment AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, device_id, employee_id, assigned_at, tracking_no, returned_at, created_at, updated_at) ON public.device_assignment TO daydor_ops;
GRANT INSERT (device_id, employee_id, assigned_at, tracking_no, returned_at) ON public.device_assignment TO daydor_ops;
GRANT UPDATE (device_id, employee_id, assigned_at, tracking_no, returned_at) ON public.device_assignment TO daydor_ops;
GRANT SELECT (id, tenant_id, device_id, employee_id, assigned_at, tracking_no, returned_at, created_at, updated_at) ON public.device_assignment TO tenant_founder;
GRANT SELECT (id, tenant_id, device_id, employee_id, assigned_at, shipped_to_address, tracking_no, returned_at, created_at, updated_at) ON public.device_assignment TO tenant_hr;
GRANT SELECT (id, tenant_id, device_id, employee_id, assigned_at, tracking_no, returned_at, created_at, updated_at) ON public.device_assignment TO tenant_it;
GRANT INSERT (device_id, employee_id, assigned_at, returned_at) ON public.device_assignment TO tenant_it;
GRANT UPDATE (device_id, employee_id, assigned_at, returned_at) ON public.device_assignment TO tenant_it;
GRANT SELECT (id, tenant_id, device_id, employee_id, assigned_at, tracking_no, returned_at, created_at, updated_at) ON public.device_assignment TO tenant_manager;
GRANT SELECT (id, tenant_id, device_id, employee_id, assigned_at, shipped_to_address, tracking_no, returned_at, created_at, updated_at) ON public.device_assignment TO tenant_employee;
GRANT SELECT (id, tenant_id, device_id, employee_id, assigned_at, tracking_no, returned_at, created_at, updated_at) ON public.device_assignment TO external_auditor;
GRANT SELECT (id, tenant_id, device_id, employee_id, assigned_at, shipped_to_address, tracking_no, returned_at, created_at, updated_at) ON public.device_assignment TO agent_runtime;
GRANT INSERT (device_id, employee_id, assigned_at, shipped_to_address, tracking_no, returned_at) ON public.device_assignment TO agent_runtime;
GRANT UPDATE (device_id, employee_id, assigned_at, shipped_to_address, tracking_no, returned_at) ON public.device_assignment TO agent_runtime;
CREATE VIEW public.device_assignment_masked WITH (security_barrier) AS SELECT
    id,
    tenant_id,
    device_id,
    employee_id,
    assigned_at,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'tenant_employee', 'agent_runtime') THEN shipped_to_address WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'external_auditor') THEN CASE WHEN shipped_to_address IS NULL THEN NULL ELSE '****' || right(shipped_to_address::text, 4) END ELSE NULL END)::text AS shipped_to_address,
    tracking_no,
    returned_at,
    created_at,
    updated_at
FROM public.device_assignment;
GRANT SELECT ON public.device_assignment_masked TO daydor_ops, tenant_founder, external_auditor;

-- payroll_profile
ALTER TABLE public.payroll_profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payroll_profile FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.payroll_profile
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.payroll_profile AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, pay_frequency, payment_method, work_state, tax_state, reciprocity_agreement_flag, state_registration_status, w4_elections, created_at, updated_at) ON public.payroll_profile TO daydor_ops;
GRANT INSERT (employee_id, pay_frequency, payment_method, work_state, tax_state, reciprocity_agreement_flag, state_registration_status, w4_elections) ON public.payroll_profile TO daydor_ops;
GRANT UPDATE (employee_id, pay_frequency, payment_method, work_state, tax_state, reciprocity_agreement_flag, state_registration_status, w4_elections) ON public.payroll_profile TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, pay_frequency, payment_method, work_state, tax_state, reciprocity_agreement_flag, state_registration_status, w4_elections, created_at, updated_at) ON public.payroll_profile TO tenant_founder;
GRANT INSERT (employee_id, pay_frequency, payment_method, work_state, tax_state, reciprocity_agreement_flag, state_registration_status, w4_elections) ON public.payroll_profile TO tenant_founder;
GRANT UPDATE (employee_id, pay_frequency, payment_method, work_state, tax_state, reciprocity_agreement_flag, state_registration_status, w4_elections) ON public.payroll_profile TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, pay_frequency, payment_method, work_state, tax_state, reciprocity_agreement_flag, state_registration_status, w4_elections, uan_number, esic_ip_number, created_at, updated_at) ON public.payroll_profile TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, pay_frequency, payment_method, work_state, tax_state, reciprocity_agreement_flag, state_registration_status, w4_elections, created_at, updated_at) ON public.payroll_profile TO tenant_payroll;
GRANT INSERT (employee_id, payment_method, reciprocity_agreement_flag, state_registration_status, w4_elections) ON public.payroll_profile TO tenant_payroll;
GRANT UPDATE (employee_id, payment_method, reciprocity_agreement_flag, state_registration_status, w4_elections) ON public.payroll_profile TO tenant_payroll;
GRANT SELECT (id, tenant_id, employee_id, pay_frequency, payment_method, work_state, tax_state, reciprocity_agreement_flag, state_registration_status, w4_elections, uan_number, esic_ip_number, created_at, updated_at) ON public.payroll_profile TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, pay_frequency, payment_method, work_state, tax_state, reciprocity_agreement_flag, state_registration_status, w4_elections, created_at, updated_at) ON public.payroll_profile TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, pay_frequency, payment_method, work_state, tax_state, reciprocity_agreement_flag, state_registration_status, w4_elections, uan_number, esic_ip_number, created_at, updated_at) ON public.payroll_profile TO agent_runtime;
GRANT INSERT (employee_id, pay_frequency, payment_method, work_state, tax_state, reciprocity_agreement_flag, state_registration_status, w4_elections, uan_number, esic_ip_number) ON public.payroll_profile TO agent_runtime;
GRANT UPDATE (employee_id, pay_frequency, payment_method, work_state, tax_state, reciprocity_agreement_flag, state_registration_status, w4_elections, uan_number, esic_ip_number) ON public.payroll_profile TO agent_runtime;
CREATE VIEW public.payroll_profile_masked WITH (security_barrier) AS SELECT
    id,
    tenant_id,
    employee_id,
    pay_frequency,
    payment_method,
    work_state,
    tax_state,
    reciprocity_agreement_flag,
    state_registration_status,
    w4_elections,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'tenant_employee', 'agent_runtime') THEN uan_number WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_payroll', 'external_auditor') THEN CASE WHEN uan_number IS NULL THEN NULL ELSE '****' || right(uan_number::text, 4) END ELSE NULL END)::text AS uan_number,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'tenant_employee', 'agent_runtime') THEN esic_ip_number WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_payroll', 'external_auditor') THEN CASE WHEN esic_ip_number IS NULL THEN NULL ELSE '****' || right(esic_ip_number::text, 4) END ELSE NULL END)::text AS esic_ip_number,
    created_at,
    updated_at
FROM public.payroll_profile;
GRANT SELECT ON public.payroll_profile_masked TO daydor_ops, tenant_founder, tenant_payroll, external_auditor;

-- payroll_run
ALTER TABLE public.payroll_run ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payroll_run FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.payroll_run
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, legal_entity_id, period_start, period_end, status, gross_total, net_total, anomaly_score, approval_request_id, disbursed_at, retention_class, created_at, updated_at) ON public.payroll_run TO daydor_ops;
GRANT INSERT (legal_entity_id, period_start, period_end, status, anomaly_score, approval_request_id, disbursed_at, retention_class) ON public.payroll_run TO daydor_ops;
GRANT UPDATE (legal_entity_id, period_start, period_end, status, anomaly_score, approval_request_id, disbursed_at, retention_class) ON public.payroll_run TO daydor_ops;
GRANT SELECT (id, tenant_id, legal_entity_id, period_start, period_end, status, gross_total, net_total, anomaly_score, approval_request_id, disbursed_at, retention_class, created_at, updated_at) ON public.payroll_run TO tenant_founder;
GRANT INSERT (legal_entity_id, period_start, period_end, status, anomaly_score, approval_request_id, disbursed_at, retention_class) ON public.payroll_run TO tenant_founder;
GRANT UPDATE (legal_entity_id, period_start, period_end, status, anomaly_score, approval_request_id, disbursed_at, retention_class) ON public.payroll_run TO tenant_founder;
GRANT SELECT (id, tenant_id, legal_entity_id, period_start, period_end, status, gross_total, net_total, anomaly_score, approval_request_id, disbursed_at, retention_class, created_at, updated_at) ON public.payroll_run TO tenant_hr;
GRANT SELECT (id, tenant_id, legal_entity_id, period_start, period_end, status, gross_total, net_total, anomaly_score, approval_request_id, disbursed_at, retention_class, created_at, updated_at) ON public.payroll_run TO tenant_payroll;
GRANT INSERT (legal_entity_id, period_start, period_end, status, anomaly_score, approval_request_id, disbursed_at, retention_class) ON public.payroll_run TO tenant_payroll;
GRANT UPDATE (legal_entity_id, period_start, period_end, status, anomaly_score, approval_request_id, disbursed_at, retention_class) ON public.payroll_run TO tenant_payroll;
GRANT SELECT (id, tenant_id, legal_entity_id, period_start, period_end, status, gross_total, net_total, anomaly_score, approval_request_id, disbursed_at, retention_class, created_at, updated_at) ON public.payroll_run TO external_auditor;
GRANT SELECT (id, tenant_id, legal_entity_id, period_start, period_end, status, gross_total, net_total, anomaly_score, approval_request_id, disbursed_at, retention_class, created_at, updated_at) ON public.payroll_run TO agent_runtime;
GRANT INSERT (legal_entity_id, period_start, period_end, status, anomaly_score, approval_request_id, disbursed_at, retention_class) ON public.payroll_run TO agent_runtime;
GRANT UPDATE (legal_entity_id, period_start, period_end, status, anomaly_score, approval_request_id, disbursed_at, retention_class) ON public.payroll_run TO agent_runtime;

-- payslip
ALTER TABLE public.payslip ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payslip FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.payslip
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.payslip AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, payroll_run_id, employee_id, employment_record_id, gross_pay, net_pay, tax_withheld, issued_at, retention_class, created_at, updated_at) ON public.payslip TO daydor_ops;
GRANT INSERT (payroll_run_id, employee_id, employment_record_id, issued_at, retention_class) ON public.payslip TO daydor_ops;
GRANT UPDATE (payroll_run_id, employee_id, employment_record_id, issued_at, retention_class) ON public.payslip TO daydor_ops;
GRANT SELECT (id, tenant_id, payroll_run_id, employee_id, employment_record_id, gross_pay, net_pay, tax_withheld, issued_at, retention_class, created_at, updated_at) ON public.payslip TO tenant_founder;
GRANT INSERT (payroll_run_id, employee_id, employment_record_id, issued_at, retention_class) ON public.payslip TO tenant_founder;
GRANT UPDATE (payroll_run_id, employee_id, employment_record_id, issued_at, retention_class) ON public.payslip TO tenant_founder;
GRANT SELECT (id, tenant_id, payroll_run_id, employee_id, employment_record_id, gross_pay, net_pay, tax_withheld, issued_at, retention_class, created_at, updated_at) ON public.payslip TO tenant_hr;
GRANT SELECT (id, tenant_id, payroll_run_id, employee_id, employment_record_id, gross_pay, net_pay, tax_withheld, issued_at, retention_class, created_at, updated_at) ON public.payslip TO tenant_payroll;
GRANT INSERT (payroll_run_id, employee_id, employment_record_id, issued_at, retention_class) ON public.payslip TO tenant_payroll;
GRANT UPDATE (payroll_run_id, employee_id, employment_record_id, issued_at, retention_class) ON public.payslip TO tenant_payroll;
GRANT SELECT (id, tenant_id, payroll_run_id, employee_id, employment_record_id, gross_pay, net_pay, tax_withheld, issued_at, retention_class, created_at, updated_at) ON public.payslip TO tenant_employee;
GRANT SELECT (id, tenant_id, payroll_run_id, employee_id, employment_record_id, gross_pay, net_pay, tax_withheld, issued_at, retention_class, created_at, updated_at) ON public.payslip TO external_auditor;
GRANT SELECT (id, tenant_id, payroll_run_id, employee_id, employment_record_id, gross_pay, net_pay, tax_withheld, issued_at, retention_class, created_at, updated_at) ON public.payslip TO agent_runtime;
GRANT INSERT (payroll_run_id, employee_id, employment_record_id, issued_at, retention_class) ON public.payslip TO agent_runtime;
GRANT UPDATE (payroll_run_id, employee_id, employment_record_id, issued_at, retention_class) ON public.payslip TO agent_runtime;

-- payslip_line
ALTER TABLE public.payslip_line ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payslip_line FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.payslip_line
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, payslip_id, component_code, amount, rule_id, created_at, updated_at) ON public.payslip_line TO daydor_ops;
GRANT INSERT (payslip_id, component_code, amount, rule_id) ON public.payslip_line TO daydor_ops;
GRANT UPDATE (payslip_id, component_code, amount, rule_id) ON public.payslip_line TO daydor_ops;
GRANT SELECT (id, tenant_id, payslip_id, component_code, amount, rule_id, created_at, updated_at) ON public.payslip_line TO tenant_founder;
GRANT INSERT (payslip_id, component_code, amount, rule_id) ON public.payslip_line TO tenant_founder;
GRANT UPDATE (payslip_id, component_code, amount, rule_id) ON public.payslip_line TO tenant_founder;
GRANT SELECT (id, tenant_id, payslip_id, component_code, amount, rule_id, created_at, updated_at) ON public.payslip_line TO tenant_hr;
GRANT SELECT (id, tenant_id, payslip_id, component_code, amount, rule_id, created_at, updated_at) ON public.payslip_line TO tenant_payroll;
GRANT INSERT (payslip_id, component_code, amount, rule_id) ON public.payslip_line TO tenant_payroll;
GRANT UPDATE (payslip_id, component_code, amount, rule_id) ON public.payslip_line TO tenant_payroll;
GRANT SELECT (id, tenant_id, payslip_id, component_code, amount, rule_id, created_at, updated_at) ON public.payslip_line TO tenant_employee;
GRANT SELECT (id, tenant_id, payslip_id, component_code, amount, rule_id, created_at, updated_at) ON public.payslip_line TO external_auditor;
GRANT SELECT (id, tenant_id, payslip_id, component_code, amount, rule_id, created_at, updated_at) ON public.payslip_line TO agent_runtime;
GRANT INSERT (payslip_id, component_code, amount, rule_id) ON public.payslip_line TO agent_runtime;
GRANT UPDATE (payslip_id, component_code, amount, rule_id) ON public.payslip_line TO agent_runtime;

-- garnishment_order
ALTER TABLE public.garnishment_order ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.garnishment_order FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.garnishment_order
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.garnishment_order AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, priority, effective_from, effective_to, created_at, updated_at) ON public.garnishment_order TO daydor_ops;
GRANT INSERT (employee_id, priority, effective_from, effective_to) ON public.garnishment_order TO daydor_ops;
GRANT UPDATE (employee_id, priority, effective_from, effective_to) ON public.garnishment_order TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, issuing_authority, order_type, amount_or_pct, priority, effective_from, effective_to, created_at, updated_at) ON public.garnishment_order TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, issuing_authority, order_type, amount_or_pct, priority, effective_from, effective_to, created_at, updated_at) ON public.garnishment_order TO tenant_payroll;
GRANT INSERT (employee_id, priority, effective_from, effective_to) ON public.garnishment_order TO tenant_payroll;
GRANT UPDATE (employee_id, priority, effective_from, effective_to) ON public.garnishment_order TO tenant_payroll;
GRANT SELECT (id, tenant_id, employee_id, issuing_authority, order_type, amount_or_pct, priority, effective_from, effective_to, created_at, updated_at) ON public.garnishment_order TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, priority, effective_from, effective_to, created_at, updated_at) ON public.garnishment_order TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, issuing_authority, order_type, amount_or_pct, priority, effective_from, effective_to, created_at, updated_at) ON public.garnishment_order TO agent_runtime;

-- filing_record
ALTER TABLE public.filing_record ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.filing_record FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.filing_record
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, legal_entity_id, scheme, period, filed_on, acknowledgement_no, document_id, approval_request_id, retention_class, created_at, updated_at) ON public.filing_record TO daydor_ops;
GRANT INSERT (legal_entity_id, scheme, period, filed_on, acknowledgement_no, document_id, approval_request_id, retention_class) ON public.filing_record TO daydor_ops;
GRANT UPDATE (legal_entity_id, scheme, period, filed_on, acknowledgement_no, document_id, approval_request_id, retention_class) ON public.filing_record TO daydor_ops;
GRANT SELECT (id, tenant_id, legal_entity_id, scheme, period, filed_on, acknowledgement_no, document_id, approval_request_id, retention_class, created_at, updated_at) ON public.filing_record TO tenant_founder;
GRANT INSERT (legal_entity_id, scheme, period, filed_on, acknowledgement_no, document_id, approval_request_id, retention_class) ON public.filing_record TO tenant_founder;
GRANT UPDATE (legal_entity_id, scheme, period, filed_on, acknowledgement_no, document_id, approval_request_id, retention_class) ON public.filing_record TO tenant_founder;
GRANT SELECT (id, tenant_id, legal_entity_id, scheme, period, filed_on, acknowledgement_no, document_id, approval_request_id, retention_class, created_at, updated_at) ON public.filing_record TO tenant_hr;
GRANT SELECT (id, tenant_id, legal_entity_id, scheme, period, filed_on, acknowledgement_no, document_id, approval_request_id, retention_class, created_at, updated_at) ON public.filing_record TO tenant_payroll;
GRANT INSERT (legal_entity_id, scheme, period, filed_on, document_id, approval_request_id, retention_class) ON public.filing_record TO tenant_payroll;
GRANT UPDATE (legal_entity_id, scheme, period, filed_on, document_id, approval_request_id, retention_class) ON public.filing_record TO tenant_payroll;
GRANT SELECT (id, tenant_id, legal_entity_id, scheme, period, filed_on, acknowledgement_no, document_id, approval_request_id, retention_class, created_at, updated_at) ON public.filing_record TO external_auditor;
GRANT SELECT (id, tenant_id, legal_entity_id, scheme, period, filed_on, acknowledgement_no, document_id, approval_request_id, retention_class, created_at, updated_at) ON public.filing_record TO agent_runtime;
GRANT INSERT (legal_entity_id, scheme, period, filed_on, acknowledgement_no, document_id, approval_request_id, retention_class) ON public.filing_record TO agent_runtime;
GRANT UPDATE (legal_entity_id, scheme, period, filed_on, acknowledgement_no, document_id, approval_request_id, retention_class) ON public.filing_record TO agent_runtime;

-- gratuity_accrual_balance
ALTER TABLE public.gratuity_accrual_balance ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gratuity_accrual_balance FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.gratuity_accrual_balance
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.gratuity_accrual_balance AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, as_of_period, accrued_amount, gratuity_wage_base, created_at, updated_at) ON public.gratuity_accrual_balance TO daydor_ops;
GRANT INSERT (employee_id, as_of_period, accrued_amount, gratuity_wage_base) ON public.gratuity_accrual_balance TO daydor_ops;
GRANT UPDATE (employee_id, as_of_period, accrued_amount, gratuity_wage_base) ON public.gratuity_accrual_balance TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, as_of_period, accrued_amount, gratuity_wage_base, created_at, updated_at) ON public.gratuity_accrual_balance TO tenant_founder;
GRANT INSERT (employee_id, as_of_period, accrued_amount, gratuity_wage_base) ON public.gratuity_accrual_balance TO tenant_founder;
GRANT UPDATE (employee_id, as_of_period, accrued_amount, gratuity_wage_base) ON public.gratuity_accrual_balance TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, as_of_period, accrued_amount, gratuity_wage_base, created_at, updated_at) ON public.gratuity_accrual_balance TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, as_of_period, accrued_amount, gratuity_wage_base, created_at, updated_at) ON public.gratuity_accrual_balance TO tenant_payroll;
GRANT INSERT (employee_id, as_of_period, accrued_amount, gratuity_wage_base) ON public.gratuity_accrual_balance TO tenant_payroll;
GRANT UPDATE (employee_id, as_of_period, accrued_amount, gratuity_wage_base) ON public.gratuity_accrual_balance TO tenant_payroll;
GRANT SELECT (id, tenant_id, employee_id, as_of_period, accrued_amount, gratuity_wage_base, created_at, updated_at) ON public.gratuity_accrual_balance TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, as_of_period, accrued_amount, gratuity_wage_base, created_at, updated_at) ON public.gratuity_accrual_balance TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, as_of_period, accrued_amount, gratuity_wage_base, created_at, updated_at) ON public.gratuity_accrual_balance TO agent_runtime;
GRANT INSERT (employee_id, as_of_period, accrued_amount, gratuity_wage_base) ON public.gratuity_accrual_balance TO agent_runtime;
GRANT UPDATE (employee_id, as_of_period, accrued_amount, gratuity_wage_base) ON public.gratuity_accrual_balance TO agent_runtime;

-- contractor_invoice
ALTER TABLE public.contractor_invoice ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contractor_invoice FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.contractor_invoice
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.contractor_invoice AS RESTRICTIVE
    USING (app.can_see_employee(contractor_employee_id))
    WITH CHECK (app.can_see_employee(contractor_employee_id));
GRANT SELECT (id, tenant_id, contractor_employee_id, legal_entity_id, period, amount, currency, status, approval_request_id, paid_at, created_at, updated_at) ON public.contractor_invoice TO daydor_ops;
GRANT INSERT (contractor_employee_id, legal_entity_id, period, amount, currency, status, approval_request_id, paid_at) ON public.contractor_invoice TO daydor_ops;
GRANT UPDATE (contractor_employee_id, legal_entity_id, period, amount, currency, status, approval_request_id, paid_at) ON public.contractor_invoice TO daydor_ops;
GRANT SELECT (id, tenant_id, contractor_employee_id, legal_entity_id, period, amount, currency, status, approval_request_id, paid_at, created_at, updated_at) ON public.contractor_invoice TO tenant_founder;
GRANT INSERT (contractor_employee_id, legal_entity_id, period, amount, currency, status, approval_request_id, paid_at) ON public.contractor_invoice TO tenant_founder;
GRANT UPDATE (contractor_employee_id, legal_entity_id, period, amount, currency, status, approval_request_id, paid_at) ON public.contractor_invoice TO tenant_founder;
GRANT SELECT (id, tenant_id, contractor_employee_id, legal_entity_id, period, amount, currency, status, approval_request_id, paid_at, created_at, updated_at) ON public.contractor_invoice TO tenant_hr;
GRANT SELECT (id, tenant_id, contractor_employee_id, legal_entity_id, period, amount, currency, status, approval_request_id, paid_at, created_at, updated_at) ON public.contractor_invoice TO tenant_payroll;
GRANT INSERT (contractor_employee_id, legal_entity_id, period, amount, currency, status, approval_request_id, paid_at) ON public.contractor_invoice TO tenant_payroll;
GRANT UPDATE (contractor_employee_id, legal_entity_id, period, amount, currency, status, approval_request_id, paid_at) ON public.contractor_invoice TO tenant_payroll;
GRANT SELECT (id, tenant_id, contractor_employee_id, legal_entity_id, period, amount, currency, status, approval_request_id, paid_at, created_at, updated_at) ON public.contractor_invoice TO tenant_manager;
GRANT SELECT (id, tenant_id, contractor_employee_id, legal_entity_id, period, amount, currency, status, approval_request_id, paid_at, created_at, updated_at) ON public.contractor_invoice TO external_auditor;
GRANT SELECT (id, tenant_id, contractor_employee_id, legal_entity_id, period, amount, currency, status, approval_request_id, paid_at, created_at, updated_at) ON public.contractor_invoice TO agent_runtime;
GRANT INSERT (contractor_employee_id, legal_entity_id, period, amount, currency, status, approval_request_id, paid_at) ON public.contractor_invoice TO agent_runtime;
GRANT UPDATE (contractor_employee_id, legal_entity_id, period, amount, currency, status, approval_request_id, paid_at) ON public.contractor_invoice TO agent_runtime;

-- benefit_plan
ALTER TABLE public.benefit_plan ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.benefit_plan FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.benefit_plan
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, legal_entity_id, plan_type, carrier, plan_year, employer_contribution, created_at, updated_at) ON public.benefit_plan TO daydor_ops;
GRANT INSERT (legal_entity_id, plan_type, carrier, plan_year, employer_contribution) ON public.benefit_plan TO daydor_ops;
GRANT UPDATE (legal_entity_id, plan_type, carrier, plan_year, employer_contribution) ON public.benefit_plan TO daydor_ops;
GRANT SELECT (id, tenant_id, legal_entity_id, plan_type, carrier, plan_year, employer_contribution, created_at, updated_at) ON public.benefit_plan TO tenant_founder;
GRANT SELECT (id, tenant_id, legal_entity_id, plan_type, carrier, plan_year, employer_contribution, created_at, updated_at) ON public.benefit_plan TO tenant_hr;
GRANT INSERT (legal_entity_id, plan_type, carrier, plan_year, employer_contribution) ON public.benefit_plan TO tenant_hr;
GRANT UPDATE (legal_entity_id, plan_type, carrier, plan_year, employer_contribution) ON public.benefit_plan TO tenant_hr;
GRANT SELECT (id, tenant_id, legal_entity_id, plan_type, carrier, plan_year, employer_contribution, created_at, updated_at) ON public.benefit_plan TO tenant_payroll;
GRANT SELECT (id, tenant_id, legal_entity_id, plan_type, carrier, plan_year, employer_contribution, created_at, updated_at) ON public.benefit_plan TO tenant_employee;
GRANT SELECT (id, tenant_id, legal_entity_id, plan_type, carrier, plan_year, employer_contribution, created_at, updated_at) ON public.benefit_plan TO external_auditor;
GRANT SELECT (id, tenant_id, legal_entity_id, plan_type, carrier, plan_year, employer_contribution, created_at, updated_at) ON public.benefit_plan TO agent_runtime;

-- benefit_election
ALTER TABLE public.benefit_election ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.benefit_election FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.benefit_election
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.benefit_election AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, benefit_plan_id, coverage_tier, employee_cost, life_event_id, effective_from, effective_to, carrier_sent_at, created_at, updated_at) ON public.benefit_election TO daydor_ops;
GRANT INSERT (employee_id, benefit_plan_id, coverage_tier, employee_cost, life_event_id, effective_from, effective_to, carrier_sent_at) ON public.benefit_election TO daydor_ops;
GRANT UPDATE (employee_id, benefit_plan_id, coverage_tier, employee_cost, life_event_id, effective_from, effective_to, carrier_sent_at) ON public.benefit_election TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, benefit_plan_id, coverage_tier, employee_cost, life_event_id, effective_from, effective_to, carrier_sent_at, created_at, updated_at) ON public.benefit_election TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, benefit_plan_id, coverage_tier, employee_cost, life_event_id, effective_from, effective_to, carrier_sent_at, created_at, updated_at) ON public.benefit_election TO tenant_hr;
GRANT INSERT (employee_id, benefit_plan_id, coverage_tier, employee_cost, life_event_id, effective_from, effective_to, carrier_sent_at) ON public.benefit_election TO tenant_hr;
GRANT UPDATE (employee_id, benefit_plan_id, coverage_tier, employee_cost, life_event_id, effective_from, effective_to, carrier_sent_at) ON public.benefit_election TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, benefit_plan_id, coverage_tier, employee_cost, life_event_id, effective_from, effective_to, carrier_sent_at, created_at, updated_at) ON public.benefit_election TO tenant_payroll;
GRANT SELECT (id, tenant_id, employee_id, benefit_plan_id, coverage_tier, employee_cost, life_event_id, effective_from, effective_to, carrier_sent_at, created_at, updated_at) ON public.benefit_election TO tenant_employee;
GRANT INSERT (employee_id, benefit_plan_id, life_event_id, effective_from, effective_to, carrier_sent_at) ON public.benefit_election TO tenant_employee;
GRANT UPDATE (employee_id, benefit_plan_id, life_event_id, effective_from, effective_to, carrier_sent_at) ON public.benefit_election TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, benefit_plan_id, coverage_tier, employee_cost, life_event_id, effective_from, effective_to, carrier_sent_at, created_at, updated_at) ON public.benefit_election TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, benefit_plan_id, coverage_tier, employee_cost, life_event_id, effective_from, effective_to, carrier_sent_at, created_at, updated_at) ON public.benefit_election TO agent_runtime;
GRANT INSERT (employee_id, benefit_plan_id, coverage_tier, employee_cost, life_event_id, effective_from, effective_to, carrier_sent_at) ON public.benefit_election TO agent_runtime;
GRANT UPDATE (employee_id, benefit_plan_id, coverage_tier, employee_cost, life_event_id, effective_from, effective_to, carrier_sent_at) ON public.benefit_election TO agent_runtime;

-- dependent
ALTER TABLE public.dependent ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dependent FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.dependent
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.dependent AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, covered_plan_ids, created_at, updated_at) ON public.dependent TO daydor_ops;
GRANT INSERT (employee_id, covered_plan_ids) ON public.dependent TO daydor_ops;
GRANT UPDATE (employee_id, covered_plan_ids) ON public.dependent TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, full_name, relationship, date_of_birth, covered_plan_ids, created_at, updated_at) ON public.dependent TO tenant_hr;
GRANT INSERT (employee_id, full_name, relationship, date_of_birth, covered_plan_ids) ON public.dependent TO tenant_hr;
GRANT UPDATE (employee_id, full_name, relationship, date_of_birth, covered_plan_ids) ON public.dependent TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, full_name, relationship, date_of_birth, covered_plan_ids, created_at, updated_at) ON public.dependent TO tenant_employee;
GRANT INSERT (employee_id, full_name, relationship, date_of_birth) ON public.dependent TO tenant_employee;
GRANT UPDATE (employee_id, full_name, relationship, date_of_birth) ON public.dependent TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, covered_plan_ids, created_at, updated_at) ON public.dependent TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, full_name, relationship, date_of_birth, covered_plan_ids, created_at, updated_at) ON public.dependent TO agent_runtime;
GRANT INSERT (employee_id, full_name, relationship, date_of_birth, covered_plan_ids) ON public.dependent TO agent_runtime;
GRANT UPDATE (employee_id, full_name, relationship, date_of_birth, covered_plan_ids) ON public.dependent TO agent_runtime;
CREATE VIEW public.dependent_masked WITH (security_barrier) AS SELECT
    id,
    tenant_id,
    employee_id,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'tenant_employee', 'agent_runtime') THEN full_name WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_payroll', 'external_auditor') THEN CASE WHEN full_name IS NULL THEN NULL ELSE '****' || right(full_name::text, 4) END ELSE NULL END)::text AS full_name,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'tenant_employee', 'agent_runtime') THEN relationship WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_payroll', 'external_auditor') THEN NULL ELSE NULL END)::text AS relationship,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'tenant_employee', 'agent_runtime') THEN date_of_birth WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_payroll', 'external_auditor') THEN NULL ELSE NULL END)::date AS date_of_birth,
    (CASE WHEN app.current_app_role() IN ('daydor_ops', 'tenant_hr', 'tenant_employee', 'external_auditor', 'agent_runtime') THEN covered_plan_ids WHEN app.current_app_role() IN ('tenant_founder', 'tenant_payroll') THEN NULL ELSE NULL END)::jsonb AS covered_plan_ids,
    created_at,
    updated_at
FROM public.dependent;
GRANT SELECT ON public.dependent_masked TO daydor_ops, tenant_founder, tenant_payroll, external_auditor;

-- life_event
ALTER TABLE public.life_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.life_event FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.life_event
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.life_event AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, evidence_document_id, status, window_closes_at, created_at, updated_at) ON public.life_event TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, event_type, event_date, evidence_document_id, status, window_closes_at, created_at, updated_at) ON public.life_event TO tenant_hr;
GRANT INSERT (employee_id, event_date, evidence_document_id, status, window_closes_at) ON public.life_event TO tenant_hr;
GRANT UPDATE (employee_id, event_date, evidence_document_id, status, window_closes_at) ON public.life_event TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, event_type, event_date, evidence_document_id, status, window_closes_at, created_at, updated_at) ON public.life_event TO tenant_employee;
GRANT INSERT (employee_id, event_type, event_date, evidence_document_id, status, window_closes_at) ON public.life_event TO tenant_employee;
GRANT UPDATE (employee_id, event_type, event_date, evidence_document_id, status, window_closes_at) ON public.life_event TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, evidence_document_id, status, window_closes_at, created_at, updated_at) ON public.life_event TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, event_type, event_date, evidence_document_id, status, window_closes_at, created_at, updated_at) ON public.life_event TO agent_runtime;
GRANT INSERT (employee_id, event_date, evidence_document_id, status, window_closes_at) ON public.life_event TO agent_runtime;
GRANT UPDATE (employee_id, event_date, evidence_document_id, status, window_closes_at) ON public.life_event TO agent_runtime;
CREATE VIEW public.life_event_masked WITH (security_barrier) AS SELECT
    id,
    tenant_id,
    employee_id,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'tenant_employee', 'agent_runtime') THEN event_type ELSE NULL END)::text AS event_type,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'tenant_employee', 'agent_runtime') THEN event_date WHEN app.current_app_role() IN ('daydor_ops', 'external_auditor') THEN NULL ELSE NULL END)::date AS event_date,
    evidence_document_id,
    status,
    window_closes_at,
    created_at,
    updated_at
FROM public.life_event;
GRANT SELECT ON public.life_event_masked TO daydor_ops, external_auditor;

-- cobra_event
ALTER TABLE public.cobra_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cobra_event FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.cobra_event
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.cobra_event AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, qualifying_event, event_date, notice_due_at, notice_sent_at, election_status, approval_request_id, created_at, updated_at) ON public.cobra_event TO daydor_ops;
GRANT INSERT (employee_id, qualifying_event, event_date, notice_due_at, notice_sent_at, election_status, approval_request_id) ON public.cobra_event TO daydor_ops;
GRANT UPDATE (employee_id, qualifying_event, event_date, notice_due_at, notice_sent_at, election_status, approval_request_id) ON public.cobra_event TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, qualifying_event, event_date, notice_due_at, notice_sent_at, election_status, approval_request_id, created_at, updated_at) ON public.cobra_event TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, qualifying_event, event_date, notice_due_at, notice_sent_at, election_status, approval_request_id, created_at, updated_at) ON public.cobra_event TO tenant_hr;
GRANT INSERT (employee_id, qualifying_event, event_date, notice_due_at, notice_sent_at, election_status, approval_request_id) ON public.cobra_event TO tenant_hr;
GRANT UPDATE (employee_id, qualifying_event, event_date, notice_due_at, notice_sent_at, election_status, approval_request_id) ON public.cobra_event TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, qualifying_event, event_date, notice_due_at, notice_sent_at, election_status, approval_request_id, created_at, updated_at) ON public.cobra_event TO tenant_payroll;
GRANT SELECT (id, tenant_id, employee_id, qualifying_event, event_date, notice_due_at, notice_sent_at, election_status, approval_request_id, created_at, updated_at) ON public.cobra_event TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, qualifying_event, event_date, notice_due_at, notice_sent_at, election_status, approval_request_id, created_at, updated_at) ON public.cobra_event TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, qualifying_event, event_date, notice_due_at, notice_sent_at, election_status, approval_request_id, created_at, updated_at) ON public.cobra_event TO agent_runtime;
GRANT INSERT (employee_id, qualifying_event, event_date, notice_due_at, notice_sent_at, election_status, approval_request_id) ON public.cobra_event TO agent_runtime;
GRANT UPDATE (employee_id, qualifying_event, event_date, notice_due_at, notice_sent_at, election_status, approval_request_id) ON public.cobra_event TO agent_runtime;

-- time_punch
ALTER TABLE public.time_punch ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.time_punch FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.time_punch
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.time_punch AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, punched_at, kind, source, created_at, updated_at) ON public.time_punch TO daydor_ops;
GRANT INSERT (employee_id, punched_at, kind, source) ON public.time_punch TO daydor_ops;
GRANT UPDATE (employee_id, punched_at, kind, source) ON public.time_punch TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, punched_at, kind, source, created_at, updated_at) ON public.time_punch TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, punched_at, kind, source, geo_point, created_at, updated_at) ON public.time_punch TO tenant_hr;
GRANT INSERT (employee_id, punched_at, kind, source, geo_point) ON public.time_punch TO tenant_hr;
GRANT UPDATE (employee_id, punched_at, kind, source, geo_point) ON public.time_punch TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, punched_at, kind, source, created_at, updated_at) ON public.time_punch TO tenant_payroll;
GRANT SELECT (id, tenant_id, employee_id, punched_at, kind, source, created_at, updated_at) ON public.time_punch TO tenant_manager;
GRANT INSERT (employee_id, kind, source) ON public.time_punch TO tenant_manager;
GRANT UPDATE (employee_id, kind, source) ON public.time_punch TO tenant_manager;
GRANT SELECT (id, tenant_id, employee_id, punched_at, kind, source, geo_point, created_at, updated_at) ON public.time_punch TO tenant_employee;
GRANT INSERT (employee_id, punched_at, kind, source, geo_point) ON public.time_punch TO tenant_employee;
GRANT UPDATE (employee_id, punched_at, kind, source, geo_point) ON public.time_punch TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, punched_at, kind, source, created_at, updated_at) ON public.time_punch TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, punched_at, kind, source, geo_point, created_at, updated_at) ON public.time_punch TO agent_runtime;
CREATE VIEW public.time_punch_masked WITH (security_barrier) AS SELECT
    id,
    tenant_id,
    employee_id,
    punched_at,
    kind,
    source,
    (CASE WHEN app.current_app_role() IN ('tenant_hr', 'tenant_employee', 'agent_runtime') THEN geo_point WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_payroll', 'external_auditor') THEN CASE WHEN geo_point IS NULL THEN NULL ELSE '****' || right(geo_point::text, 4) END ELSE NULL END)::text AS geo_point,
    created_at,
    updated_at
FROM public.time_punch;
GRANT SELECT ON public.time_punch_masked TO daydor_ops, tenant_founder, tenant_payroll, external_auditor;

-- timecard
ALTER TABLE public.timecard ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.timecard FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.timecard
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.timecard AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, period_start, period_end, regular_hours, overtime_hours, status, approved_by_user_id, created_at, updated_at) ON public.timecard TO daydor_ops;
GRANT INSERT (employee_id, period_start, period_end, regular_hours, overtime_hours, status, approved_by_user_id) ON public.timecard TO daydor_ops;
GRANT UPDATE (employee_id, period_start, period_end, regular_hours, overtime_hours, status, approved_by_user_id) ON public.timecard TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, period_start, period_end, regular_hours, overtime_hours, status, approved_by_user_id, created_at, updated_at) ON public.timecard TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, period_start, period_end, regular_hours, overtime_hours, status, approved_by_user_id, created_at, updated_at) ON public.timecard TO tenant_hr;
GRANT INSERT (employee_id, period_start, period_end, regular_hours, overtime_hours, status, approved_by_user_id) ON public.timecard TO tenant_hr;
GRANT UPDATE (employee_id, period_start, period_end, regular_hours, overtime_hours, status, approved_by_user_id) ON public.timecard TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, period_start, period_end, regular_hours, overtime_hours, status, approved_by_user_id, created_at, updated_at) ON public.timecard TO tenant_payroll;
GRANT SELECT (id, tenant_id, employee_id, period_start, period_end, regular_hours, overtime_hours, status, approved_by_user_id, created_at, updated_at) ON public.timecard TO tenant_manager;
GRANT INSERT (employee_id, period_start, period_end, status, approved_by_user_id) ON public.timecard TO tenant_manager;
GRANT UPDATE (employee_id, period_start, period_end, status, approved_by_user_id) ON public.timecard TO tenant_manager;
GRANT SELECT (id, tenant_id, employee_id, period_start, period_end, regular_hours, overtime_hours, status, approved_by_user_id, created_at, updated_at) ON public.timecard TO tenant_employee;
GRANT INSERT (employee_id, period_start, period_end, status, approved_by_user_id) ON public.timecard TO tenant_employee;
GRANT UPDATE (employee_id, period_start, period_end, status, approved_by_user_id) ON public.timecard TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, period_start, period_end, regular_hours, overtime_hours, status, approved_by_user_id, created_at, updated_at) ON public.timecard TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, period_start, period_end, regular_hours, overtime_hours, status, approved_by_user_id, created_at, updated_at) ON public.timecard TO agent_runtime;
GRANT INSERT (employee_id, period_start, period_end, regular_hours, overtime_hours, status, approved_by_user_id) ON public.timecard TO agent_runtime;
GRANT UPDATE (employee_id, period_start, period_end, regular_hours, overtime_hours, status, approved_by_user_id) ON public.timecard TO agent_runtime;

-- leave_policy
ALTER TABLE public.leave_policy ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.leave_policy FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.leave_policy
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, legal_entity_id, leave_type, accrual_rule, carry_forward_cap, created_at, updated_at) ON public.leave_policy TO daydor_ops;
GRANT INSERT (legal_entity_id, leave_type, accrual_rule, carry_forward_cap) ON public.leave_policy TO daydor_ops;
GRANT UPDATE (legal_entity_id, leave_type, accrual_rule, carry_forward_cap) ON public.leave_policy TO daydor_ops;
GRANT SELECT (id, tenant_id, legal_entity_id, leave_type, accrual_rule, carry_forward_cap, created_at, updated_at) ON public.leave_policy TO tenant_founder;
GRANT SELECT (id, tenant_id, legal_entity_id, leave_type, accrual_rule, carry_forward_cap, created_at, updated_at) ON public.leave_policy TO tenant_hr;
GRANT INSERT (legal_entity_id, leave_type, accrual_rule, carry_forward_cap) ON public.leave_policy TO tenant_hr;
GRANT UPDATE (legal_entity_id, leave_type, accrual_rule, carry_forward_cap) ON public.leave_policy TO tenant_hr;
GRANT SELECT (id, tenant_id, legal_entity_id, leave_type, accrual_rule, carry_forward_cap, created_at, updated_at) ON public.leave_policy TO tenant_payroll;
GRANT SELECT (id, tenant_id, legal_entity_id, leave_type, accrual_rule, carry_forward_cap, created_at, updated_at) ON public.leave_policy TO tenant_manager;
GRANT INSERT (legal_entity_id, leave_type, accrual_rule, carry_forward_cap) ON public.leave_policy TO tenant_manager;
GRANT UPDATE (legal_entity_id, leave_type, accrual_rule, carry_forward_cap) ON public.leave_policy TO tenant_manager;
GRANT SELECT (id, tenant_id, legal_entity_id, leave_type, accrual_rule, carry_forward_cap, created_at, updated_at) ON public.leave_policy TO tenant_employee;
GRANT SELECT (id, tenant_id, legal_entity_id, leave_type, accrual_rule, carry_forward_cap, created_at, updated_at) ON public.leave_policy TO external_auditor;
GRANT SELECT (id, tenant_id, legal_entity_id, leave_type, accrual_rule, carry_forward_cap, created_at, updated_at) ON public.leave_policy TO agent_runtime;

-- leave_balance
ALTER TABLE public.leave_balance ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.leave_balance FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.leave_balance
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.leave_balance AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, leave_policy_id, balance_days, as_of, created_at, updated_at) ON public.leave_balance TO daydor_ops;
GRANT INSERT (employee_id, leave_policy_id, balance_days, as_of) ON public.leave_balance TO daydor_ops;
GRANT UPDATE (employee_id, leave_policy_id, balance_days, as_of) ON public.leave_balance TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, leave_policy_id, balance_days, as_of, created_at, updated_at) ON public.leave_balance TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, leave_policy_id, balance_days, as_of, created_at, updated_at) ON public.leave_balance TO tenant_hr;
GRANT INSERT (employee_id, leave_policy_id, balance_days, as_of) ON public.leave_balance TO tenant_hr;
GRANT UPDATE (employee_id, leave_policy_id, balance_days, as_of) ON public.leave_balance TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, leave_policy_id, balance_days, as_of, created_at, updated_at) ON public.leave_balance TO tenant_payroll;
GRANT SELECT (id, tenant_id, employee_id, leave_policy_id, balance_days, as_of, created_at, updated_at) ON public.leave_balance TO tenant_manager;
GRANT INSERT (employee_id, leave_policy_id, as_of) ON public.leave_balance TO tenant_manager;
GRANT UPDATE (employee_id, leave_policy_id, as_of) ON public.leave_balance TO tenant_manager;
GRANT SELECT (id, tenant_id, employee_id, leave_policy_id, balance_days, as_of, created_at, updated_at) ON public.leave_balance TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, leave_policy_id, balance_days, as_of, created_at, updated_at) ON public.leave_balance TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, leave_policy_id, balance_days, as_of, created_at, updated_at) ON public.leave_balance TO agent_runtime;
GRANT INSERT (employee_id, leave_policy_id, balance_days, as_of) ON public.leave_balance TO agent_runtime;
GRANT UPDATE (employee_id, leave_policy_id, balance_days, as_of) ON public.leave_balance TO agent_runtime;

-- leave_request
ALTER TABLE public.leave_request ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.leave_request FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.leave_request
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.leave_request AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, leave_policy_id, start_date, end_date, status, approval_request_id, created_at, updated_at) ON public.leave_request TO daydor_ops;
GRANT INSERT (employee_id, leave_policy_id, start_date, end_date, status, approval_request_id) ON public.leave_request TO daydor_ops;
GRANT UPDATE (employee_id, leave_policy_id, start_date, end_date, status, approval_request_id) ON public.leave_request TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, leave_policy_id, start_date, end_date, status, approval_request_id, created_at, updated_at) ON public.leave_request TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, leave_policy_id, start_date, end_date, status, reason_detail, fmla_designation, approval_request_id, created_at, updated_at) ON public.leave_request TO tenant_hr;
GRANT INSERT (employee_id, leave_policy_id, start_date, end_date, status, approval_request_id) ON public.leave_request TO tenant_hr;
GRANT UPDATE (employee_id, leave_policy_id, start_date, end_date, status, approval_request_id) ON public.leave_request TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, leave_policy_id, start_date, end_date, status, approval_request_id, created_at, updated_at) ON public.leave_request TO tenant_payroll;
GRANT SELECT (id, tenant_id, employee_id, leave_policy_id, start_date, end_date, status, approval_request_id, created_at, updated_at) ON public.leave_request TO tenant_manager;
GRANT INSERT (employee_id, leave_policy_id, status, approval_request_id) ON public.leave_request TO tenant_manager;
GRANT UPDATE (employee_id, leave_policy_id, status, approval_request_id) ON public.leave_request TO tenant_manager;
GRANT SELECT (id, tenant_id, employee_id, leave_policy_id, start_date, end_date, status, reason_detail, fmla_designation, approval_request_id, created_at, updated_at) ON public.leave_request TO tenant_employee;
GRANT INSERT (employee_id, leave_policy_id, start_date, end_date, status, reason_detail, fmla_designation, approval_request_id) ON public.leave_request TO tenant_employee;
GRANT UPDATE (employee_id, leave_policy_id, start_date, end_date, status, reason_detail, fmla_designation, approval_request_id) ON public.leave_request TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, leave_policy_id, start_date, end_date, status, approval_request_id, created_at, updated_at) ON public.leave_request TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, leave_policy_id, start_date, end_date, status, reason_detail, fmla_designation, approval_request_id, created_at, updated_at) ON public.leave_request TO agent_runtime;
GRANT INSERT (employee_id, leave_policy_id, start_date, end_date, status, approval_request_id) ON public.leave_request TO agent_runtime;
GRANT UPDATE (employee_id, leave_policy_id, start_date, end_date, status, approval_request_id) ON public.leave_request TO agent_runtime;

-- compensation_event
ALTER TABLE public.compensation_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.compensation_event FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.compensation_event
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.compensation_event AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, event_type, cycle_ref, proposed_amount, comp_band_id, out_of_band, proposed_by_user_id, approval_request_id, resulting_record_id, effective_date, created_at, updated_at) ON public.compensation_event TO daydor_ops;
GRANT INSERT (employee_id, event_type, cycle_ref, proposed_amount, comp_band_id, out_of_band, proposed_by_user_id, approval_request_id, resulting_record_id, effective_date) ON public.compensation_event TO daydor_ops;
GRANT UPDATE (employee_id, event_type, cycle_ref, proposed_amount, comp_band_id, out_of_band, proposed_by_user_id, approval_request_id, resulting_record_id, effective_date) ON public.compensation_event TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, event_type, cycle_ref, proposed_amount, comp_band_id, out_of_band, proposed_by_user_id, approval_request_id, resulting_record_id, effective_date, created_at, updated_at) ON public.compensation_event TO tenant_founder;
GRANT INSERT (employee_id, event_type, cycle_ref, proposed_amount, comp_band_id, out_of_band, proposed_by_user_id, approval_request_id, resulting_record_id, effective_date) ON public.compensation_event TO tenant_founder;
GRANT UPDATE (employee_id, event_type, cycle_ref, proposed_amount, comp_band_id, out_of_band, proposed_by_user_id, approval_request_id, resulting_record_id, effective_date) ON public.compensation_event TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, event_type, cycle_ref, proposed_amount, comp_band_id, out_of_band, proposed_by_user_id, approval_request_id, resulting_record_id, effective_date, created_at, updated_at) ON public.compensation_event TO tenant_hr;
GRANT INSERT (employee_id, event_type, cycle_ref, proposed_amount, comp_band_id, out_of_band, proposed_by_user_id, approval_request_id, resulting_record_id, effective_date) ON public.compensation_event TO tenant_hr;
GRANT UPDATE (employee_id, event_type, cycle_ref, proposed_amount, comp_band_id, out_of_band, proposed_by_user_id, approval_request_id, resulting_record_id, effective_date) ON public.compensation_event TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, event_type, cycle_ref, proposed_amount, comp_band_id, out_of_band, proposed_by_user_id, approval_request_id, resulting_record_id, effective_date, created_at, updated_at) ON public.compensation_event TO tenant_payroll;
GRANT SELECT (id, tenant_id, employee_id, event_type, cycle_ref, proposed_amount, comp_band_id, out_of_band, proposed_by_user_id, approval_request_id, resulting_record_id, effective_date, created_at, updated_at) ON public.compensation_event TO tenant_manager;
GRANT INSERT (employee_id, event_type, cycle_ref, comp_band_id, out_of_band, proposed_by_user_id, approval_request_id, resulting_record_id, effective_date) ON public.compensation_event TO tenant_manager;
GRANT UPDATE (employee_id, event_type, cycle_ref, comp_band_id, out_of_band, proposed_by_user_id, approval_request_id, resulting_record_id, effective_date) ON public.compensation_event TO tenant_manager;
GRANT SELECT (id, tenant_id, employee_id, event_type, cycle_ref, proposed_amount, comp_band_id, out_of_band, proposed_by_user_id, approval_request_id, resulting_record_id, effective_date, created_at, updated_at) ON public.compensation_event TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, event_type, cycle_ref, proposed_amount, comp_band_id, out_of_band, proposed_by_user_id, approval_request_id, resulting_record_id, effective_date, created_at, updated_at) ON public.compensation_event TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, event_type, cycle_ref, proposed_amount, comp_band_id, out_of_band, proposed_by_user_id, approval_request_id, resulting_record_id, effective_date, created_at, updated_at) ON public.compensation_event TO agent_runtime;
GRANT INSERT (employee_id, event_type, cycle_ref, proposed_amount, comp_band_id, out_of_band, proposed_by_user_id, approval_request_id, resulting_record_id, effective_date) ON public.compensation_event TO agent_runtime;
GRANT UPDATE (employee_id, event_type, cycle_ref, proposed_amount, comp_band_id, out_of_band, proposed_by_user_id, approval_request_id, resulting_record_id, effective_date) ON public.compensation_event TO agent_runtime;

-- equity_grant
ALTER TABLE public.equity_grant ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.equity_grant FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.equity_grant
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.equity_grant AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, grant_type, shares, strike_price, grant_date, valuation_409a_id, board_approved_at, approval_request_id, created_at, updated_at) ON public.equity_grant TO daydor_ops;
GRANT INSERT (employee_id, grant_type, shares, strike_price, grant_date, valuation_409a_id, board_approved_at, approval_request_id) ON public.equity_grant TO daydor_ops;
GRANT UPDATE (employee_id, grant_type, shares, strike_price, grant_date, valuation_409a_id, board_approved_at, approval_request_id) ON public.equity_grant TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, grant_type, shares, strike_price, grant_date, valuation_409a_id, board_approved_at, approval_request_id, created_at, updated_at) ON public.equity_grant TO tenant_founder;
GRANT INSERT (employee_id, grant_type, shares, strike_price, grant_date, valuation_409a_id, board_approved_at, approval_request_id) ON public.equity_grant TO tenant_founder;
GRANT UPDATE (employee_id, grant_type, shares, strike_price, grant_date, valuation_409a_id, board_approved_at, approval_request_id) ON public.equity_grant TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, grant_type, shares, strike_price, grant_date, valuation_409a_id, board_approved_at, approval_request_id, created_at, updated_at) ON public.equity_grant TO tenant_hr;
GRANT INSERT (employee_id, grant_type, shares, strike_price, grant_date, valuation_409a_id, board_approved_at, approval_request_id) ON public.equity_grant TO tenant_hr;
GRANT UPDATE (employee_id, grant_type, shares, strike_price, grant_date, valuation_409a_id, board_approved_at, approval_request_id) ON public.equity_grant TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, grant_type, shares, strike_price, grant_date, valuation_409a_id, board_approved_at, approval_request_id, created_at, updated_at) ON public.equity_grant TO tenant_payroll;
GRANT SELECT (id, tenant_id, employee_id, grant_type, shares, strike_price, grant_date, valuation_409a_id, board_approved_at, approval_request_id, created_at, updated_at) ON public.equity_grant TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, grant_type, shares, strike_price, grant_date, valuation_409a_id, board_approved_at, approval_request_id, created_at, updated_at) ON public.equity_grant TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, grant_type, shares, strike_price, grant_date, valuation_409a_id, board_approved_at, approval_request_id, created_at, updated_at) ON public.equity_grant TO agent_runtime;
GRANT INSERT (employee_id, grant_type, shares, strike_price, grant_date, valuation_409a_id, board_approved_at, approval_request_id) ON public.equity_grant TO agent_runtime;
GRANT UPDATE (employee_id, grant_type, shares, strike_price, grant_date, valuation_409a_id, board_approved_at, approval_request_id) ON public.equity_grant TO agent_runtime;

-- vesting_event
ALTER TABLE public.vesting_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vesting_event FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.vesting_event
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, equity_grant_id, vest_date, shares_vested, status, created_at, updated_at) ON public.vesting_event TO daydor_ops;
GRANT INSERT (equity_grant_id, vest_date, shares_vested, status) ON public.vesting_event TO daydor_ops;
GRANT UPDATE (equity_grant_id, vest_date, shares_vested, status) ON public.vesting_event TO daydor_ops;
GRANT SELECT (id, tenant_id, equity_grant_id, vest_date, shares_vested, status, created_at, updated_at) ON public.vesting_event TO tenant_founder;
GRANT INSERT (equity_grant_id, vest_date, shares_vested, status) ON public.vesting_event TO tenant_founder;
GRANT UPDATE (equity_grant_id, vest_date, shares_vested, status) ON public.vesting_event TO tenant_founder;
GRANT SELECT (id, tenant_id, equity_grant_id, vest_date, shares_vested, status, created_at, updated_at) ON public.vesting_event TO tenant_hr;
GRANT INSERT (equity_grant_id, vest_date, shares_vested, status) ON public.vesting_event TO tenant_hr;
GRANT UPDATE (equity_grant_id, vest_date, shares_vested, status) ON public.vesting_event TO tenant_hr;
GRANT SELECT (id, tenant_id, equity_grant_id, vest_date, shares_vested, status, created_at, updated_at) ON public.vesting_event TO tenant_payroll;
GRANT SELECT (id, tenant_id, equity_grant_id, vest_date, shares_vested, status, created_at, updated_at) ON public.vesting_event TO tenant_employee;
GRANT SELECT (id, tenant_id, equity_grant_id, vest_date, shares_vested, status, created_at, updated_at) ON public.vesting_event TO external_auditor;
GRANT SELECT (id, tenant_id, equity_grant_id, vest_date, shares_vested, status, created_at, updated_at) ON public.vesting_event TO agent_runtime;
GRANT INSERT (equity_grant_id, vest_date, shares_vested, status) ON public.vesting_event TO agent_runtime;
GRANT UPDATE (equity_grant_id, vest_date, shares_vested, status) ON public.vesting_event TO agent_runtime;

-- option_exercise
ALTER TABLE public.option_exercise ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.option_exercise FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.option_exercise
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, equity_grant_id, exercised_at, shares, fmv_at_exercise, tax_withheld, status, created_at, updated_at) ON public.option_exercise TO daydor_ops;
GRANT INSERT (equity_grant_id, exercised_at, shares, fmv_at_exercise, tax_withheld, status) ON public.option_exercise TO daydor_ops;
GRANT UPDATE (equity_grant_id, exercised_at, shares, fmv_at_exercise, tax_withheld, status) ON public.option_exercise TO daydor_ops;
GRANT SELECT (id, tenant_id, equity_grant_id, exercised_at, shares, fmv_at_exercise, tax_withheld, status, created_at, updated_at) ON public.option_exercise TO tenant_founder;
GRANT INSERT (equity_grant_id, exercised_at, shares, fmv_at_exercise, tax_withheld, status) ON public.option_exercise TO tenant_founder;
GRANT UPDATE (equity_grant_id, exercised_at, shares, fmv_at_exercise, tax_withheld, status) ON public.option_exercise TO tenant_founder;
GRANT SELECT (id, tenant_id, equity_grant_id, exercised_at, shares, fmv_at_exercise, tax_withheld, status, created_at, updated_at) ON public.option_exercise TO tenant_hr;
GRANT INSERT (equity_grant_id, exercised_at, shares, fmv_at_exercise, tax_withheld, status) ON public.option_exercise TO tenant_hr;
GRANT UPDATE (equity_grant_id, exercised_at, shares, fmv_at_exercise, tax_withheld, status) ON public.option_exercise TO tenant_hr;
GRANT SELECT (id, tenant_id, equity_grant_id, exercised_at, shares, fmv_at_exercise, tax_withheld, status, created_at, updated_at) ON public.option_exercise TO tenant_payroll;
GRANT SELECT (id, tenant_id, equity_grant_id, exercised_at, shares, fmv_at_exercise, tax_withheld, status, created_at, updated_at) ON public.option_exercise TO tenant_employee;
GRANT SELECT (id, tenant_id, equity_grant_id, exercised_at, shares, fmv_at_exercise, tax_withheld, status, created_at, updated_at) ON public.option_exercise TO external_auditor;
GRANT SELECT (id, tenant_id, equity_grant_id, exercised_at, shares, fmv_at_exercise, tax_withheld, status, created_at, updated_at) ON public.option_exercise TO agent_runtime;
GRANT INSERT (equity_grant_id, exercised_at, shares, fmv_at_exercise, tax_withheld, status) ON public.option_exercise TO agent_runtime;
GRANT UPDATE (equity_grant_id, exercised_at, shares, fmv_at_exercise, tax_withheld, status) ON public.option_exercise TO agent_runtime;

-- valuation_409a
ALTER TABLE public.valuation_409a ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.valuation_409a FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.valuation_409a
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, legal_entity_id, valuation_date, fmv_per_share, provider, expires_on, trigger_event, created_at, updated_at) ON public.valuation_409a TO daydor_ops;
GRANT INSERT (legal_entity_id, valuation_date, fmv_per_share, provider, expires_on, trigger_event) ON public.valuation_409a TO daydor_ops;
GRANT UPDATE (legal_entity_id, valuation_date, fmv_per_share, provider, expires_on, trigger_event) ON public.valuation_409a TO daydor_ops;
GRANT SELECT (id, tenant_id, legal_entity_id, valuation_date, fmv_per_share, provider, expires_on, trigger_event, created_at, updated_at) ON public.valuation_409a TO tenant_founder;
GRANT INSERT (legal_entity_id, valuation_date, fmv_per_share, provider, expires_on, trigger_event) ON public.valuation_409a TO tenant_founder;
GRANT UPDATE (legal_entity_id, valuation_date, fmv_per_share, provider, expires_on, trigger_event) ON public.valuation_409a TO tenant_founder;
GRANT SELECT (id, tenant_id, legal_entity_id, valuation_date, fmv_per_share, provider, expires_on, trigger_event, created_at, updated_at) ON public.valuation_409a TO tenant_hr;
GRANT INSERT (legal_entity_id, valuation_date, fmv_per_share, provider, expires_on, trigger_event) ON public.valuation_409a TO tenant_hr;
GRANT UPDATE (legal_entity_id, valuation_date, fmv_per_share, provider, expires_on, trigger_event) ON public.valuation_409a TO tenant_hr;
GRANT SELECT (id, tenant_id, legal_entity_id, valuation_date, fmv_per_share, provider, expires_on, trigger_event, created_at, updated_at) ON public.valuation_409a TO tenant_payroll;
GRANT SELECT (id, tenant_id, legal_entity_id, valuation_date, fmv_per_share, provider, expires_on, trigger_event, created_at, updated_at) ON public.valuation_409a TO external_auditor;
GRANT SELECT (id, tenant_id, legal_entity_id, valuation_date, fmv_per_share, provider, expires_on, trigger_event, created_at, updated_at) ON public.valuation_409a TO agent_runtime;

-- review_cycle
ALTER TABLE public.review_cycle ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.review_cycle FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.review_cycle
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, name, opens_at, closes_at, calibration_status, created_at, updated_at) ON public.review_cycle TO daydor_ops;
GRANT SELECT (id, tenant_id, name, opens_at, closes_at, calibration_status, created_at, updated_at) ON public.review_cycle TO tenant_founder;
GRANT SELECT (id, tenant_id, name, opens_at, closes_at, calibration_status, created_at, updated_at) ON public.review_cycle TO tenant_hr;
GRANT INSERT (name, opens_at, closes_at, calibration_status) ON public.review_cycle TO tenant_hr;
GRANT UPDATE (name, opens_at, closes_at, calibration_status) ON public.review_cycle TO tenant_hr;
GRANT SELECT (id, tenant_id, name, opens_at, closes_at, calibration_status, created_at, updated_at) ON public.review_cycle TO tenant_manager;
GRANT INSERT (name, opens_at, closes_at, calibration_status) ON public.review_cycle TO tenant_manager;
GRANT UPDATE (name, opens_at, closes_at, calibration_status) ON public.review_cycle TO tenant_manager;
GRANT SELECT (id, tenant_id, name, opens_at, closes_at, calibration_status, created_at, updated_at) ON public.review_cycle TO tenant_employee;
GRANT SELECT (id, tenant_id, name, opens_at, closes_at, calibration_status, created_at, updated_at) ON public.review_cycle TO external_auditor;
GRANT SELECT (id, tenant_id, name, opens_at, closes_at, calibration_status, created_at, updated_at) ON public.review_cycle TO agent_runtime;
GRANT INSERT (name, opens_at, closes_at, calibration_status) ON public.review_cycle TO agent_runtime;
GRANT UPDATE (name, opens_at, closes_at, calibration_status) ON public.review_cycle TO agent_runtime;

-- performance_review
ALTER TABLE public.performance_review ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.performance_review FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.performance_review
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.performance_review AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, review_cycle_id, employee_id, reviewer_employee_id, self_assessment, manager_rating, calibrated_rating, submitted_at, created_at, updated_at) ON public.performance_review TO daydor_ops;
GRANT SELECT (id, tenant_id, review_cycle_id, employee_id, reviewer_employee_id, self_assessment, manager_rating, calibrated_rating, submitted_at, created_at, updated_at) ON public.performance_review TO tenant_founder;
GRANT SELECT (id, tenant_id, review_cycle_id, employee_id, reviewer_employee_id, self_assessment, manager_rating, calibrated_rating, submitted_at, created_at, updated_at) ON public.performance_review TO tenant_hr;
GRANT INSERT (review_cycle_id, employee_id, reviewer_employee_id, self_assessment, manager_rating, calibrated_rating, submitted_at) ON public.performance_review TO tenant_hr;
GRANT UPDATE (review_cycle_id, employee_id, reviewer_employee_id, self_assessment, manager_rating, calibrated_rating, submitted_at) ON public.performance_review TO tenant_hr;
GRANT SELECT (id, tenant_id, review_cycle_id, employee_id, reviewer_employee_id, self_assessment, manager_rating, calibrated_rating, submitted_at, created_at, updated_at) ON public.performance_review TO tenant_manager;
GRANT INSERT (review_cycle_id, employee_id, reviewer_employee_id, submitted_at) ON public.performance_review TO tenant_manager;
GRANT UPDATE (review_cycle_id, employee_id, reviewer_employee_id, submitted_at) ON public.performance_review TO tenant_manager;
GRANT SELECT (id, tenant_id, review_cycle_id, employee_id, reviewer_employee_id, self_assessment, manager_rating, calibrated_rating, submitted_at, created_at, updated_at) ON public.performance_review TO tenant_employee;
GRANT INSERT (review_cycle_id, employee_id, reviewer_employee_id, submitted_at) ON public.performance_review TO tenant_employee;
GRANT UPDATE (review_cycle_id, employee_id, reviewer_employee_id, submitted_at) ON public.performance_review TO tenant_employee;
GRANT SELECT (id, tenant_id, review_cycle_id, employee_id, reviewer_employee_id, self_assessment, manager_rating, calibrated_rating, submitted_at, created_at, updated_at) ON public.performance_review TO external_auditor;
GRANT SELECT (id, tenant_id, review_cycle_id, employee_id, reviewer_employee_id, self_assessment, manager_rating, calibrated_rating, submitted_at, created_at, updated_at) ON public.performance_review TO agent_runtime;

-- pip
ALTER TABLE public.pip ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pip FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.pip
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.pip AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, initiated_by_user_id, plan_document_id, milestones, outcome, started_at, ends_at, created_at, updated_at) ON public.pip TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, initiated_by_user_id, plan_document_id, milestones, outcome, started_at, ends_at, created_at, updated_at) ON public.pip TO tenant_hr;
GRANT INSERT (employee_id, initiated_by_user_id, plan_document_id, milestones, outcome, started_at, ends_at) ON public.pip TO tenant_hr;
GRANT UPDATE (employee_id, initiated_by_user_id, plan_document_id, milestones, outcome, started_at, ends_at) ON public.pip TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, initiated_by_user_id, plan_document_id, milestones, outcome, started_at, ends_at, created_at, updated_at) ON public.pip TO tenant_manager;
GRANT INSERT (employee_id, initiated_by_user_id, plan_document_id, started_at, ends_at) ON public.pip TO tenant_manager;
GRANT UPDATE (employee_id, initiated_by_user_id, plan_document_id, started_at, ends_at) ON public.pip TO tenant_manager;
GRANT SELECT (id, tenant_id, employee_id, initiated_by_user_id, plan_document_id, milestones, outcome, started_at, ends_at, created_at, updated_at) ON public.pip TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, initiated_by_user_id, plan_document_id, milestones, outcome, started_at, ends_at, created_at, updated_at) ON public.pip TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, initiated_by_user_id, plan_document_id, milestones, outcome, started_at, ends_at, created_at, updated_at) ON public.pip TO agent_runtime;
GRANT INSERT (employee_id, initiated_by_user_id, plan_document_id, milestones, outcome, started_at, ends_at) ON public.pip TO agent_runtime;
GRANT UPDATE (employee_id, initiated_by_user_id, plan_document_id, milestones, outcome, started_at, ends_at) ON public.pip TO agent_runtime;

-- course
ALTER TABLE public.course ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.course FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.course
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, title, jurisdiction_rule, is_mandatory, validity_months, created_at, updated_at) ON public.course TO daydor_ops;
GRANT INSERT (title, jurisdiction_rule, is_mandatory, validity_months) ON public.course TO daydor_ops;
GRANT UPDATE (title, jurisdiction_rule, is_mandatory, validity_months) ON public.course TO daydor_ops;
GRANT SELECT (id, tenant_id, title, jurisdiction_rule, is_mandatory, validity_months, created_at, updated_at) ON public.course TO tenant_founder;
GRANT SELECT (id, tenant_id, title, jurisdiction_rule, is_mandatory, validity_months, created_at, updated_at) ON public.course TO tenant_hr;
GRANT INSERT (title, jurisdiction_rule, is_mandatory, validity_months) ON public.course TO tenant_hr;
GRANT UPDATE (title, jurisdiction_rule, is_mandatory, validity_months) ON public.course TO tenant_hr;
GRANT SELECT (id, tenant_id, title, jurisdiction_rule, is_mandatory, validity_months, created_at, updated_at) ON public.course TO tenant_manager;
GRANT SELECT (id, tenant_id, title, jurisdiction_rule, is_mandatory, validity_months, created_at, updated_at) ON public.course TO tenant_employee;
GRANT SELECT (id, tenant_id, title, jurisdiction_rule, is_mandatory, validity_months, created_at, updated_at) ON public.course TO external_auditor;
GRANT SELECT (id, tenant_id, title, jurisdiction_rule, is_mandatory, validity_months, created_at, updated_at) ON public.course TO agent_runtime;

-- training_assignment
ALTER TABLE public.training_assignment ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.training_assignment FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.training_assignment
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.training_assignment AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, course_id, assigned_reason, due_at, completed_at, score, created_at, updated_at) ON public.training_assignment TO daydor_ops;
GRANT INSERT (employee_id, course_id, assigned_reason, due_at, completed_at, score) ON public.training_assignment TO daydor_ops;
GRANT UPDATE (employee_id, course_id, assigned_reason, due_at, completed_at, score) ON public.training_assignment TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, course_id, assigned_reason, due_at, completed_at, score, created_at, updated_at) ON public.training_assignment TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, course_id, assigned_reason, due_at, completed_at, score, created_at, updated_at) ON public.training_assignment TO tenant_hr;
GRANT INSERT (employee_id, course_id, assigned_reason, due_at, completed_at, score) ON public.training_assignment TO tenant_hr;
GRANT UPDATE (employee_id, course_id, assigned_reason, due_at, completed_at, score) ON public.training_assignment TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, course_id, assigned_reason, due_at, completed_at, score, created_at, updated_at) ON public.training_assignment TO tenant_manager;
GRANT SELECT (id, tenant_id, employee_id, course_id, assigned_reason, due_at, completed_at, score, created_at, updated_at) ON public.training_assignment TO tenant_employee;
GRANT INSERT (employee_id, course_id, assigned_reason, due_at, completed_at) ON public.training_assignment TO tenant_employee;
GRANT UPDATE (employee_id, course_id, assigned_reason, due_at, completed_at) ON public.training_assignment TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, course_id, assigned_reason, due_at, completed_at, score, created_at, updated_at) ON public.training_assignment TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, course_id, assigned_reason, due_at, completed_at, score, created_at, updated_at) ON public.training_assignment TO agent_runtime;
GRANT INSERT (employee_id, course_id, assigned_reason, due_at, completed_at, score) ON public.training_assignment TO agent_runtime;
GRANT UPDATE (employee_id, course_id, assigned_reason, due_at, completed_at, score) ON public.training_assignment TO agent_runtime;

-- certification
ALTER TABLE public.certification ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.certification FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.certification
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.certification AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, name, issuer, issued_on, expires_on, role_critical, document_id, created_at, updated_at) ON public.certification TO daydor_ops;
GRANT INSERT (employee_id, name, issuer, issued_on, expires_on, role_critical, document_id) ON public.certification TO daydor_ops;
GRANT UPDATE (employee_id, name, issuer, issued_on, expires_on, role_critical, document_id) ON public.certification TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, name, issuer, issued_on, expires_on, role_critical, document_id, created_at, updated_at) ON public.certification TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, name, issuer, issued_on, expires_on, role_critical, document_id, created_at, updated_at) ON public.certification TO tenant_hr;
GRANT INSERT (employee_id, name, issuer, issued_on, expires_on, role_critical, document_id) ON public.certification TO tenant_hr;
GRANT UPDATE (employee_id, name, issuer, issued_on, expires_on, role_critical, document_id) ON public.certification TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, name, issuer, issued_on, expires_on, role_critical, document_id, created_at, updated_at) ON public.certification TO tenant_manager;
GRANT SELECT (id, tenant_id, employee_id, name, issuer, issued_on, expires_on, role_critical, document_id, created_at, updated_at) ON public.certification TO tenant_employee;
GRANT INSERT (employee_id, name, issuer, issued_on, expires_on, role_critical, document_id) ON public.certification TO tenant_employee;
GRANT UPDATE (employee_id, name, issuer, issued_on, expires_on, role_critical, document_id) ON public.certification TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, name, issuer, issued_on, expires_on, role_critical, document_id, created_at, updated_at) ON public.certification TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, name, issuer, issued_on, expires_on, role_critical, document_id, created_at, updated_at) ON public.certification TO agent_runtime;

-- expense
ALTER TABLE public.expense ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.expense FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.expense
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.expense AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, amount, category, receipt_document_id, policy_flags, approval_request_id, reimbursed_at, gl_journal_entry_id, created_at, updated_at) ON public.expense TO daydor_ops;
GRANT INSERT (employee_id, amount, category, receipt_document_id, policy_flags, approval_request_id, reimbursed_at, gl_journal_entry_id) ON public.expense TO daydor_ops;
GRANT UPDATE (employee_id, amount, category, receipt_document_id, policy_flags, approval_request_id, reimbursed_at, gl_journal_entry_id) ON public.expense TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, amount, category, receipt_document_id, policy_flags, approval_request_id, reimbursed_at, gl_journal_entry_id, created_at, updated_at) ON public.expense TO tenant_founder;
GRANT INSERT (employee_id, amount, category, receipt_document_id, policy_flags, approval_request_id, reimbursed_at, gl_journal_entry_id) ON public.expense TO tenant_founder;
GRANT UPDATE (employee_id, amount, category, receipt_document_id, policy_flags, approval_request_id, reimbursed_at, gl_journal_entry_id) ON public.expense TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, amount, category, receipt_document_id, policy_flags, approval_request_id, reimbursed_at, gl_journal_entry_id, created_at, updated_at) ON public.expense TO tenant_payroll;
GRANT INSERT (employee_id, amount, category, receipt_document_id, policy_flags, approval_request_id, reimbursed_at, gl_journal_entry_id) ON public.expense TO tenant_payroll;
GRANT UPDATE (employee_id, amount, category, receipt_document_id, policy_flags, approval_request_id, reimbursed_at, gl_journal_entry_id) ON public.expense TO tenant_payroll;
GRANT SELECT (id, tenant_id, employee_id, amount, category, receipt_document_id, policy_flags, approval_request_id, reimbursed_at, gl_journal_entry_id, created_at, updated_at) ON public.expense TO tenant_manager;
GRANT SELECT (id, tenant_id, employee_id, amount, category, receipt_document_id, policy_flags, approval_request_id, reimbursed_at, gl_journal_entry_id, created_at, updated_at) ON public.expense TO tenant_employee;
GRANT INSERT (employee_id, category, receipt_document_id, policy_flags, approval_request_id, reimbursed_at, gl_journal_entry_id) ON public.expense TO tenant_employee;
GRANT UPDATE (employee_id, category, receipt_document_id, policy_flags, approval_request_id, reimbursed_at, gl_journal_entry_id) ON public.expense TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, amount, category, receipt_document_id, policy_flags, approval_request_id, reimbursed_at, gl_journal_entry_id, created_at, updated_at) ON public.expense TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, amount, category, receipt_document_id, policy_flags, approval_request_id, reimbursed_at, gl_journal_entry_id, created_at, updated_at) ON public.expense TO agent_runtime;
GRANT INSERT (employee_id, amount, category, receipt_document_id, policy_flags, approval_request_id, reimbursed_at, gl_journal_entry_id) ON public.expense TO agent_runtime;
GRANT UPDATE (employee_id, amount, category, receipt_document_id, policy_flags, approval_request_id, reimbursed_at, gl_journal_entry_id) ON public.expense TO agent_runtime;

-- corporate_card
ALTER TABLE public.corporate_card ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.corporate_card FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.corporate_card
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.corporate_card AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, spend_limit, status, created_at, updated_at) ON public.corporate_card TO daydor_ops;
GRANT INSERT (employee_id, spend_limit, status) ON public.corporate_card TO daydor_ops;
GRANT UPDATE (employee_id, spend_limit, status) ON public.corporate_card TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, spend_limit, status, created_at, updated_at) ON public.corporate_card TO tenant_founder;
GRANT INSERT (employee_id, spend_limit, status) ON public.corporate_card TO tenant_founder;
GRANT UPDATE (employee_id, spend_limit, status) ON public.corporate_card TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, spend_limit, status, created_at, updated_at) ON public.corporate_card TO tenant_payroll;
GRANT INSERT (employee_id, spend_limit, status) ON public.corporate_card TO tenant_payroll;
GRANT UPDATE (employee_id, spend_limit, status) ON public.corporate_card TO tenant_payroll;
GRANT SELECT (id, tenant_id, employee_id, spend_limit, status, created_at, updated_at) ON public.corporate_card TO tenant_manager;
GRANT SELECT (id, tenant_id, employee_id, last4, spend_limit, status, created_at, updated_at) ON public.corporate_card TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, spend_limit, status, created_at, updated_at) ON public.corporate_card TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, last4, spend_limit, status, created_at, updated_at) ON public.corporate_card TO agent_runtime;
GRANT INSERT (employee_id, last4, spend_limit, status) ON public.corporate_card TO agent_runtime;
GRANT UPDATE (employee_id, last4, spend_limit, status) ON public.corporate_card TO agent_runtime;
CREATE VIEW public.corporate_card_masked WITH (security_barrier) AS SELECT
    id,
    tenant_id,
    employee_id,
    (CASE WHEN app.current_app_role() IN ('tenant_employee', 'agent_runtime') THEN last4 WHEN app.current_app_role() IN ('daydor_ops', 'tenant_founder', 'tenant_payroll', 'external_auditor') THEN CASE WHEN last4 IS NULL THEN NULL ELSE '****' || right(last4::text, 4) END ELSE NULL END)::text AS last4,
    spend_limit,
    status,
    created_at,
    updated_at
FROM public.corporate_card;
GRANT SELECT ON public.corporate_card_masked TO daydor_ops, tenant_founder, tenant_payroll, external_auditor;

-- vendor_bill
ALTER TABLE public.vendor_bill ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vendor_bill FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.vendor_bill
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, legal_entity_id, vendor_name, amount, po_ref, match_status, approval_request_id, paid_at, created_at, updated_at) ON public.vendor_bill TO daydor_ops;
GRANT INSERT (legal_entity_id, vendor_name, amount, po_ref, match_status, approval_request_id, paid_at) ON public.vendor_bill TO daydor_ops;
GRANT UPDATE (legal_entity_id, vendor_name, amount, po_ref, match_status, approval_request_id, paid_at) ON public.vendor_bill TO daydor_ops;
GRANT SELECT (id, tenant_id, legal_entity_id, vendor_name, amount, po_ref, match_status, approval_request_id, paid_at, created_at, updated_at) ON public.vendor_bill TO tenant_founder;
GRANT INSERT (legal_entity_id, vendor_name, amount, po_ref, match_status, approval_request_id, paid_at) ON public.vendor_bill TO tenant_founder;
GRANT UPDATE (legal_entity_id, vendor_name, amount, po_ref, match_status, approval_request_id, paid_at) ON public.vendor_bill TO tenant_founder;
GRANT SELECT (id, tenant_id, legal_entity_id, vendor_name, amount, po_ref, match_status, approval_request_id, paid_at, created_at, updated_at) ON public.vendor_bill TO tenant_payroll;
GRANT INSERT (legal_entity_id, vendor_name, amount, po_ref, match_status, approval_request_id, paid_at) ON public.vendor_bill TO tenant_payroll;
GRANT UPDATE (legal_entity_id, vendor_name, amount, po_ref, match_status, approval_request_id, paid_at) ON public.vendor_bill TO tenant_payroll;
GRANT SELECT (id, tenant_id, legal_entity_id, vendor_name, amount, po_ref, match_status, approval_request_id, paid_at, created_at, updated_at) ON public.vendor_bill TO external_auditor;
GRANT SELECT (id, tenant_id, legal_entity_id, vendor_name, amount, po_ref, match_status, approval_request_id, paid_at, created_at, updated_at) ON public.vendor_bill TO agent_runtime;
GRANT INSERT (legal_entity_id, vendor_name, amount, po_ref, match_status, approval_request_id, paid_at) ON public.vendor_bill TO agent_runtime;
GRANT UPDATE (legal_entity_id, vendor_name, amount, po_ref, match_status, approval_request_id, paid_at) ON public.vendor_bill TO agent_runtime;

-- gl_journal_entry
ALTER TABLE public.gl_journal_entry ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gl_journal_entry FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.gl_journal_entry
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, legal_entity_id, source_table, source_id, period, cost_center_code, debit_account, credit_account, amount, posted_at, approval_request_id, created_at, updated_at) ON public.gl_journal_entry TO daydor_ops;
GRANT INSERT (legal_entity_id, source_table, source_id, period, cost_center_code, debit_account, credit_account, amount, posted_at, approval_request_id) ON public.gl_journal_entry TO daydor_ops;
GRANT UPDATE (legal_entity_id, source_table, source_id, period, cost_center_code, debit_account, credit_account, amount, posted_at, approval_request_id) ON public.gl_journal_entry TO daydor_ops;
GRANT SELECT (id, tenant_id, legal_entity_id, source_table, source_id, period, cost_center_code, debit_account, credit_account, amount, posted_at, approval_request_id, created_at, updated_at) ON public.gl_journal_entry TO tenant_founder;
GRANT INSERT (legal_entity_id, source_table, source_id, period, cost_center_code, debit_account, credit_account, amount, posted_at, approval_request_id) ON public.gl_journal_entry TO tenant_founder;
GRANT UPDATE (legal_entity_id, source_table, source_id, period, cost_center_code, debit_account, credit_account, amount, posted_at, approval_request_id) ON public.gl_journal_entry TO tenant_founder;
GRANT SELECT (id, tenant_id, legal_entity_id, source_table, source_id, period, cost_center_code, debit_account, credit_account, amount, posted_at, approval_request_id, created_at, updated_at) ON public.gl_journal_entry TO tenant_payroll;
GRANT INSERT (legal_entity_id, source_table, source_id, period, cost_center_code, debit_account, credit_account, posted_at, approval_request_id) ON public.gl_journal_entry TO tenant_payroll;
GRANT UPDATE (legal_entity_id, source_table, source_id, period, cost_center_code, debit_account, credit_account, posted_at, approval_request_id) ON public.gl_journal_entry TO tenant_payroll;
GRANT SELECT (id, tenant_id, legal_entity_id, source_table, source_id, period, cost_center_code, debit_account, credit_account, amount, posted_at, approval_request_id, created_at, updated_at) ON public.gl_journal_entry TO external_auditor;
GRANT SELECT (id, tenant_id, legal_entity_id, source_table, source_id, period, cost_center_code, debit_account, credit_account, amount, posted_at, approval_request_id, created_at, updated_at) ON public.gl_journal_entry TO agent_runtime;
GRANT INSERT (legal_entity_id, source_table, source_id, period, cost_center_code, debit_account, credit_account, amount, posted_at, approval_request_id) ON public.gl_journal_entry TO agent_runtime;
GRANT UPDATE (legal_entity_id, source_table, source_id, period, cost_center_code, debit_account, credit_account, amount, posted_at, approval_request_id) ON public.gl_journal_entry TO agent_runtime;

-- er_case
ALTER TABLE public.er_case ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.er_case FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.er_case
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.er_case AS RESTRICTIVE
    USING (app.can_see_employee(complainant_employee_id))
    WITH CHECK (app.can_see_employee(complainant_employee_id));
GRANT SELECT (id, tenant_id, complainant_employee_id, subject_employee_id, category, status, intake_at, assigned_investigator_user_id, outcome, legal_hold_id, approval_request_id, created_at, updated_at) ON public.er_case TO tenant_hr;
GRANT INSERT (complainant_employee_id, subject_employee_id, status, intake_at, assigned_investigator_user_id, legal_hold_id, approval_request_id) ON public.er_case TO tenant_hr;
GRANT UPDATE (complainant_employee_id, subject_employee_id, status, intake_at, assigned_investigator_user_id, legal_hold_id, approval_request_id) ON public.er_case TO tenant_hr;
GRANT SELECT (id, tenant_id, complainant_employee_id, subject_employee_id, status, intake_at, assigned_investigator_user_id, legal_hold_id, approval_request_id, created_at, updated_at) ON public.er_case TO external_auditor;
GRANT SELECT (id, tenant_id, complainant_employee_id, subject_employee_id, status, intake_at, assigned_investigator_user_id, legal_hold_id, approval_request_id, created_at, updated_at) ON public.er_case TO agent_runtime;
GRANT INSERT (complainant_employee_id, subject_employee_id, status, intake_at, assigned_investigator_user_id, legal_hold_id, approval_request_id) ON public.er_case TO agent_runtime;
GRANT UPDATE (complainant_employee_id, subject_employee_id, status, intake_at, assigned_investigator_user_id, legal_hold_id, approval_request_id) ON public.er_case TO agent_runtime;
CREATE VIEW public.er_case_masked WITH (security_barrier) AS SELECT
    id,
    tenant_id,
    complainant_employee_id,
    subject_employee_id,
    (CASE WHEN app.current_app_role() IN ('tenant_hr') THEN category WHEN app.current_app_role() IN ('tenant_employee') THEN NULL ELSE NULL END)::text AS category,
    status,
    intake_at,
    assigned_investigator_user_id,
    (CASE WHEN app.current_app_role() IN ('tenant_hr') THEN outcome WHEN app.current_app_role() IN ('tenant_employee') THEN NULL ELSE NULL END)::text AS outcome,
    legal_hold_id,
    approval_request_id,
    created_at,
    updated_at
FROM public.er_case;
GRANT SELECT ON public.er_case_masked TO tenant_founder, tenant_employee;

-- er_case_note
ALTER TABLE public.er_case_note ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.er_case_note FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.er_case_note
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT (id, tenant_id, er_case_id, author_user_id, visibility, created_at) ON public.er_case_note TO tenant_hr;
GRANT INSERT (er_case_id, author_user_id, visibility) ON public.er_case_note TO tenant_hr;

-- termination
ALTER TABLE public.termination ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.termination FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.termination
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.termination AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, termination_type, reason_code, notice_date, last_working_day, initiated_by_user_id, rehire_eligible, exit_interview_at, approval_request_id, created_at, updated_at) ON public.termination TO daydor_ops;
GRANT INSERT (employee_id, termination_type, reason_code, notice_date, last_working_day, initiated_by_user_id, rehire_eligible, exit_interview_at, approval_request_id) ON public.termination TO daydor_ops;
GRANT UPDATE (employee_id, termination_type, reason_code, notice_date, last_working_day, initiated_by_user_id, rehire_eligible, exit_interview_at, approval_request_id) ON public.termination TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, termination_type, reason_code, notice_date, last_working_day, initiated_by_user_id, rehire_eligible, exit_interview_at, approval_request_id, created_at, updated_at) ON public.termination TO tenant_founder;
GRANT INSERT (employee_id, termination_type, reason_code, notice_date, last_working_day, initiated_by_user_id, rehire_eligible, exit_interview_at, approval_request_id) ON public.termination TO tenant_founder;
GRANT UPDATE (employee_id, termination_type, reason_code, notice_date, last_working_day, initiated_by_user_id, rehire_eligible, exit_interview_at, approval_request_id) ON public.termination TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, termination_type, reason_code, notice_date, last_working_day, initiated_by_user_id, rehire_eligible, exit_interview_at, approval_request_id, created_at, updated_at) ON public.termination TO tenant_hr;
GRANT INSERT (employee_id, termination_type, reason_code, notice_date, last_working_day, initiated_by_user_id, rehire_eligible, exit_interview_at, approval_request_id) ON public.termination TO tenant_hr;
GRANT UPDATE (employee_id, termination_type, reason_code, notice_date, last_working_day, initiated_by_user_id, rehire_eligible, exit_interview_at, approval_request_id) ON public.termination TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, termination_type, reason_code, notice_date, last_working_day, initiated_by_user_id, rehire_eligible, exit_interview_at, approval_request_id, created_at, updated_at) ON public.termination TO tenant_payroll;
GRANT SELECT (id, tenant_id, employee_id, notice_date, last_working_day, initiated_by_user_id, exit_interview_at, approval_request_id, created_at, updated_at) ON public.termination TO tenant_it;
GRANT SELECT (id, tenant_id, employee_id, termination_type, reason_code, notice_date, last_working_day, initiated_by_user_id, rehire_eligible, exit_interview_at, approval_request_id, created_at, updated_at) ON public.termination TO tenant_manager;
GRANT SELECT (id, tenant_id, employee_id, termination_type, reason_code, notice_date, last_working_day, initiated_by_user_id, rehire_eligible, exit_interview_at, approval_request_id, created_at, updated_at) ON public.termination TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, termination_type, reason_code, notice_date, last_working_day, initiated_by_user_id, rehire_eligible, exit_interview_at, approval_request_id, created_at, updated_at) ON public.termination TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, termination_type, reason_code, notice_date, last_working_day, initiated_by_user_id, rehire_eligible, exit_interview_at, approval_request_id, created_at, updated_at) ON public.termination TO agent_runtime;
GRANT INSERT (employee_id, termination_type, reason_code, notice_date, last_working_day, initiated_by_user_id, rehire_eligible, exit_interview_at, approval_request_id) ON public.termination TO agent_runtime;
GRANT UPDATE (employee_id, termination_type, reason_code, notice_date, last_working_day, initiated_by_user_id, rehire_eligible, exit_interview_at, approval_request_id) ON public.termination TO agent_runtime;

-- final_settlement
ALTER TABLE public.final_settlement ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.final_settlement FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.final_settlement
    USING (tenant_id = app.tenant_id())
    WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY person_scope ON public.final_settlement AS RESTRICTIVE
    USING (app.can_see_employee(employee_id))
    WITH CHECK (app.can_see_employee(employee_id));
GRANT SELECT (id, tenant_id, employee_id, termination_id, pending_wages, gratuity_payout, leave_encashment, recoveries, total_settlement, approval_request_id, disbursed_at, created_at, updated_at) ON public.final_settlement TO daydor_ops;
GRANT INSERT (employee_id, termination_id, pending_wages, gratuity_payout, leave_encashment, recoveries, approval_request_id, disbursed_at) ON public.final_settlement TO daydor_ops;
GRANT UPDATE (employee_id, termination_id, pending_wages, gratuity_payout, leave_encashment, recoveries, approval_request_id, disbursed_at) ON public.final_settlement TO daydor_ops;
GRANT SELECT (id, tenant_id, employee_id, termination_id, pending_wages, gratuity_payout, leave_encashment, recoveries, total_settlement, approval_request_id, disbursed_at, created_at, updated_at) ON public.final_settlement TO tenant_founder;
GRANT INSERT (employee_id, termination_id, pending_wages, gratuity_payout, leave_encashment, recoveries, approval_request_id, disbursed_at) ON public.final_settlement TO tenant_founder;
GRANT UPDATE (employee_id, termination_id, pending_wages, gratuity_payout, leave_encashment, recoveries, approval_request_id, disbursed_at) ON public.final_settlement TO tenant_founder;
GRANT SELECT (id, tenant_id, employee_id, termination_id, pending_wages, gratuity_payout, leave_encashment, recoveries, total_settlement, approval_request_id, disbursed_at, created_at, updated_at) ON public.final_settlement TO tenant_hr;
GRANT SELECT (id, tenant_id, employee_id, termination_id, pending_wages, gratuity_payout, leave_encashment, recoveries, total_settlement, approval_request_id, disbursed_at, created_at, updated_at) ON public.final_settlement TO tenant_payroll;
GRANT INSERT (employee_id, termination_id, pending_wages, gratuity_payout, leave_encashment, recoveries, approval_request_id, disbursed_at) ON public.final_settlement TO tenant_payroll;
GRANT UPDATE (employee_id, termination_id, pending_wages, gratuity_payout, leave_encashment, recoveries, approval_request_id, disbursed_at) ON public.final_settlement TO tenant_payroll;
GRANT SELECT (id, tenant_id, employee_id, termination_id, pending_wages, gratuity_payout, leave_encashment, recoveries, total_settlement, approval_request_id, disbursed_at, created_at, updated_at) ON public.final_settlement TO tenant_employee;
GRANT SELECT (id, tenant_id, employee_id, termination_id, pending_wages, gratuity_payout, leave_encashment, recoveries, total_settlement, approval_request_id, disbursed_at, created_at, updated_at) ON public.final_settlement TO external_auditor;
GRANT SELECT (id, tenant_id, employee_id, termination_id, pending_wages, gratuity_payout, leave_encashment, recoveries, total_settlement, approval_request_id, disbursed_at, created_at, updated_at) ON public.final_settlement TO agent_runtime;
GRANT INSERT (employee_id, termination_id, pending_wages, gratuity_payout, leave_encashment, recoveries, approval_request_id, disbursed_at) ON public.final_settlement TO agent_runtime;
GRANT UPDATE (employee_id, termination_id, pending_wages, gratuity_payout, leave_encashment, recoveries, approval_request_id, disbursed_at) ON public.final_settlement TO agent_runtime;
