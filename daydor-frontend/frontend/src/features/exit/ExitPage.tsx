import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useLookups, useTable } from '../../api/hooks'
import { explain } from '../../api/errors'
import { useSession } from '../../api/session'
import { labelFor } from '../../contract'
import { Badge, Button } from '../../ui'
import { shortDate } from '../shared'
import { StartExitDialog } from './StartExitDialog'

/** One termination row per employee (daydor.exit.termination: "idempotent on employee_id"). The
 *  flow runs automatically from here except for three steps a person triggers on the detail page --
 *  deprovisioning, final-settlement disbursal, COBRA notice -- each gated by a column on a row other
 *  than the termination itself (docs/integration-notes.md). */
export function ExitPage() {
  const { session } = useSession()
  const role = session!.role
  const terminations = useTable('termination', { limit: '50' })
  const { lookups } = useLookups(['employee'])
  const [open, setOpen] = useState(false)
  const canStart = role === 'tenant_hr' || role === 'tenant_founder'

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="spread">
        <div><h1>Exit</h1><p className="muted">Legal hold, checklist, deprovisioning, device return, final settlement, COBRA (US) and closeout.</p></div>
        {canStart && <Button variant="primary" onClick={() => setOpen(true)}>Start a termination</Button>}
      </div>
      <section className="panel" aria-label="Terminations" aria-live="polite">
        {terminations.isPending && <p>Loading…</p>}
        {terminations.isError && <p role="alert" className="notice notice-danger">{explain(terminations.error)}</p>}
        {terminations.data && terminations.data.rows.length === 0 && <p className="muted">No terminations yet.</p>}
        {terminations.data && terminations.data.rows.length > 0 && (
          <div className="table-wrap"><table className="data">
            <caption className="sr-only">Terminations</caption>
            <thead><tr><th scope="col">Employee</th><th scope="col">Type</th><th scope="col">Reason</th><th scope="col">Last working day</th><th scope="col">Status</th></tr></thead>
            <tbody>{terminations.data.rows.map((t) => {
              const employee = lookups.employee?.[String(t.employee_id)]
              const closed = employee ? employee.is_active === false : false
              return (
                <tr key={String(t.id)}>
                  <td><Link to={`/exit/${t.id}`} className="btn btn-quiet" style={{ paddingLeft: 0, minHeight: 32 }}>{employee ? labelFor('employee', employee) : 'Termination'}</Link></td>
                  <td>{String(t.termination_type)}</td>
                  <td>{String(t.reason_code)}</td>
                  <td>{shortDate(t.last_working_day)}</td>
                  <td>{closed ? <Badge tone="ok">Closed out</Badge> : <Badge tone="warn">In progress</Badge>}</td>
                </tr>
              )
            })}</tbody>
          </table></div>
        )}
      </section>
      {open && <StartExitDialog onClose={() => setOpen(false)} />}
    </div>
  )
}
