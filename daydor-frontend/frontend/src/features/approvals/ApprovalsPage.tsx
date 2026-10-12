import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useApprovals, useResolveApproval } from '../../api/hooks'
import { explain } from '../../api/errors'
import { useSession } from '../../api/session'
import { gateLabel } from '../../contract'
import { ApprovalCard } from '../../ui'

type Tab = 'pending' | 'resolved' | 'all'

export function ApprovalsPage() {
  const { session } = useSession()
  const [tab, setTab] = useState<Tab>('pending')
  const [gateFilter, setGateFilter] = useState('')
  const q = useApprovals()
  const resolve = useResolveApproval()
  const [errors, setErrors] = useState<Record<string, string>>({})

  const all = useMemo(() => q.data?.approvals ?? [], [q.data])
  const gatesPresent = useMemo(() => [...new Set(all.map((a) => a.gate_type))].sort((x, y) => gateLabel(x).localeCompare(gateLabel(y))), [all])
  const scoped = all.filter((a) => !gateFilter || a.gate_type === gateFilter)
  const counts = { pending: scoped.filter((a) => a.status === 'pending').length, resolved: scoped.filter((a) => a.status !== 'pending').length, all: scoped.length }
  const rows = scoped
    .filter((a) => tab === 'all' || (tab === 'pending' ? a.status === 'pending' : a.status !== 'pending'))
    // Things this person can act on come first, then newest.
    .sort((a, b) => Number(b.can_resolve) - Number(a.can_resolve) || b.created_at.localeCompare(a.created_at))

  const onResolve = (id: string) => (decision: 'approved' | 'rejected', note: string) => {
    setErrors((e) => ({ ...e, [id]: '' }))
    resolve.mutate({ id, decision, note }, { onError: (e) => setErrors((x) => ({ ...x, [id]: explain(e) })) })
  }
  const TABS: { id: Tab; label: string }[] = [{ id: 'pending', label: `Waiting (${counts.pending})` }, { id: 'resolved', label: `Resolved (${counts.resolved})` }, { id: 'all', label: `All (${counts.all})` }]
  return (
    <div className="stack" style={{ gap: 20 }}>
      <h1>Approvals</h1>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <div className="tabs" role="group" aria-label="Filter approvals by status">
          {TABS.map((t) => <button key={t.id} type="button" className="tab" aria-pressed={tab === t.id} onClick={() => setTab(t.id)}>{t.label}</button>)}
        </div>
        {gatesPresent.length > 1 && (
          <div>
            <label className="sr-only" htmlFor="gate-filter">Kind of approval</label>
            <select id="gate-filter" className="input" style={{ minHeight: 44, width: 'auto' }} value={gateFilter} onChange={(e) => setGateFilter(e.target.value)}>
              <option value="">All kinds</option>
              {gatesPresent.map((g) => <option key={g} value={g}>{gateLabel(g)}</option>)}
            </select>
          </div>
        )}
      </div>
      <section className="panel" aria-label="Approval requests" aria-live="polite">
        {q.isPending && <p>Loading approvals…</p>}
        {q.isError && <p role="alert" className="notice notice-danger">{explain(q.error)}</p>}
        {q.data && rows.length === 0 && <p className="muted">{tab === 'pending' ? 'Nothing is waiting for approval.' : 'No approvals to show here.'}</p>}
        <div className="list">
          {rows.map((a) => (
            <ApprovalCard key={a.id} approval={a} myRole={session!.role}
              busy={resolve.isPending && resolve.variables?.id === a.id} error={errors[a.id] || null} onResolve={onResolve(a.id)}
              footer={<Link to={`/approvals/${a.id}`} className="btn btn-quiet" style={{ alignSelf: 'flex-start', paddingLeft: 0 }}>Details</Link>} />
          ))}
        </div>
      </section>
    </div>
  )
}
