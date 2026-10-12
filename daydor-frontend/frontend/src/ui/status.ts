import { gateLabel, roleName } from '../contract'

export interface StatusInput {
  gate_type: string
  status: 'pending' | 'approved' | 'rejected' | 'expired'
  created_at: string
  resolved_at: string | null
  decision_note: string | null
  allowed_roles: string[]
}

const day = (iso: string) => new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })
const join = (roles: string[]) => roles.map(roleName).join(' or ') || 'an approver'

/** One plain sentence about where an approval stands. This is all a role without workflow access
 *  gets, so it must stand on its own. */
export function describeApproval(a: StatusInput): string {
  const gate = gateLabel(a.gate_type)
  switch (a.status) {
    case 'pending': return `Waiting for ${join(a.allowed_roles)} to decide: ${gate}. Raised ${day(a.created_at)}.`
    case 'approved': return `Approved${a.resolved_at ? ` on ${day(a.resolved_at)}` : ''}: ${gate}.${a.decision_note ? ` Note: ${a.decision_note}` : ''}`
    case 'rejected': return `Rejected${a.resolved_at ? ` on ${day(a.resolved_at)}` : ''}: ${gate}.${a.decision_note ? ` Note: ${a.decision_note}` : ''}`
    default: return `Expired without a decision: ${gate}.`
  }
}

export const INSTANCE_STATUS: Record<string, { text: string; tone: 'accent' | 'warn' | 'ok' | 'neutral'; mark: string }> = {
  running: { text: 'In progress', tone: 'accent', mark: '▸' },
  waiting_gate: { text: 'Waiting for approval', tone: 'warn', mark: '◔' },
  completed: { text: 'Completed', tone: 'ok', mark: '✓' },
  cancelled: { text: 'Stopped', tone: 'neutral', mark: '–' },
}

export const DECISION_TEXT: Record<string, string> = { pass: 'Looks fine', escalate: 'Needs a person', error: 'Could not run' }
