import { Link } from 'react-router-dom'
import { useRequisitions } from '../../api/hooks'
import { explain } from '../../api/errors'
import { money } from '../../contract'
import { dateTime, shortDate, StageBadge } from '../shared'

export function RequisitionsPage() {
  const q = useRequisitions()
  const rows = q.data?.requisitions ?? []
  return (
    <div className="stack" style={{ gap: 20 }}>
      <h1>Requisitions</h1>
      <p className="muted">One requisition per hire. Open seats are on the <Link to="/positions" className="btn btn-quiet" style={{ minHeight: 0, padding: 0 }}>Positions</Link> page.</p>
      <section className="panel" aria-label="Requisitions" aria-live="polite">
        {q.isPending && <p>Loading requisitions…</p>}
        {q.isError && <p role="alert" className="notice notice-danger">{explain(q.error)}</p>}
        {q.data && rows.length === 0 && <p className="muted">No requisitions yet. Start hiring from an open seat on the Positions page.</p>}
        {rows.length > 0 && (
          <div className="table-wrap"><table className="data">
            <caption className="sr-only">Requisitions</caption>
            <thead><tr><th scope="col">Job</th><th scope="col">Stage</th><th scope="col">Hiring manager</th><th scope="col">Pay range</th><th scope="col">Posted</th><th scope="col">Candidates</th><th scope="col">Target start</th></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.id}>
                <td><Link to={`/requisitions/${r.id}`} className="btn btn-quiet" style={{ paddingLeft: 0, minHeight: 32 }}>{r.job_title ?? 'Requisition'}{r.department_name ? `, ${r.department_name}` : ''}</Link></td>
                <td><StageBadge stage={r.stage} /></td>
                <td>{r.hiring_manager_name ?? <span className="muted">Not visible</span>}</td>
                <td>{r.posting ? `${money(r.posting.pay_range_min)} to ${money(r.posting.pay_range_max)}` : <span className="muted">Not posted</span>}</td>
                <td>{r.posting?.posted_at ? dateTime(r.posting.posted_at) : <span className="muted">Not yet</span>}</td>
                <td>{r.candidate_count}</td>
                <td>{shortDate(r.target_start_date)}</td>
              </tr>))}</tbody>
          </table></div>
        )}
      </section>
    </div>
  )
}
