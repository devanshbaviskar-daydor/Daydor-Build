import { useLookups, useTable } from '../../api/hooks'
import { explain } from '../../api/errors'
import { useSession } from '../../api/session'
import { enumLabel, labelFor } from '../../contract'
import { Badge, FieldValue, TimerCountdown } from '../../ui'
import { shortDate } from '../shared'

export function WorkAuthorizationPage() {
  const { session } = useSession()
  const role = session!.role
  const q = useTable('work_authorization', { limit: '100' })
  const { lookups } = useLookups(['employee'])
  return (
    <div className="stack" style={{ gap: 20 }}>
      <div><h1>Work authorization</h1><p className="muted" style={{ marginTop: 6 }}>For US employees only. The I-9 form and E-Verify are US requirements, so employees in India do not appear here.</p></div>
      <section className="panel" aria-label="Work authorization cases" aria-live="polite">
        {q.isPending && <p>Loading…</p>}
        {q.isError && <p role="alert" className="notice notice-danger">{explain(q.error)}</p>}
        {q.data && q.data.rows.length === 0 && <p className="muted">No US employees need work authorization tracking right now.</p>}
        {q.data && q.data.rows.length > 0 && (
          <div className="table-wrap"><table className="data">
            <caption className="sr-only">Work authorization cases</caption>
            <thead><tr><th scope="col">Employee</th><th scope="col">Type</th><th scope="col">Status</th><th scope="col">E-Verify</th><th scope="col">Expires</th><th scope="col">Next step due</th><th scope="col">Sponsored</th></tr></thead>
            <tbody>{q.data.rows.map((r) => {
              const who = lookups.employee?.[String(r.employee_id)]
              return (
                <tr key={String(r.id)}>
                  <td>{who ? labelFor('employee', who) : <span className="muted">Not visible</span>}</td>
                  <td><FieldValue table="work_authorization" column="auth_type" value={r.auth_type} role={role} /></td>
                  <td><FieldValue table="work_authorization" column="status" value={r.status ? enumLabel('work_authorization', 'status', String(r.status)) : r.status} role={role} /></td>
                  <td><FieldValue table="work_authorization" column="everify_status" value={r.everify_status ? enumLabel('work_authorization', 'everify_status', String(r.everify_status)) : r.everify_status} role={role} /> <Badge tone="outline" title="E-Verify is a stand-in for now. Nothing was sent to the government service.">Test E-Verify</Badge></td>
                  <td><FieldValue table="work_authorization" column="expiration_date" value={r.expiration_date} role={role} /></td>
                  <td>{r.next_action_due ? <><span>{shortDate(r.next_action_due)} </span><TimerCountdown dueAt={`${String(r.next_action_due)}T23:59:59`} /></> : <span className="restricted">None</span>}</td>
                  <td><FieldValue table="work_authorization" column="sponsor_flag" value={r.sponsor_flag} role={role} /></td>
                </tr>
              )
            })}</tbody>
          </table></div>
        )}
      </section>
    </div>
  )
}
