import { Link, useParams } from 'react-router-dom'
import { useWorkflowInstance } from '../../api/hooks'
import { ApiError, explain } from '../../api/errors'
import { humanize } from '../../contract'
import { GateBadge, WorkflowTimeline } from '../../ui'
import { AuditTrailButton } from '../trail/AuditTrailButton'
import { StatusBadge } from './WorkflowsPage'

const when = (iso: string) => new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })
const OUTCOME: Record<string, string> = { moved: 'Moved on', waiting_gate: 'Paused for approval', rejected: 'Approval rejected' }

export function WorkflowDetailPage() {
  const { id } = useParams()
  const q = useWorkflowInstance(id ?? null)
  if (q.isPending) return <p aria-live="polite">Loading…</p>
  if (q.isError || !q.data) {
    const missing = q.error instanceof ApiError && q.error.status === 404
    return (
      <div className="stack">
        <h1>{missing ? 'Workflow not found' : 'Workflow unavailable'}</h1>
        <p role="alert" className="notice notice-danger">{explain(q.error)}</p>
        <Link to="/workflows" className="btn btn-quiet" style={{ alignSelf: 'flex-start', paddingLeft: 0 }}>Back to workflows</Link>
      </div>
    )
  }
  const { instance: i, transitions, definition } = q.data
  const hidden = i.context_hidden_keys?.length ?? 0
  const gateId = definition.states[i.state]?.on?.advance?.gate
  return (
    <div className="stack" style={{ gap: 20 }}>
      <Link to="/workflows" className="btn btn-quiet" style={{ alignSelf: 'flex-start', paddingLeft: 0 }}>Back to workflows</Link>
      <div className="spread">
        <div>
          <h1>{humanize(i.definition_name)} workflow</h1>
          <p className="muted" style={{ marginTop: 6 }}>{humanize(i.subject_table)} <span className="mono">{i.subject_id.slice(0, 8)}</span> · version {i.definition_version}</p>
        </div>
        <AuditTrailButton table={i.subject_table} id={i.subject_id} title={`Audit trail: ${humanize(i.subject_table)}`} />
      </div>

      <section className="panel" aria-labelledby="summary">
        <h2 id="summary">Summary</h2>
        <dl className="grid-2" style={{ margin: 0 }}>
          <div className="field"><dt className="field-label">Status</dt><dd className="field-value" style={{ margin: 0 }}><StatusBadge status={i.status} /></dd></div>
          <div className="field"><dt className="field-label">Current step</dt><dd className="field-value" style={{ margin: 0 }}>{humanize(i.state)}</dd></div>
          <div className="field"><dt className="field-label">Started</dt><dd className="field-value" style={{ margin: 0 }}>{when(i.created_at)}</dd></div>
          <div className="field"><dt className="field-label">Last change</dt><dd className="field-value" style={{ margin: 0 }}>{when(i.updated_at)}</dd></div>
        </dl>
        {i.waiting_on_approval && (
          <p style={{ marginTop: 16 }}>
            {gateId ? <GateBadge gateId={gateId} status="waiting" /> : 'Waiting for an approval.'}{' '}
            <Link to={`/approvals/${i.waiting_on_approval}`} className="btn btn-quiet">Open the approval</Link>
          </p>
        )}
      </section>

      <section className="panel" aria-labelledby="steps"><h2 id="steps">Steps</h2><WorkflowTimeline definition={definition} instance={i} transitions={transitions} /></section>

      <section className="panel" aria-labelledby="log">
        <h2 id="log">What happened</h2>
        {transitions.length === 0 ? <p className="muted">Nothing has happened yet.</p> : (
          <div className="table-wrap"><table className="data">
            <thead><tr><th>When</th><th>From</th><th>To</th><th>Result</th></tr></thead>
            <tbody>{transitions.map((t) => (
              <tr key={t.id}><td>{when(t.created_at)}</td><td>{humanize(t.from_state)}</td><td>{humanize(t.to_state)}</td><td>{OUTCOME[t.outcome] ?? t.outcome}</td></tr>
            ))}</tbody></table></div>
        )}
      </section>

      <section className="panel" aria-labelledby="ctx">
        <h2 id="ctx">Details the workflow carries</h2>
        <dl className="grid-2" style={{ margin: 0 }}>
          {Object.entries(i.context).map(([k, v]) => (
            <div key={k} className="field"><dt className="field-label">{humanize(k)}</dt><dd className="field-value mono" style={{ margin: 0 }}>{String(v)}</dd></div>
          ))}
        </dl>
        {hidden > 0 && <p className="muted" style={{ fontSize: 14, marginTop: 12 }}>{hidden} more {hidden === 1 ? 'value stays' : 'values stay'} in the database and {hidden === 1 ? 'is' : 'are'} not shown here, such as candidate details.</p>}
      </section>
    </div>
  )
}
