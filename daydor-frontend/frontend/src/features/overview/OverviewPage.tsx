import { Link } from 'react-router-dom'
import { useApprovals, useRequisitions, useTable, useWorkflowInstances } from '../../api/hooks'
import { explain } from '../../api/errors'
import { useSession } from '../../api/session'
import { GateBadge } from '../../ui'
import { canReadTable } from '../../contract'

function HiringSummary() {
  const reqs = useRequisitions()
  const positions = useTable('position', { limit: '200' })
  const list = reqs.data?.requisitions ?? []
  const openSeats = (positions.data?.rows ?? []).filter((p) => p.status === 'open' && !p.current_employee_id).length
  const waiting = list.filter((r) => r.stage === 'awaiting_budget_approval').length
  const candidates = list.reduce((n, r) => n + r.candidate_count, 0)
  return (
    <section className="panel" aria-labelledby="hire">
      <div className="spread"><h2 id="hire">Hiring</h2><Link to="/requisitions" className="btn btn-quiet">All requisitions</Link></div>
      {(reqs.isPending || positions.isPending) && <p aria-live="polite">Loading…</p>}
      {reqs.isError && <p role="alert" className="notice notice-danger">{explain(reqs.error)}</p>}
      {reqs.data && (
        <dl className="grid-2" style={{ margin: 0 }}>
          <div className="field"><dt className="field-label">Open seats</dt><dd className="field-value" style={{ margin: 0 }}>{positions.data ? <Link to="/positions">{openSeats}</Link> : 'n/a'}</dd></div>
          <div className="field"><dt className="field-label">Requisitions</dt><dd className="field-value" style={{ margin: 0 }}>{list.length}</dd></div>
          <div className="field"><dt className="field-label">Waiting for budget approval</dt><dd className="field-value" style={{ margin: 0 }}>{waiting}</dd></div>
          <div className="field"><dt className="field-label">Candidates in progress</dt><dd className="field-value" style={{ margin: 0 }}>{candidates}</dd></div>
        </dl>
      )}
    </section>
  )
}

function WorkflowSummary() {
  const q = useWorkflowInstances()
  const list = q.data?.instances ?? []
  const waiting = list.filter((i) => i.status === 'waiting_gate').length
  const running = list.filter((i) => i.status === 'running').length
  return (
    <section className="panel" aria-labelledby="wfs">
      <div className="spread"><h2 id="wfs">Workflows</h2><Link to="/workflows" className="btn btn-quiet">All workflows</Link></div>
      {q.isPending && <p aria-live="polite">Loading…</p>}
      {q.isError && <p role="alert" className="notice notice-danger">{explain(q.error)}</p>}
      {q.data && <p>{waiting} waiting for approval, {running} in progress.</p>}
    </section>
  )
}

export function OverviewPage() {
  const { session } = useSession()
  const role = session!.role
  const readsApprovals = canReadTable('approval_request', role)
  const approvals = useApprovals('pending')
  const mine = approvals.data?.approvals.filter((a) => a.can_resolve) ?? []
  return (
    <div className="stack" style={{ gap: 24 }}>
      <div><div className="muted" style={{ fontSize: 14 }}>{new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}</div><h1>Overview</h1></div>
      <section className="panel" aria-labelledby="wait">
        <div className="spread"><h2 id="wait">Waiting for you</h2>{readsApprovals && <Link to="/approvals" className="btn btn-quiet">All approvals</Link>}</div>
        {!readsApprovals && <p className="muted">Approvals are not part of your role. Your screens will appear here as they are built.</p>}
        {readsApprovals && approvals.isPending && <p aria-live="polite">Loading…</p>}
        {readsApprovals && approvals.isError && <p role="alert" className="notice notice-danger">{explain(approvals.error)}</p>}
        {readsApprovals && approvals.data && mine.length === 0 && <p className="muted">Nothing needs your approval right now.</p>}
        {mine.length > 0 && (
          <ul className="list" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {mine.slice(0, 5).map((a) => <li key={a.id} className="list-row"><GateBadge gateId={a.gate_type} status="pending" /><Link to={`/approvals/${a.id}`} className="btn btn-quiet">Review</Link></li>)}
          </ul>
        )}
      </section>
      {canReadTable('job_requisition', role) && <HiringSummary />}
      {(session!.capabilities?.workflow_timeline ?? false) && <WorkflowSummary />}
      <section className="panel" aria-labelledby="who">
        <h2 id="who">Your session</h2>
        <dl className="grid-2" style={{ margin: 0 }}>
          <div className="field"><dt className="field-label">Name</dt><dd className="field-value" style={{ margin: 0 }}>{session!.display_name}</dd></div>
          <div className="field"><dt className="field-label">Role</dt><dd className="field-value" style={{ margin: 0 }}>{session!.role_label}</dd></div>
          <div className="field"><dt className="field-label">Company</dt><dd className="field-value" style={{ margin: 0 }}>{session!.tenant_name ?? 'All companies (platform)'}</dd></div>
        </dl>
      </section>
    </div>
  )
}
