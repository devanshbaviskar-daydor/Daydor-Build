import { Link, useParams } from 'react-router-dom'
import {
  useApprovalsFor, useDeprovision, useDisburseFinalSettlement, useSendCobraNotice, useTable,
} from '../../api/hooks'
import { ApiError, explain } from '../../api/errors'
import { useSession } from '../../api/session'
import { labelFor } from '../../contract'
import { Badge, Button, GateBadge } from '../../ui'
import { shortDate } from '../shared'

/** Everything here runs automatically once the termination is created except three steps gated by
 *  a column on a row other than the termination itself -- deprovisioning (g_it_deprov on
 *  identity_account), final-settlement disbursal (g_pay_disburse on final_settlement) and the
 *  COBRA notice (g_cobra on cobra_event) -- so those are the only actions this page offers
 *  (daydor.exit.workflow's module docstring; same create-then-gate shape as Payroll's disbursal). */
export function ExitDetailPage() {
  const { id } = useParams()
  const { session } = useSession()
  const role = session!.role
  const termination = useTable('termination', id ? { id } : { id: '-' })
  const t = termination.data?.rows[0]
  const employeeId = t ? String(t.employee_id) : '-'

  const employee = useTable('employee', { id: employeeId })
  const terminationApprovals = useApprovalsFor(id)
  const checklist = useTable('checklist', { employee_id: employeeId, kind: 'termination' })
  const checklistId = checklist.data?.rows[0] ? String(checklist.data.rows[0].id) : '-'
  const tasks = useTable('checklist_task', { checklist_id: checklistId })
  const identity = useTable('identity_account', { employee_id: employeeId })
  const identityAccount = identity.data?.rows[0]
  const identityApprovals = useApprovalsFor(identityAccount ? String(identityAccount.id) : undefined)
  const devices = useTable('device_assignment', { employee_id: employeeId })
  const settlement = useTable('final_settlement', { employee_id: employeeId })
  const finalSettlement = settlement.data?.rows[0]
  const settlementApprovals = useApprovalsFor(finalSettlement ? String(finalSettlement.id) : undefined)
  const cobra = useTable('cobra_event', { employee_id: employeeId })
  const cobraEvent = cobra.data?.rows[0]
  const cobraApprovals = useApprovalsFor(cobraEvent ? String(cobraEvent.id) : undefined)

  const deprovision = useDeprovision()
  const disburse = useDisburseFinalSettlement()
  const sendNotice = useSendCobraNotice()

  if (termination.isPending) return <p aria-live="polite">Loading…</p>
  if (termination.isError || !t) {
    const missing = termination.error instanceof ApiError && termination.error.status === 404
    return (
      <div className="stack"><h1>{missing ? 'Termination not found' : 'Termination unavailable'}</h1>
        <p role="alert" className="notice notice-danger">{explain(termination.error)}</p>
        <Link to="/exit" className="btn btn-quiet" style={{ alignSelf: 'flex-start', paddingLeft: 0 }}>Back to exit</Link></div>
    )
  }
  const emp = employee.data?.rows[0]
  const closed = emp?.is_active === false

  const legalHoldGate = (terminationApprovals.data?.approvals ?? []).find((a) => a.gate_type === 'g_legalhold')
  const finalPayGate = (terminationApprovals.data?.approvals ?? []).find((a) => a.gate_type === 'g_finalpay')
  const deprovGate = (identityApprovals.data?.approvals ?? []).find((a) => a.gate_type === 'g_it_deprov')
  const disburseGate = (settlementApprovals.data?.approvals ?? []).find((a) => a.gate_type === 'g_pay_disburse')
  const cobraGate = (cobraApprovals.data?.approvals ?? []).find((a) => a.gate_type === 'g_cobra')

  const canDeprovision = role === 'tenant_it' || role === 'daydor_ops'
  const canDisburse = role === 'tenant_payroll' || role === 'tenant_founder' || role === 'daydor_ops'
  const canSendCobra = role === 'tenant_hr'

  return (
    <div className="stack" style={{ gap: 20 }}>
      <Link to="/exit" className="btn btn-quiet" style={{ alignSelf: 'flex-start', paddingLeft: 0 }}>Back to exit</Link>
      <div><h1>{emp ? labelFor('employee', emp) : 'Termination'}</h1>
        <p className="muted">{String(t.termination_type)} · {String(t.reason_code)} · last working day {shortDate(t.last_working_day)}</p></div>

      <section className="panel">
        <h2>Status</h2>
        <p>{closed ? <Badge tone="ok">Closed out {shortDate(emp?.date_of_exit)}</Badge> : <Badge tone="warn">In progress</Badge>}</p>
        {legalHoldGate && (
          <p style={{ marginTop: 10 }}><GateBadge gateId="g_legalhold" status={legalHoldGate.status} showId={false} /> {legalHoldGate.status === 'pending' && <Link to={`/approvals/${legalHoldGate.id}`} className="btn btn-quiet">Open the approval</Link>}</p>
        )}
      </section>

      <section className="panel" aria-label="Termination checklist">
        <h2>Checklist</h2>
        {checklist.data && checklist.data.rows.length === 0 && <p className="muted">Not built yet.</p>}
        {tasks.data && tasks.data.rows.length > 0 && (
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {tasks.data.rows.map((task) => (
              <li key={String(task.id)}>{String(task.title)} <span className="muted">({String(task.owner_domain)}{task.blocking ? ', blocking' : ''})</span> — {task.completed_at ? <Badge tone="ok">Done</Badge> : <Badge tone="neutral">{String(task.status)}</Badge>}</li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel" aria-label="Identity and access">
        <h2>Deprovisioning</h2>
        {!identityAccount && <p className="muted">No identity account on file.</p>}
        {!!identityAccount?.deprovisioned_at && <p><Badge tone="ok">Deprovisioned {shortDate(identityAccount.deprovisioned_at)}</Badge></p>}
        {identityAccount && !identityAccount.deprovisioned_at && (
          <>
            {!deprovGate && <p className="muted">Waiting for the deprovisioning agent to raise its approval.</p>}
            {deprovGate && deprovGate.status !== 'approved' && <p><GateBadge gateId="g_it_deprov" status={deprovGate.status} showId={false} /> <Link to={`/approvals/${deprovGate.id}`} className="btn btn-quiet">Open the approval</Link></p>}
            {canDeprovision && deprovGate && deprovGate.status === 'approved' && (
              <div style={{ marginTop: 10 }}>
                <Button variant="primary" busy={deprovision.isPending}
                  onClick={() => deprovision.mutate({ identityAccountId: String(identityAccount.id), approval_request_id: deprovGate.id, key: crypto.randomUUID() })}>
                  Deprovision
                </Button>
                {deprovision.isError && <p role="alert" className="notice notice-danger" style={{ marginTop: 8 }}>{explain(deprovision.error)}</p>}
              </div>
            )}
          </>
        )}
      </section>

      <section className="panel" aria-label="Device return">
        <h2>Devices</h2>
        {devices.data && devices.data.rows.length === 0 && <p className="muted">No devices assigned.</p>}
        {devices.data && devices.data.rows.length > 0 && (
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {devices.data.rows.map((d) => (
              <li key={String(d.id)}>{d.returned_at ? <Badge tone="ok">Returned {shortDate(d.returned_at)}</Badge> : <Badge tone="warn">Not yet returned</Badge>}</li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel" aria-label="Final settlement">
        <h2>Final settlement</h2>
        {!finalSettlement && <p className="muted">Not calculated yet.</p>}
        {finalSettlement && (
          <>
            <dl className="grid-2" style={{ margin: 0 }}>
              <div className="field"><dt className="field-label">Pending wages</dt><dd className="field-value" style={{ margin: 0 }}>{String(finalSettlement.pending_wages)}</dd></div>
              <div className="field"><dt className="field-label">Gratuity payout</dt><dd className="field-value" style={{ margin: 0 }}>{String(finalSettlement.gratuity_payout)}</dd></div>
              <div className="field"><dt className="field-label">Leave encashment</dt><dd className="field-value" style={{ margin: 0 }}>{String(finalSettlement.leave_encashment)}</dd></div>
              <div className="field"><dt className="field-label">Total</dt><dd className="field-value" style={{ margin: 0 }}>{String(finalSettlement.total_settlement)}</dd></div>
            </dl>
            {finalPayGate && (
              <p style={{ marginTop: 10 }}><GateBadge gateId="g_finalpay" status={finalPayGate.status} showId={false} /> {finalPayGate.status === 'pending' && <Link to={`/approvals/${finalPayGate.id}`} className="btn btn-quiet">Open the approval</Link>}</p>
            )}
            {finalSettlement.disbursed_at && <p style={{ marginTop: 10 }}><Badge tone="ok">Disbursed {shortDate(finalSettlement.disbursed_at)}</Badge></p>}
            {!finalSettlement.disbursed_at && (
              <>
                {!disburseGate && <p className="muted">Waiting for the disbursal agent to raise its approval.</p>}
                {disburseGate && disburseGate.status !== 'approved' && <p><GateBadge gateId="g_pay_disburse" status={disburseGate.status} showId={false} /> <Link to={`/approvals/${disburseGate.id}`} className="btn btn-quiet">Open the approval</Link></p>}
                {canDisburse && disburseGate && disburseGate.status === 'approved' && (
                  <div style={{ marginTop: 10 }}>
                    <Button variant="primary" busy={disburse.isPending}
                      onClick={() => disburse.mutate({ finalSettlementId: String(finalSettlement.id), approval_request_id: disburseGate.id, key: crypto.randomUUID() })}>
                      Disburse
                    </Button>
                    {disburse.isError && <p role="alert" className="notice notice-danger" style={{ marginTop: 8 }}>{explain(disburse.error)}</p>}
                  </div>
                )}
              </>
            )}
          </>
        )}
      </section>

      {cobraEvent && (
        <section className="panel" aria-label="COBRA">
          <h2>COBRA</h2>
          <p className="muted" style={{ fontSize: 14 }}>US-only: a qualifying event that starts the notice clock.</p>
          {!!cobraEvent.notice_sent_at && <p><Badge tone="ok">Notice sent {shortDate(cobraEvent.notice_sent_at)}</Badge></p>}
          {!cobraEvent.notice_sent_at && (
            <>
              {!cobraGate && <p className="muted">Waiting for the trigger detector to raise its approval.</p>}
              {cobraGate && cobraGate.status !== 'approved' && <p><GateBadge gateId="g_cobra" status={cobraGate.status} showId={false} /> <Link to={`/approvals/${cobraGate.id}`} className="btn btn-quiet">Open the approval</Link></p>}
              {canSendCobra && cobraGate && cobraGate.status === 'approved' && (
                <div style={{ marginTop: 10 }}>
                  <Button variant="primary" busy={sendNotice.isPending}
                    onClick={() => sendNotice.mutate({ cobraEventId: String(cobraEvent.id), approval_request_id: cobraGate.id, key: crypto.randomUUID() })}>
                    Send COBRA notice
                  </Button>
                  {sendNotice.isError && <p role="alert" className="notice notice-danger" style={{ marginTop: 8 }}>{explain(sendNotice.error)}</p>}
                </div>
              )}
            </>
          )}
        </section>
      )}
    </div>
  )
}
