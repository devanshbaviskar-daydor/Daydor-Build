import { Link } from 'react-router-dom'
import { useTable } from '../../api/hooks'
import type { ApprovalBrief, PipelineItem } from '../../api/types'
import { canReadTable, enumLabel, money } from '../../contract'
import { Badge, GateBadge, MockAdapterBadge } from '../../ui'
import { dateTime, shortDate } from '../shared'

type StepState = 'done' | 'waiting' | 'todo'
function Step({ title, state, children }: { title: string; state: StepState; children: React.ReactNode }) {
  const t = state === 'done' ? { text: 'Done', tone: 'ok' as const, mark: '✓' } : state === 'waiting' ? { text: 'Needs a decision', tone: 'warn' as const, mark: '◔' } : { text: 'Not reached yet', tone: 'neutral' as const, mark: '·' }
  return (
    <li className="list-row" style={{ alignItems: 'flex-start', display: 'block' }} aria-label={title}>
      <div className="row"><h3>{title}</h3><Badge tone={t.tone} mark={t.mark}>{t.text}</Badge></div>
      <div style={{ marginTop: 6 }}>{children}</div>
    </li>
  )
}
const ApprovalLine = ({ a }: { a: ApprovalBrief | null }) => (a
  ? <p style={{ marginTop: 6 }}><GateBadge gateId={a.gate_type} status={a.status} showId={false} /> <Link to={`/approvals/${a.id}`} className="btn btn-quiet">Open the approval</Link></p>
  : null)
const pct = (v: number | string) => `${Math.round(Number(v) * 100)}%`

/** What the background-check step reads, keyed by candidate. */
function BackgroundStep({ candidateId, role }: { candidateId: string; role: string }) {
  const can = canReadTable('background_check', role)
  const q = useTable('background_check', { candidate_id: candidateId })
  if (!can) return <Step title="Background check" state="todo"><p className="muted">Your role cannot see background checks.</p></Step>
  const bg = q.data?.rows[0]
  if (!bg) return <Step title="Background check" state="todo"><p className="muted">Not started yet. It runs automatically once the offer step clears.</p></Step>
  const adverse = !!bg.adverse_action_stage
  return (
    <Step title="Background check" state={adverse ? 'waiting' : 'done'}>
      <div className="row"><span>{enumLabel('background_check', 'status', String(bg.status))}</span><MockAdapterBadge vendor="background check vendor" /></div>
      <p className="muted" style={{ fontSize: 14 }}>Ordered {dateTime(bg.ordered_at)}{bg.findings_summary ? `. ${String(bg.findings_summary)}` : ''}</p>
      {adverse && <p className="notice notice-warn">An adverse finding needs HR review before anything else happens.</p>}
    </Step>
  )
}

export function PipelineCard({ item, role, seeCandidates }: { item: PipelineItem; role: string; seeCandidates: boolean }) {
  const { application: a, candidate: c, screening: s, interview: i, offer: o } = item
  return (
    <article className="panel" aria-label={c ? `Candidate ${c.full_name}` : 'Candidate'}>
      <div className="spread">
        <div>
          <h2>{c ? c.full_name : 'Candidate not visible to your role'}</h2>
          <p className="muted" style={{ fontSize: 14 }}>{c ? `${c.email} · from ${enumLabel('candidate', 'source', c.source)}` : seeCandidates ? 'The database hides a candidate’s details from managers until they become an employee.' : ''}</p>
        </div>
        <Badge tone="accent">{enumLabel('application', 'stage', a.stage)}</Badge>
      </div>
      <ol className="list" style={{ listStyle: 'none', margin: '12px 0 0', padding: 0 }}>
        <Step title="Screening" state={!s ? 'todo' : s.approval?.status === 'pending' ? 'waiting' : 'done'}>
          {s ? (<>
            <div className="row"><span>Score <strong>{pct(s.score)}</strong>, suggests <strong>{enumLabel('screening_result', 'recommendation', s.recommendation)}</strong></span><MockAdapterBadge vendor="screener" /></div>
            <p className="muted" style={{ fontSize: 14 }}>{s.tool_name} version {s.model_version}. This is a placeholder: it always needs HR sign-off before the candidate moves on.</p>
            <ApprovalLine a={s.approval} />
          </>) : <p className="muted">Runs after an application is entered.</p>}
        </Step>
        <Step title="Interview" state={i ? 'done' : 'todo'}>
          {i ? <p>{dateTime(i.scheduled_at)} with {i.interviewer_name ?? 'the interviewer'}{i.recommendation ? `. Recommendation: ${enumLabel('interview', 'recommendation', i.recommendation)}` : ''}</p> : <p className="muted">Scheduled after HR signs off the screening.</p>}
        </Step>
        <Step title="Offer" state={!o ? 'todo' : o.approval?.status === 'pending' ? 'waiting' : 'done'}>
          {o ? (<>
            <div className="row"><span>Proposed base <strong>{money(o.proposed_base)}</strong></span>
              {o.within_band ? <Badge tone="ok">Within band</Badge> : <Badge tone="warn" mark="◔">Outside band</Badge>}</div>
            {o.band && <p className="muted" style={{ fontSize: 14 }}>Band {money(o.band.band_min, o.band.currency)} to {money(o.band.band_max, o.band.currency)}</p>}
            {!o.within_band && <p className="muted" style={{ fontSize: 14 }}>An offer outside the band needs the founder’s approval before it can go out.</p>}
            <ApprovalLine a={o.approval} />
            {(o.sent_at || o.accepted_at) && <p className="muted" style={{ fontSize: 14 }}>{o.sent_at ? `Sent ${shortDate(o.sent_at)}` : ''}{o.accepted_at ? `. Accepted ${shortDate(o.accepted_at)}` : ''}</p>}
          </>) : <p className="muted">Made after the interview.</p>}
        </Step>
        {c && <BackgroundStep candidateId={c.id} role={role} />}
      </ol>
    </article>
  )
}
