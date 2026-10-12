import { Badge, type Tone } from '../ui'
import type { RequisitionStage } from '../api/types'

export const shortDate = (v: unknown) => (v ? new Date(String(v)).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '')
export const dateTime = (v: unknown) => (v ? new Date(String(v)).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' }) : '')

const STAGES: Record<RequisitionStage, { text: string; tone: Tone; mark: string }> = {
  drafting: { text: 'Drafting', tone: 'neutral', mark: '·' },
  awaiting_budget_approval: { text: 'Waiting for budget approval', tone: 'warn', mark: '◔' },
  budget_rejected: { text: 'Budget rejected', tone: 'danger', mark: '✕' },
  approved: { text: 'Approved, posting soon', tone: 'accent', mark: '✓' },
  posted: { text: 'Posted', tone: 'ok', mark: '✓' },
}
export function StageBadge({ stage }: { stage: RequisitionStage }) {
  const s = STAGES[stage]
  return <Badge tone={s.tone} mark={s.mark}>{s.text}</Badge>
}

/** A short readable reference for an id someone may need to quote. */
export const shortId = (id: string) => id.slice(0, 8)
