import { gate, humanize } from '../contract'
import { Badge, type Tone } from './Badge'
import { ShadowModeBadge } from './ModeBadges'

export type GateStatus = 'pending' | 'approved' | 'rejected' | 'expired' | 'waiting' | 'recorded'
const STATUS: Record<GateStatus, { text: string; tone: Tone; mark: string }> = {
  pending: { text: 'Waiting for approval', tone: 'warn', mark: '◔' },
  waiting: { text: 'Workflow paused here', tone: 'warn', mark: '◔' },
  approved: { text: 'Approved', tone: 'ok', mark: '✓' },
  rejected: { text: 'Rejected', tone: 'danger', mark: '✕' },
  expired: { text: 'Expired', tone: 'neutral', mark: '–' },
  recorded: { text: 'Recorded', tone: 'neutral', mark: '·' },
}

export function GateBadge({ gateId, status, showId = true, mode = 'shadow' }: { gateId: string; status?: GateStatus; showId?: boolean; mode?: 'shadow' | 'enforce' }) {
  const g = gate(gateId)
  const label = g?.label ?? humanize(gateId)
  const soft = g?.kind === 'soft'
  const s = status ? STATUS[status] : null
  return (
    <span className="gate">
      <span>{label}</span>
      {s && <Badge tone={s.tone} mark={s.mark}>{s.text}</Badge>}
      {soft && mode === 'shadow' && <ShadowModeBadge />}
      {showId && <span className="gate-id">{gateId}</span>}
    </span>
  )
}
