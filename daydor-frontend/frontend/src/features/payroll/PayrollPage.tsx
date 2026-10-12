import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useBuildPayrollRun, useLookups, useTable } from '../../api/hooks'
import { explain } from '../../api/errors'
import { useSession } from '../../api/session'
import { labelFor, money } from '../../contract'
import { Badge, Button, Dialog } from '../../ui'
import { shortDate } from '../shared'

/** Payroll is not workflow-engine-driven (docs/integration-notes.md): there is no requisition-like
 *  instance to list, only payroll_run rows with their own status. This lists them and starts new
 *  ones; the run detail page carries anomaly check, disbursal, payslip issuance, filing and GL. */
export function PayrollPage() {
  const { session } = useSession()
  const role = session!.role
  const runs = useTable('payroll_run', { limit: '50' })
  const { lookups } = useLookups(['legal_entity', 'retention_policy'])
  const build = useBuildPayrollRun()
  const [open, setOpen] = useState(false)
  const [key, setKey] = useState(() => crypto.randomUUID())
  const [form, setForm] = useState({ legalEntity: '', start: '', end: '', retention: '' })
  const canRun = role === 'tenant_payroll' || role === 'tenant_founder' || role === 'daydor_ops'
  const entities = Object.values(lookups.legal_entity ?? {})
  const retentions = Object.values(lookups.retention_policy ?? {})

  const submit = () => {
    setKey(crypto.randomUUID())
    build.mutate({ body: { legal_entity_id: form.legalEntity, period_start: form.start, period_end: form.end, retention_class_id: form.retention }, key },
      { onSuccess: () => setOpen(false) })
  }
  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="spread">
        <div><h1>Payroll</h1><p className="muted">Gross-to-net is illustrative (one flat rate per statutory scheme), not compliance-grade.</p></div>
        {canRun && <Button variant="primary" onClick={() => setOpen(true)}>Build a run</Button>}
      </div>
      <section className="panel" aria-label="Payroll runs" aria-live="polite">
        {runs.isPending && <p>Loading…</p>}
        {runs.isError && <p role="alert" className="notice notice-danger">{explain(runs.error)}</p>}
        {runs.data && runs.data.rows.length === 0 && <p className="muted">No payroll runs yet.</p>}
        {runs.data && runs.data.rows.length > 0 && (
          <div className="table-wrap"><table className="data">
            <caption className="sr-only">Payroll runs</caption>
            <thead><tr><th scope="col">Legal entity</th><th scope="col">Period</th><th scope="col">Gross</th><th scope="col">Net</th><th scope="col">Disbursed</th></tr></thead>
            <tbody>{runs.data.rows.map((r) => {
              const entity = lookups.legal_entity?.[String(r.legal_entity_id)]
              return (
                <tr key={String(r.id)}>
                  <td><Link to={`/payroll/${r.id}`} className="btn btn-quiet" style={{ paddingLeft: 0, minHeight: 32 }}>{entity ? labelFor('legal_entity', entity) : 'Payroll run'}</Link></td>
                  <td>{shortDate(r.period_start)} to {shortDate(r.period_end)}</td>
                  <td>{money(r.gross_total)}</td>
                  <td>{money(r.net_total)}</td>
                  <td>{r.disbursed_at ? <Badge tone="ok">{shortDate(r.disbursed_at)}</Badge> : <Badge tone="warn">Not yet</Badge>}</td>
                </tr>
              )
            })}</tbody>
          </table></div>
        )}
      </section>
      <Dialog open={open} title="Build a payroll run" onClose={() => setOpen(false)}>
        <p className="muted" style={{ fontSize: 14 }}>Computes gross-to-net for every active employee under the legal entity and runs its anomaly pre-check in the same step -- shadow mode always escalates, so this always raises an approval.</p>
        <div className="stack" style={{ gap: 12, marginTop: 12 }}>
          <div><label className="label" htmlFor="le">Legal entity</label>
            <select id="le" className="input" value={form.legalEntity} onChange={(e) => setForm((f) => ({ ...f, legalEntity: e.target.value }))}>
              <option value="">Choose…</option>{entities.map((e) => <option key={String(e.id)} value={String(e.id)}>{labelFor('legal_entity', e)}</option>)}
            </select>
          </div>
          <div className="row">
            <div style={{ flex: 1 }}><label className="label" htmlFor="start">Period start</label><input id="start" className="input" type="date" value={form.start} onChange={(e) => setForm((f) => ({ ...f, start: e.target.value }))} /></div>
            <div style={{ flex: 1 }}><label className="label" htmlFor="end">Period end</label><input id="end" className="input" type="date" value={form.end} onChange={(e) => setForm((f) => ({ ...f, end: e.target.value }))} /></div>
          </div>
          <div><label className="label" htmlFor="rc">Document retention policy</label>
            <select id="rc" className="input" value={form.retention} onChange={(e) => setForm((f) => ({ ...f, retention: e.target.value }))}>
              <option value="">Choose…</option>{retentions.map((r) => <option key={String(r.id)} value={String(r.id)}>{String(r.retention_class)}</option>)}
            </select>
          </div>
          {build.isError && <p role="alert" className="notice notice-danger">{explain(build.error)}</p>}
          <div className="row"><Button variant="primary" busy={build.isPending} disabled={!form.legalEntity || !form.start || !form.end || !form.retention} onClick={submit}>Build run</Button><Button onClick={() => setOpen(false)}>Cancel</Button></div>
        </div>
      </Dialog>
    </div>
  )
}
