import { useState, type ReactNode } from 'react'
import { humanize, roleName } from '../contract'
import { Button } from './Button'
import { GateBadge } from './GateBadge'

export interface ApprovalView {
  id: string; gate_type: string; subject_table: string; subject_id: string
  status: 'pending' | 'approved' | 'rejected' | 'expired'
  created_at: string; resolved_at: string | null; decision_note: string | null
  allowed_roles: string[]; requested_by_me: boolean; can_resolve: boolean
}

/** Why a pending request cannot be resolved by this person, in plain words. */
export function whyNot(a: ApprovalView, myRole: string): string | null {
  if (a.status !== 'pending' || a.can_resolve) return null
  if (a.requested_by_me) return 'You raised this request, so someone else has to approve it.'
  if (!a.allowed_roles.includes(myRole)) return `Waiting for ${a.allowed_roles.map(roleName).join(' or ') || 'an approver'}.`
  return null
}

const when = (iso: string) => new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })

export function ApprovalCard({ approval: a, myRole, busy, error, onResolve, footer }: {
  approval: ApprovalView; myRole: string; busy?: boolean; error?: string | null
  onResolve?: (decision: 'approved' | 'rejected', note: string) => void
  /** Extra content under the status, such as a link to the details page. */
  footer?: ReactNode
}) {
  const [note, setNote] = useState('')
  const reason = whyNot(a, myRole)
  const noteId = `note-${a.id}`
  return (
    <article className="list-row" style={{ alignItems: 'flex-start' }} aria-label={`${humanize(a.subject_table)} approval`}>
      <div style={{ flex: '1 1 340px', minWidth: 0 }} className="stack">
        <div>
          <GateBadge gateId={a.gate_type} status={a.status === 'pending' ? 'pending' : a.status} />
          <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
            {humanize(a.subject_table)} <span className="mono">{a.subject_id.slice(0, 8)}</span> · raised {when(a.created_at)}
            {a.resolved_at ? ` · resolved ${when(a.resolved_at)}` : ''}
          </div>
          {a.decision_note && <div style={{ fontSize: 14, marginTop: 4 }}>Note: {a.decision_note}</div>}
        </div>
        {reason && <p className="muted" style={{ fontSize: 14 }}>{reason}</p>}
        {error && <p role="alert" className="notice notice-danger">{error}</p>}
        {footer}
      </div>
      {a.can_resolve && onResolve && (
        <div style={{ flex: '0 1 300px' }} className="stack">
          <div>
            <label className="label" htmlFor={noteId}>Note (optional)</label>
            <input id={noteId} className="input" value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          <div className="row">
            <Button variant="primary" busy={busy} onClick={() => onResolve('approved', note)}>Approve</Button>
            <Button variant="danger" disabled={busy} onClick={() => onResolve('rejected', note)}>Reject</Button>
          </div>
        </div>
      )}
    </article>
  )
}
