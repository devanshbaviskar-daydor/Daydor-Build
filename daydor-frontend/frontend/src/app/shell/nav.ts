import { canReadTable, canWriteTable } from '../../contract'

export interface NavItem { to: string; label: string }
export interface Caps { workflow_timeline: boolean; directory: boolean }

/** What this role can open today. Each entry is decided by the contract (the backend's access
 *  levels) or by a capability the API reports, never by a role list typed here. */
export function navFor(role: string, caps: Caps = { workflow_timeline: false, directory: false }, hasEmployee = false): { ready: NavItem[]; soon: string[] } {
  const ready: NavItem[] = [{ to: '/', label: 'Overview' }]
  if (canReadTable('approval_request', role)) ready.push({ to: '/approvals', label: 'Approvals' })
  if (caps.workflow_timeline) ready.push({ to: '/workflows', label: 'Workflows' })
  if (canReadTable('position', role)) ready.push({ to: '/positions', label: 'Positions' })
  if (canReadTable('job_requisition', role)) ready.push({ to: '/requisitions', label: 'Requisitions' })
  if (caps.directory) ready.push({ to: '/people', label: 'People' })
  if (canReadTable('checklist', role)) ready.push({ to: '/onboarding', label: 'Onboarding' })
  if (canReadTable('work_authorization', role)) ready.push({ to: '/work-authorization', label: 'Work authorization' })
  if (hasEmployee && canWriteTable('consent_record', role)) ready.push({ to: '/my/privacy', label: 'My privacy' })
  if (['job_profile', 'comp_band', 'access_role_template', 'skill', 'leave_policy', 'benefit_plan', 'statutory_rate_rule'].some((t) => canWriteTable(t as never, role))) ready.push({ to: '/reference-data', label: 'Reference data' })
  if ((hasEmployee && canWriteTable('time_punch', role)) || canReadTable('timecard', role)) ready.push({ to: '/time', label: 'Time and leave' })
  if (canReadTable('payroll_run', role)) ready.push({ to: '/payroll', label: 'Payroll' })
  if (canReadTable('termination', role)) ready.push({ to: '/exit', label: 'Exit' })
  const soon: string[] = []
  return { ready, soon }
}
