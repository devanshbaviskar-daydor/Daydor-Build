import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useDirectory, useLookups } from '../../api/hooks'
import { explain } from '../../api/errors'
import { labelFor } from '../../contract'

export function PeoplePage() {
  const [q, setQ] = useState('')
  const [dept, setDept] = useState('')
  const dir = useDirectory({ q, department_id: dept })
  const { lookups } = useLookups(['department', 'location'])
  return (
    <div className="stack" style={{ gap: 20 }}>
      <h1>People</h1>
      <div className="row">
        <div style={{ flex: '1 1 260px' }}><label className="sr-only" htmlFor="search">Search by name or email</label><input id="search" className="input" type="search" placeholder="Search by name or email" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        <div><label className="sr-only" htmlFor="dept">Department</label>
          <select id="dept" className="input" style={{ width: 'auto' }} value={dept} onChange={(e) => setDept(e.target.value)}>
            <option value="">All departments</option>{Object.values(lookups.department ?? {}).map((d) => <option key={String(d.id)} value={String(d.id)}>{labelFor('department', d)}</option>)}</select></div>
      </div>
      <section className="panel" aria-label="People" aria-live="polite">
        {dir.isPending && <p>Loading…</p>}
        {dir.isError && <p role="alert" className="notice notice-danger">{explain(dir.error)}</p>}
        {dir.data && dir.data.rows.length === 0 && <p className="muted">Nobody matches. Try a different search.</p>}
        {dir.data && dir.data.rows.length > 0 && (
          <div className="table-wrap"><table className="data">
            <caption className="sr-only">People</caption>
            <thead><tr><th scope="col">Name</th><th scope="col">Work email</th><th scope="col">Department</th><th scope="col">Location</th></tr></thead>
            <tbody>{dir.data.rows.map((p) => (
              <tr key={p.id}>
                <td><Link to={`/people/${p.id}`} className="btn btn-quiet" style={{ paddingLeft: 0, minHeight: 32 }}>{p.full_name}</Link></td>
                <td>{p.work_email}</td>
                <td>{lookups.department?.[p.department_id] ? labelFor('department', lookups.department[p.department_id]!) : ''}</td>
                <td>{lookups.location?.[p.location_id] ? labelFor('location', lookups.location[p.location_id]!) : ''}</td>
              </tr>))}</tbody>
          </table></div>
        )}
        {dir.data && <p className="muted" style={{ fontSize: 14, marginTop: 12 }}>{dir.data.total} {dir.data.total === 1 ? 'person' : 'people'}</p>}
      </section>
    </div>
  )
}
