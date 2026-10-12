import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useWorkflowInstances } from '../../api/hooks'
import { explain } from '../../api/errors'
import { humanize } from '../../contract'
import { Badge, INSTANCE_STATUS } from '../../ui'

const TABS = [{ id: '', label: 'All' }, { id: 'waiting_gate', label: 'Waiting for approval' }, { id: 'running', label: 'In progress' }, { id: 'completed', label: 'Completed' }, { id: 'cancelled', label: 'Stopped' }]

export function StatusBadge({ status }: { status: string }) {
  const s = INSTANCE_STATUS[status] ?? { text: status, tone: 'neutral' as const, mark: '·' }
  return <Badge tone={s.tone} mark={s.mark}>{s.text}</Badge>
}

export function WorkflowsPage() {
  const [status, setStatus] = useState('')
  const q = useWorkflowInstances(status || undefined)
  return (
    <div className="stack" style={{ gap: 20 }}>
      <h1>Workflows</h1>
      <div className="tabs" role="group" aria-label="Filter workflows by status">
        {TABS.map((t) => <button key={t.id} type="button" className="tab" aria-pressed={status === t.id} onClick={() => setStatus(t.id)}>{t.label}</button>)}
      </div>
      <section className="panel" aria-label="Workflows" aria-live="polite">
        {q.isPending && <p>Loading workflows…</p>}
        {q.isError && <p role="alert" className="notice notice-danger">{explain(q.error)}</p>}
        {q.data && q.data.instances.length === 0 && <p className="muted">No workflows match this filter.</p>}
        {q.data && q.data.instances.length > 0 && (
          <div className="table-wrap">
            <table className="data">
              <thead><tr><th>Workflow</th><th>Current step</th><th>Status</th><th>Updated</th></tr></thead>
              <tbody>
                {q.data.instances.map((i) => (
                  <tr key={i.id}>
                    <td><Link to={`/workflows/${i.id}`} className="btn btn-quiet" style={{ paddingLeft: 0, minHeight: 32 }}>{humanize(i.definition_name)}: {humanize(i.subject_table)} <span className="mono">{i.subject_id.slice(0, 8)}</span></Link></td>
                    <td>{humanize(i.state)}</td>
                    <td><StatusBadge status={i.status} /></td>
                    <td>{new Date(i.updated_at).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
