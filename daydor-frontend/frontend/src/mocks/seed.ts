// Sample data for Acme Technologies (Bengaluru, with one US employee). It follows the real model's
// tables and columns, and it is arranged so every Hire screen has something to show: a hire waiting on
// its budget, one waiting on an out-of-band offer, and one finished, with the onboarding data behind it.
export type Row = Record<string, unknown>
export const T = 'tenant-acme'
const H = 3_600_000
export const ago = (ms: number) => new Date(Date.now() - ms).toISOString()
const day = (d: number) => new Date(Date.now() + d * 86_400_000).toISOString().slice(0, 10)
const r = (id: string, extra: Row, age = 30 * 24 * H): Row => ({ id, tenant_id: T, created_at: ago(age), updated_at: ago(age), ...extra })

/** Who reports to whom, for the manager's row scope. */
export const REPORTS: Record<string, string[]> = { 'e-meera': ['e-arjun', 'e-isha'] }

export function seedTables(): Record<string, Row[]> {
  const emp = (id: string, name: string, email: string, dept: string, loc: string, pos: string | null, state: string, joined: string, extra: Row = {}) => r(id, {
    hire_event_id: `evt-${id}`, full_name: name, work_email: email, employment_type: 'full_time', legal_entity_id: 'le-1', department_id: dept,
    location_id: loc, position_id: pos, state_code: state, date_of_joining: joined, date_of_exit: null, is_active: true,
    date_of_birth: '1992-04-12', personal_address: 'Bengaluru', aadhaar_last4: loc === 'loc-blr' ? '4821' : null, ...extra,
  })
  const pos = (id: string, dept: string, profile: string, status: string, holder: string | null) => r(id, {
    department_id: dept, job_profile_id: profile, status, budgeted_fte: 1, budgeted_cost: 2400000, current_employee_id: holder, opened_at: '2026-09-01', closed_at: null })
  return {
    department: [r('dept-eng', { name: 'Engineering', parent_department_id: null, head_employee_id: 'e-meera', cost_center_code: 'CC-100' }),
      r('dept-sales', { name: 'Sales', parent_department_id: null, head_employee_id: null, cost_center_code: 'CC-200' }),
      r('dept-people', { name: 'People Operations', parent_department_id: null, head_employee_id: null, cost_center_code: 'CC-300' })],
    location: [r('loc-blr', { name: 'Bengaluru', country_code: 'IN', state_code: 'KA', is_remote: false, legal_entity_id: 'le-1' }),
      r('loc-aus', { name: 'Austin', country_code: 'US', state_code: 'TX', is_remote: false, legal_entity_id: 'le-1' })],
    job_profile: [
      r('jp-1', { title: 'Backend Engineer', job_family: 'Engineering', level: 'L3', flsa_default: 'exempt', description: 'Builds and runs backend services' }),
      r('jp-2', { title: 'Account Executive', job_family: 'Sales', level: 'L2', flsa_default: 'exempt', description: 'Owns customer deals' }),
      r('jp-3', { title: 'People Partner', job_family: 'People', level: 'L3', flsa_default: 'exempt', description: 'Supports managers and employees' })],
    comp_band: [
      r('cb-1', { job_profile_id: 'jp-1', location_id: null, currency: 'INR', band_min: 1800000, band_mid: 2400000, band_max: 3000000, effective_from: '2026-01-01', effective_to: null }),
      r('cb-2', { job_profile_id: 'jp-2', location_id: null, currency: 'INR', band_min: 1200000, band_mid: 1600000, band_max: 2000000, effective_from: '2026-01-01', effective_to: null })],
    access_role_template: [r('art-1', { job_profile_id: 'jp-1', department_id: 'dept-eng', app_bundle: { apps: ['Email', 'Source control', 'Issue tracker'] } })],
    skill: [r('sk-1', { name: 'Go', category: 'Backend' }), r('sk-2', { name: 'PostgreSQL', category: 'Data' }), r('sk-3', { name: 'Recruiting', category: 'People' }), r('sk-4', { name: 'Negotiation', category: 'Sales' })],
    position: [pos('pos-1', 'dept-eng', 'jp-1', 'open', null), pos('pos-2', 'dept-eng', 'jp-1', 'open', null), pos('pos-3', 'dept-sales', 'jp-2', 'open', null),
      pos('pos-4', 'dept-eng', 'jp-1', 'filled', 'e-meera'), pos('pos-5', 'dept-people', 'jp-3', 'filled', 'e-isha')],
    employee: [
      emp('e-meera', 'Meera Iyer', 'meera.iyer@acme.test', 'dept-eng', 'loc-blr', 'pos-4', 'KA', '2025-04-01'),
      emp('e-arjun', 'Arjun Rao', 'arjun.rao@acme.test', 'dept-eng', 'loc-blr', null, 'KA', '2025-06-16'),
      emp('e-isha', 'Isha Nair', 'isha.nair@acme.test', 'dept-people', 'loc-blr', 'pos-5', 'KA', day(1)),
      emp('e-john', 'John Carter', 'john.carter@acme.test', 'dept-sales', 'loc-aus', null, 'TX', '2026-09-15', { date_of_birth: '1989-08-03', personal_address: 'Austin, TX', aadhaar_last4: null }),
    ],
    employment_record: [
      r('er-1', { employee_id: 'e-isha', effective_from: day(1), effective_to: null, job_profile_id: 'jp-3', comp_band_id: null, fte: 1, ctc_annual: 1440000, basic_da_monthly: 49000, other_allowances_json: {}, wage_floor_compliant: true, tax_regime_election: 'new', flsa_status: null }),
      r('er-2', { employee_id: 'e-meera', effective_from: '2025-04-01', effective_to: null, job_profile_id: 'jp-1', comp_band_id: 'cb-1', fte: 1, ctc_annual: 2800000, basic_da_monthly: 95000, other_allowances_json: {}, wage_floor_compliant: true, tax_regime_election: 'old', flsa_status: null }),
      r('er-3', { employee_id: 'e-john', effective_from: '2026-09-15', effective_to: null, job_profile_id: 'jp-2', comp_band_id: 'cb-2', fte: 1, ctc_annual: 1800000, basic_da_monthly: 0, other_allowances_json: {}, wage_floor_compliant: null, tax_regime_election: null, flsa_status: 'exempt' })],
    job_requisition: [
      r('req-1', { position_id: 'pos-1', hiring_manager_id: 'e-meera', status: 'draft', target_start_date: day(60), approval_request_id: 'ap-1' }, 2 * H),
      r('req-3', { position_id: 'pos-3', hiring_manager_id: 'e-meera', status: 'draft', target_start_date: day(45), approval_request_id: 'ap-9' }, 9 * 24 * H),
      r('req-4', { position_id: 'pos-5', hiring_manager_id: 'e-meera', status: 'draft', target_start_date: day(1), approval_request_id: 'ap-11' }, 40 * 24 * H)],
    job_posting: [
      r('post-3', { requisition_id: 'req-3', channel: 'company_site', pay_range_min: 1200000, pay_range_max: 2000000, pay_transparency_checked: true, posted_at: ago(8 * 24 * H), closed_at: null }),
      r('post-4', { requisition_id: 'req-4', channel: 'company_site', pay_range_min: 1300000, pay_range_max: 1700000, pay_transparency_checked: true, posted_at: ago(38 * 24 * H), closed_at: ago(25 * 24 * H) })],
    candidate: [
      r('cand-3', { full_name: 'Rahul Verma', email: 'rahul.verma@example.test', phone: '+91 98450 22222', resume_ref: 'r-3', source: 'referral', retain_until: day(400), converted_employee_id: null }),
      r('cand-4', { full_name: 'Isha Nair', email: 'isha.nair@example.test', phone: '+91 98450 33333', resume_ref: 'r-4', source: 'company_site', retain_until: day(400), converted_employee_id: 'e-isha' })],
    application: [
      r('app-3', { candidate_id: 'cand-3', requisition_id: 'req-3', stage: 'applied', stage_changed_at: ago(6 * 24 * H), rejection_reason_code: null }),
      r('app-4', { candidate_id: 'cand-4', requisition_id: 'req-4', stage: 'hired', stage_changed_at: ago(20 * 24 * H), rejection_reason_code: null })],
    screening_result: [
      r('sr-3', { application_id: 'app-3', aedt_audit_id: null, tool_name: 'placeholder-screener', model_version: '0.1', score: 0.81, recommendation: 'advance', candidate_notified_at: ago(6 * 24 * H), human_reviewer_user_id: 'u-hr', human_override: false }),
      r('sr-4', { application_id: 'app-4', aedt_audit_id: null, tool_name: 'placeholder-screener', model_version: '0.1', score: 0.88, recommendation: 'advance', candidate_notified_at: ago(35 * 24 * H), human_reviewer_user_id: 'u-hr', human_override: false })],
    interview: [
      r('int-3', { application_id: 'app-3', interviewer_employee_id: 'e-meera', scheduled_at: ago(4 * 24 * H), scorecard: { overall: 'strong' }, recommendation: 'hire' }),
      r('int-4', { application_id: 'app-4', interviewer_employee_id: 'e-meera', scheduled_at: ago(30 * 24 * H), scorecard: { overall: 'strong' }, recommendation: 'hire' })],
    offer: [
      r('off-3', { application_id: 'app-3', comp_band_id: 'cb-2', proposed_base: 2800000, proposed_equity: null, within_band: false, approval_request_id: 'ap-2', offer_document_id: null, sent_at: null, accepted_at: null }),
      r('off-4', { application_id: 'app-4', comp_band_id: null, proposed_base: 1440000, proposed_equity: null, within_band: true, approval_request_id: null, offer_document_id: 'doc-1', sent_at: ago(22 * 24 * H), accepted_at: ago(20 * 24 * H) })],
    background_check: [r('bg-4', { candidate_id: 'cand-4', vendor: 'Test vendor', ordered_at: ago(19 * 24 * H), status: 'clear', findings_summary: 'No adverse findings', adverse_action_stage: null, pre_adverse_notice_at: null })],
    consent_record: [
      r('cr-1', { employee_id: 'e-isha', data_category: 'pan', purpose: 'identity_verification', status: 'granted', granted_at: ago(18 * 24 * H), withdrawn_at: null, consent_artifact_ref: 'web-form-1' }),
      r('cr-2', { employee_id: 'e-isha', data_category: 'aadhaar', purpose: 'identity_verification', status: 'granted', granted_at: ago(18 * 24 * H), withdrawn_at: null, consent_artifact_ref: 'web-form-1' }),
      r('cr-3', { employee_id: 'e-john', data_category: 'ssn', purpose: 'identity_verification', status: 'granted', granted_at: ago(50 * 24 * H), withdrawn_at: null, consent_artifact_ref: 'web-form-2' })],
    document: [
      r('doc-1', { subject_type: 'employee', subject_id: 'e-isha', document_class: 'offer_letter', storage_ref: 'vault://doc-1', retention_class: 'rp-1', consent_record_id: null, signed_at: ago(20 * 24 * H) }),
      r('doc-2', { subject_type: 'employee', subject_id: 'e-isha', document_class: 'identity_proof', storage_ref: 'vault://doc-2', retention_class: 'rp-1', consent_record_id: 'cr-2', signed_at: null })],
    checklist: [r('ck-1', { employee_id: 'e-isha', kind: 'onboarding', template_key: 'onboarding-in', status: 'in_progress', due_date: day(1) })],
    checklist_task: [
      r('tk-1', { checklist_id: 'ck-1', owner_domain: 'hr', assignee_user_id: 'u-hr', title: 'Collect identity documents', status: 'done', due_at: ago(5 * 24 * H), completed_at: ago(6 * 24 * H), blocking: true }),
      r('tk-2', { checklist_id: 'ck-1', owner_domain: 'it', assignee_user_id: 'u-it', title: 'Create the single sign-on account', status: 'done', due_at: ago(2 * 24 * H), completed_at: ago(3 * 24 * H), blocking: true }),
      r('tk-3', { checklist_id: 'ck-1', owner_domain: 'it', assignee_user_id: 'u-it', title: 'Prepare a laptop', status: 'open', due_at: new Date(Date.now() + 24 * H).toISOString(), completed_at: null, blocking: true }),
      r('tk-4', { checklist_id: 'ck-1', owner_domain: 'payroll', assignee_user_id: 'u-payroll', title: 'Add to the first payroll run', status: 'open', due_at: new Date(Date.now() + 6 * 24 * H).toISOString(), completed_at: null, blocking: false })],
    identity_account: [r('ia-1', { employee_id: 'e-isha', directory_provider: 'test-idp', external_id: 'isha.nair', status: 'active', provisioned_at: ago(3 * 24 * H), deprovisioned_at: null, approval_request_id: null })],
    app_access_grant: [
      r('g-1', { identity_account_id: 'ia-1', app_name: 'Email', permission_level: 'member', source: 'template', template_id: 'art-1', approval_request_id: null, granted_at: ago(3 * 24 * H), revoked_at: null }),
      r('g-2', { identity_account_id: 'ia-1', app_name: 'Issue tracker', permission_level: 'member', source: 'template', template_id: 'art-1', approval_request_id: null, granted_at: ago(3 * 24 * H), revoked_at: null }),
      r('grant-1', { identity_account_id: 'ia-1', app_name: 'Production database', permission_level: 'read', source: 'request', template_id: null, approval_request_id: 'ap-5', granted_at: ago(0.7 * H), revoked_at: null })],
    payroll_profile: [
      r('pp-1', { employee_id: 'e-isha', pay_frequency: 'monthly', payment_method: 'bank_transfer', work_state: 'KA', tax_state: null, reciprocity_agreement_flag: null, state_registration_status: null, w4_elections: null, uan_number: '101234567890', esic_ip_number: '3100012345' }),
      r('pp-2', { employee_id: 'e-john', pay_frequency: 'biweekly', payment_method: 'direct_deposit', work_state: 'TX', tax_state: 'TX', reciprocity_agreement_flag: false, state_registration_status: 'registered', w4_elections: { filing_status: 'single', allowances: 1 }, uan_number: null, esic_ip_number: null })],
    payslip: [r('ps-1', { payroll_run_id: 'run-1', employee_id: 'e-isha', employment_record_id: 'er-1', gross_pay: 98000, net_pay: 86400, tax_withheld: 5520, issued_at: ago(0.5 * H), retention_class: 'rp-1' })],
    payslip_line: [
      r('pl-1', { payslip_id: 'ps-1', component_code: 'Basic', amount: 49000, rule_id: null }), r('pl-2', { payslip_id: 'ps-1', component_code: 'House rent allowance', amount: 24500, rule_id: null }),
      r('pl-3', { payslip_id: 'ps-1', component_code: 'Special allowance', amount: 24500, rule_id: null }), r('pl-4', { payslip_id: 'ps-1', component_code: 'Provident fund', amount: -5880, rule_id: null }),
      r('pl-5', { payslip_id: 'ps-1', component_code: 'Professional tax', amount: -200, rule_id: null }), r('pl-6', { payslip_id: 'ps-1', component_code: 'Income tax', amount: -5520, rule_id: null })],
    emergency_contact: [
      r('ec-1', { employee_id: 'e-isha', contact_name: 'Anil Nair', relationship: 'Father', phone: '+91 98450 44444', priority: 1 }),
      r('ec-2', { employee_id: 'e-arjun', contact_name: 'Lakshmi Rao', relationship: 'Mother', phone: '+91 98450 11111', priority: 1 })],
    employee_skill: [
      r('es-1', { employee_id: 'e-meera', skill_id: 'sk-1', proficiency_level: 4, source: 'manager_rated', last_updated: ago(20 * 24 * H) }),
      r('es-2', { employee_id: 'e-isha', skill_id: 'sk-3', proficiency_level: 3, source: 'manager_rated', last_updated: ago(10 * 24 * H) })],
    work_authorization: [r('wa-1', { employee_id: 'e-john', auth_type: 'H-1B', status: 'active', i9_section2_completed_at: ago(25 * 24 * H), everify_case_no: 'EV-2026-0042', everify_status: 'authorized', expiration_date: '2027-03-31', sponsor_flag: true, renewal_case_status: 'not_started', next_action_due: day(3) })],
  }
}
