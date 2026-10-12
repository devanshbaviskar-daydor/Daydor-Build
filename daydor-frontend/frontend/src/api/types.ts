export interface Session {
  id: string; email: string; display_name: string
  role: string; role_letter: string; role_label: string
  tenant_id: string | null; tenant_name: string | null
  user_id: string | null; employee_id: string | null
  capabilities: { workflow_timeline: boolean; directory: boolean }
}
export interface Approval {
  id: string; gate_type: string; gate_label: string
  subject_table: string; subject_id: string
  required_approver_role: string | null
  status: 'pending' | 'approved' | 'rejected' | 'expired'
  requested_by_user_id: string | null; resolved_by_user_id: string | null
  resolved_at: string | null; deadline_at: string | null; decision_note: string | null; created_at: string
  allowed_roles: string[]; requested_by_me: boolean; can_resolve: boolean
  /** Only present for roles that may read workflow tables, and only when a workflow exists. */
  workflow_instance_id?: string | null
}
export interface WorkflowInstance {
  id: string; definition_name: string; definition_version: number
  subject_table: string; subject_id: string; state: string
  status: 'running' | 'waiting_gate' | 'completed' | 'cancelled'
  waiting_on_approval: string | null; context: Record<string, unknown>; context_hidden_keys: string[]
  version: number; created_at: string; updated_at: string
}
export interface WorkflowTransitionRow {
  id: number | string; event: string; from_state: string; to_state: string; outcome: string
  approval_request_id: string | null; created_at: string
}
export interface TableRows { table: string; columns: string[]; rows: Record<string, unknown>[]; total: number; limit: number; offset: number }
export interface AuditEntry { id: string; at: string; kind: string; actor: string; action: string }
export interface AuditTrail { table: string; subject_id: string; entries: AuditEntry[]; sources: { approvals: boolean; workflow: boolean; audit_log: boolean } }
export interface Evaluation {
  id: string; gate_id: string; gate_label: string; subject_table: string; subject_id: string
  engine: string; engine_version: string | null; confidence: number | string | null; threshold: number | string
  model_decision: 'pass' | 'escalate' | 'error'; effective_decision: 'pass' | 'escalate'; mode: 'shadow' | 'enforce'
  error: string | null; approval_request_id: string | null; created_at: string
}

export interface ApprovalBrief { id: string; status: 'pending' | 'approved' | 'rejected' | 'expired'; gate_type: string }
export type RequisitionStage = 'drafting' | 'awaiting_budget_approval' | 'budget_rejected' | 'approved' | 'posted'
export interface RequisitionSummary {
  id: string; status: string; target_start_date: string; position_id: string; hiring_manager_id: string
  hiring_manager_name: string | null; job_title: string | null; department_name: string | null
  stage: RequisitionStage; approval: ApprovalBrief | null
  posting: { channel: string; pay_range_min: number | string; pay_range_max: number | string; pay_transparency_checked: boolean; posted_at: string | null } | null
  candidate_count: number; created_at: string
}
export interface PipelineItem {
  application: { id: string; stage: string; stage_changed_at: string; rejection_reason_code: string | null }
  candidate: { id: string; full_name: string; email: string; source: string } | null
  screening: { id: string; score: number | string; recommendation: string; tool_name: string; model_version: string; candidate_notified_at: string | null; human_override: boolean; approval: ApprovalBrief | null } | null
  interview: { id: string; scheduled_at: string; interviewer_employee_id: string; interviewer_name: string | null; recommendation: string | null } | null
  offer: { id: string; proposed_base: number | string; proposed_equity: number | string | null; within_band: boolean; sent_at: string | null; accepted_at: string | null
           band: { currency: string; band_min: number | string; band_mid: number | string; band_max: number | string } | null; approval: ApprovalBrief | null } | null
}
export interface OnboardingBrief { employee_id: string; instance_state: string; instance_status: string; awaiting_consent_request: boolean }
export interface RequisitionDetail { requisition: RequisitionSummary; pipeline: PipelineItem[]; onboarding: OnboardingBrief | null; access: { can_enter_applications: boolean; sees_candidates: boolean } }
export interface DirectoryRow { id: string; full_name: string; work_email: string; department_id: string; location_id: string; position_id: string | null }
export interface StartHireBody {
  position_id: string; hiring_manager_id: string; target_start_date: string; channel: string; pay_range_min: number; pay_range_max: number
  interviewer_employee_id?: string; scheduled_at?: string; comp_band_id?: string; proposed_base?: number; proposed_equity?: number
  // New-hire personal and payroll-setup details. The backend's employee/employment_record/payroll_profile
  // writers (hire flow steps 10, 11, 18) read these from the workflow's own context, which is fixed from
  // whatever rides along at start_hire() time (see docs/integration-notes.md, finding 6) -- a real system
  // would collect these at offer acceptance, but this prototype has no such step.
  legal_entity_id?: string; location_id?: string; state_code?: string; employment_type?: string
  date_of_birth?: string; personal_address?: string; aadhaar_last4?: string
  basic_da_monthly?: number; tax_regime_election?: string; retention_class_id?: string
  pay_frequency?: string; payment_method?: string; work_state?: string; tax_state?: string; uan_number?: string; esic_ip_number?: string
}
export interface ApplicationBody { full_name: string; email: string; phone: string; resume_ref?: string; source?: string }
