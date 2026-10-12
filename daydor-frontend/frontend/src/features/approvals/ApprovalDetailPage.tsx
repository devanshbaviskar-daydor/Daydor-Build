import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useApproval, useEvaluations, useResolveApproval, useWorkflowInstance } from '../../api/hooks'
import { ApiError, explain } from '../../api/errors'
import { useSession } from '../../api/session'
import { gateLabel, humanize } from '../../contract'
import { ApprovalCard, Badge, DECISION_TEXT, GateBadge, WorkflowTimeline, describeApproval } from '../../ui'
import { AuditTrailButton } from '../trail/AuditTrailButton'

const pct = (v: number | string | null) => (v === null ? 'unknown' : `${Math.round(Number(v) * 100)}%`)

function Evaluations({ approvalId }: { approvalId: string }) {
  const q = useEvaluations({ approval_id: approvalId }, true)
  return (
    <section className="panel" aria-labelledby="pre">
      <h2 id="pre">Automated pre-check</h2>
      {q.isPending && <p aria-live="polite">Loading…</p>}
      {q.isError && <p role="alert" className="notice notice-danger">{explain(q.error)}</p>}
      {q.data && q.data.evaluations.length === 0 && <p className="muted">No automated pre-check was recorded for this request.</p>}
      <ul className="list" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
        {q.data?.evaluations.map((e) => (
          <li key={e.id} className="list-row" style={{ display: 'block' }}>
            <div className="row"><GateBadge gateId={e.gate_id} status="recorded" showId={false} mode={e.mode} /></div>
            <p style={{ marginTop: 6 }}>Pre-check result: <strong>{DECISION_TEXT[e.model_decision] ?? e.model_decision}</strong>. {pct(e.confidence)} sure; it needs {pct(e.threshold)} to pass without a person.</p>
            <p className="muted" style={{ fontSize: 14 }}>{e.mode === 'shadow' ? 'This check is recorded for comparison only. A person decides either way.' : 'This check can pass a request without a person when it is confident enough.'}</p>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function ApprovalDetailPage() {
  const { id } = useParams()
  const { session } = useSession()
  const approval = useApproval(id)
  const a = approval.data
  const canSeeWorkflow = (session!.capabilities?.workflow_timeline ?? false)
  const wf = useWorkflowInstance(canSeeWorkflow ? (a?.workflow_instance_id ?? null) : null)
  const resolve = useResolveApproval()
  const [error, setError] = useState<string | null>(null)

  if (approval.isPending) return <p aria-live="polite">Loading…</p>
  if (approval.isError || !a) {
    const missing = approval.error instanceof ApiError && approval.error.status === 404
    return (
      <div className="stack">
        <h1>{missing ? 'Request not found' : 'Approval unavailable'}</h1>
        <p role="alert" className="notice notice-danger">{explain(approval.error)}</p>
        <Link to="/approvals" className="btn btn-quiet" style={{ alignSelf: 'flex-start', paddingLeft: 0 }}>Back to approvals</Link>
      </div>
    )
  }
  return (
    <div className="stack" style={{ gap: 20 }}>
      <Link to="/approvals" className="btn btn-quiet" style={{ alignSelf: 'flex-start', paddingLeft: 0 }}>Back to approvals</Link>
      <div className="spread">
        <div>
          <h1>{gateLabel(a.gate_type)}</h1>
          <p className="muted" style={{ marginTop: 6 }}>{humanize(a.subject_table)} <span className="mono">{a.subject_id.slice(0, 8)}</span></p>
        </div>
        <AuditTrailButton table={a.subject_table} id={a.subject_id} title={`Audit trail: ${humanize(a.subject_table)}`} />
      </div>

      <section className="panel" aria-labelledby="decide">
        <h2 id="decide">Decision</h2>
        <div className="list">
          <ApprovalCard approval={a} myRole={session!.role} busy={resolve.isPending} error={error}
            onResolve={(decision, note) => { setError(null); resolve.mutate({ id: a.id, decision, note }, { onError: (e) => setError(explain(e)) }) }} />
        </div>
      </section>

      <section className="panel" aria-labelledby="stands">
        <h2 id="stands">Where this stands</h2>
        {canSeeWorkflow && wf.data ? (
          <>
            <div className="row" style={{ marginBottom: 14 }}>
              <Badge tone="outline">{humanize(wf.data.instance.definition_name)} workflow</Badge>
              <Link to={`/workflows/${wf.data.instance.id}`} className="btn btn-quiet">Open workflow</Link>
            </div>
            <WorkflowTimeline definition={wf.data.definition} instance={wf.data.instance} transitions={wf.data.transitions} />
          </>
        ) : (
          <>
            <p>{describeApproval(a)}</p>
            <p className="muted" style={{ fontSize: 14, marginTop: 8 }}>
              {canSeeWorkflow ? 'No workflow is attached to this request.' : 'Your role cannot see workflow timelines, so this is the status of the approval itself.'}
            </p>
          </>
        )}
        {canSeeWorkflow && wf.isError && <p role="alert" className="notice notice-danger" style={{ marginTop: 12 }}>{explain(wf.error)}</p>}
      </section>

      {canSeeWorkflow && <Evaluations approvalId={a.id} />}
    </div>
  )
}
