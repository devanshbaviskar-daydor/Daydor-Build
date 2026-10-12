import { Link, useParams } from 'react-router-dom'
import {
  useApprovalsFor, useDisburse, useFileReturns, useIssuePayslips, useLookups,
  useOpenGlEntry, usePostGlEntry, useRequestDisbursal, useTable,
} from '../../api/hooks'
import { explain } from '../../api/errors'
import { useSession } from '../../api/session'
import { labelFor, money } from '../../contract'
import { Badge, Button, GateBadge } from '../../ui'
import { shortDate } from '../shared'

function Action({ title, blurb, children }: { title: string; blurb: string; children: React.ReactNode }) {
  return <section className="panel"><h2>{title}</h2><p className="muted" style={{ fontSize: 14 }}>{blurb}</p><div style={{ marginTop: 10 }}>{children}</div></section>
}

export function PayrollRunDetailPage() {
  const { id } = useParams()
  const { session } = useSession()
  const role = session!.role
  const canAct = role === 'tenant_payroll' || role === 'tenant_founder' || role === 'daydor_ops'
  const run = useTable('payroll_run', id ? { id } : { id: '-' })
  const payslips = useTable('payslip', id ? { payroll_run_id: id } : { payroll_run_id: '-' })
  const filings = useTable('filing_record', { limit: '50' })
  const gl = useTable('gl_journal_entry', { source_id: id ?? '-' })
  const approvals = useApprovalsFor(id)
  const glEntry = gl.data?.rows[0]
  const glApprovals = useApprovalsFor(glEntry ? String(glEntry.id) : undefined)
  const { lookups } = useLookups(['legal_entity', 'retention_policy'])

  const requestDisbursal = useRequestDisbursal()
  const disburse = useDisburse()
  const issue = useIssuePayslips()
  const file = useFileReturns()
  const openGl = useOpenGlEntry()
  const postGl = usePostGlEntry()

  const r = run.data?.rows[0]
  if (run.isPending) return <p aria-live="polite">Loading…</p>
  if (run.isError || !r) return <div className="stack"><h1>Payroll run</h1><p role="alert" className="notice notice-danger">{run.isError ? explain(run.error) : 'That payroll run was not found.'}</p></div>

  const entity = lookups.legal_entity?.[String(r.legal_entity_id)]
  const anomalyGate = (approvals.data?.approvals ?? []).find((a) => a.gate_type === 'g_pay_anomaly')
  const disbursalGate = (approvals.data?.approvals ?? []).find((a) => a.gate_type === 'g_pay_disburse')
  const closeGate = (glApprovals.data?.approvals ?? []).find((a) => a.gate_type === 'g_close')
  const anomalyCleared = anomalyGate ? anomalyGate.status === 'approved' : true
  const disbursed = !!r.disbursed_at
  const retention = Object.values(lookups.retention_policy ?? {})[0]
  const period = String(r.period_end).slice(0, 7)

  return (
    <div className="stack" style={{ gap: 20 }}>
      <Link to="/payroll" className="btn btn-quiet" style={{ alignSelf: 'flex-start', paddingLeft: 0 }}>Back to payroll</Link>
      <div><h1>{entity ? labelFor('legal_entity', entity) : 'Payroll run'}</h1><p className="muted">{shortDate(r.period_start)} to {shortDate(r.period_end)}</p></div>

      <section className="panel">
        <h2>Totals</h2>
        <dl className="grid-2" style={{ margin: 0 }}>
          <div className="field"><dt className="field-label">Gross</dt><dd className="field-value" style={{ margin: 0 }}>{money(r.gross_total)}</dd></div>
          <div className="field"><dt className="field-label">Net</dt><dd className="field-value" style={{ margin: 0 }}>{money(r.net_total)}</dd></div>
        </dl>
      </section>

      {anomalyGate && (
        <section className="panel">
          <h2>Anomaly pre-check</h2>
          <p style={{ marginTop: 6 }}><GateBadge gateId="g_pay_anomaly" status={anomalyGate.status} showId={false} /> {anomalyGate.status === 'pending' && <Link to={`/approvals/${anomalyGate.id}`} className="btn btn-quiet">Open the approval</Link>}</p>
          <p className="muted" style={{ fontSize: 14 }}>Shadow mode always escalates this to a human review, regardless of what the pre-check found.</p>
        </section>
      )}

      {canAct && anomalyCleared && !disbursed && (
        <Action title="Disbursal" blurb="Impossible without an approved g_pay_disburse request, enforced by the database, not this screen.">
          {!disbursalGate && <Button busy={requestDisbursal.isPending} onClick={() => requestDisbursal.mutate({ runId: r.id as string, key: crypto.randomUUID() })}>Request disbursal</Button>}
          {disbursalGate && disbursalGate.status !== 'approved' && <p><GateBadge gateId="g_pay_disburse" status={disbursalGate.status} showId={false} /> <Link to={`/approvals/${disbursalGate.id}`} className="btn btn-quiet">Open the approval</Link></p>}
          {disbursalGate && disbursalGate.status === 'approved' && (
            <Button variant="primary" busy={disburse.isPending} onClick={() => disburse.mutate({ runId: r.id as string, approval_request_id: disbursalGate.id, key: crypto.randomUUID() })}>Disburse</Button>
          )}
          {requestDisbursal.isError && <p role="alert" className="notice notice-danger" style={{ marginTop: 8 }}>{explain(requestDisbursal.error)}</p>}
          {disburse.isError && <p role="alert" className="notice notice-danger" style={{ marginTop: 8 }}>{explain(disburse.error)}</p>}
        </Action>
      )}
      {disbursed && <section className="panel"><h2>Disbursal</h2><p><Badge tone="ok">Disbursed {shortDate(r.disbursed_at)}</Badge></p></section>}

      {canAct && disbursed && (
        <Action title="Payslips" blurb="Refuses until the run is disbursed -- not a UI check, the backend raises PayrollRunNotDisbursed.">
          <Button busy={issue.isPending} onClick={() => issue.mutate({ runId: r.id as string, key: crypto.randomUUID() })}>Issue payslips</Button>
          {issue.isError && <p role="alert" className="notice notice-danger" style={{ marginTop: 8 }}>{explain(issue.error)}</p>}
        </Action>
      )}
      <section className="panel" aria-label="Payslips on this run">
        <h2>Payslips</h2>
        {payslips.data && payslips.data.rows.length === 0 && <p className="muted">None issued yet.</p>}
        {payslips.data && payslips.data.rows.length > 0 && (
          <div className="table-wrap"><table className="data"><caption className="sr-only">Payslips</caption>
            <thead><tr><th scope="col">Employee</th><th scope="col">Gross</th><th scope="col">Net</th></tr></thead>
            <tbody>{payslips.data.rows.map((p) => <tr key={String(p.id)}><td>{String(p.employee_id).slice(0, 8)}</td><td>{money(p.gross_pay)}</td><td>{money(p.net_pay)}</td></tr>)}</tbody>
          </table></div>
        )}
      </section>

      {canAct && disbursed && (
        <Action title="Statutory filings" blurb="One filing per scheme for the run's jurisdiction (illustrative scheme lists, not a real filing calendar).">
          <Button busy={file.isPending} disabled={!retention}
            onClick={() => retention && file.mutate({ runId: r.id as string, period, retention_class_id: String(retention.id), key: crypto.randomUUID() })}>
            File returns
          </Button>
          {file.isError && <p role="alert" className="notice notice-danger" style={{ marginTop: 8 }}>{explain(file.error)}</p>}
        </Action>
      )}
      <section className="panel" aria-label="Filings">
        <h2>Filings</h2>
        {filings.data && filings.data.rows.filter((f) => f.legal_entity_id === r.legal_entity_id && f.period === period).length === 0 && <p className="muted">None filed yet.</p>}
        {filings.data && filings.data.rows.filter((f) => f.legal_entity_id === r.legal_entity_id && f.period === period).map((f) => (
          <p key={String(f.id)} style={{ margin: '4px 0' }}><Badge tone="ok">{String(f.scheme)}</Badge> filed {shortDate(f.filed_on)}, ack {String(f.acknowledgement_no)}</p>
        ))}
      </section>

      {canAct && disbursed && (
        <Action title="General ledger" blurb="Same create-then-gate shape as disbursal: the row exists before the g_close approval can be requested against it.">
          {!glEntry && <Button busy={openGl.isPending} onClick={() => openGl.mutate({ runId: r.id as string, key: crypto.randomUUID() })}>Open journal entry</Button>}
          {glEntry && !glEntry.posted_at && closeGate && closeGate.status !== 'approved' && (
            <p><GateBadge gateId="g_close" status={closeGate.status} showId={false} /> <Link to={`/approvals/${closeGate.id}`} className="btn btn-quiet">Open the approval</Link></p>
          )}
          {glEntry && !glEntry.posted_at && closeGate && closeGate.status === 'approved' && (
            <Button variant="primary" busy={postGl.isPending} onClick={() => postGl.mutate({ glId: String(glEntry.id), approval_request_id: closeGate.id, key: crypto.randomUUID() })}>Post to GL</Button>
          )}
          {!!glEntry?.posted_at && <p><Badge tone="ok">Posted {shortDate(glEntry.posted_at)}</Badge></p>}
          {openGl.isError && <p role="alert" className="notice notice-danger" style={{ marginTop: 8 }}>{explain(openGl.error)}</p>}
          {postGl.isError && <p role="alert" className="notice notice-danger" style={{ marginTop: 8 }}>{explain(postGl.error)}</p>}
        </Action>
      )}
    </div>
  )
}
