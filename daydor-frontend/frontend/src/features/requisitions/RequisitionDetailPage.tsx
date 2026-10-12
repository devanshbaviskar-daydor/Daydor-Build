import { useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { useRequestConsent, useRequisition } from '../../api/hooks'
import { ApiError, explain } from '../../api/errors'
import { useSession } from '../../api/session'
import { money } from '../../contract'
import { Button, GateBadge } from '../../ui'
import { AuditTrailButton } from '../trail/AuditTrailButton'
import { dateTime, shortDate, StageBadge } from '../shared'
import { ApplicationDialog } from './ApplicationDialog'
import { PipelineCard } from './PipelineCard'

export function RequisitionDetailPage() {
  const { id } = useParams()
  const { session } = useSession()
  const q = useRequisition(id)
  const notice = (useLocation().state as { notice?: string } | null)?.notice
  const [applying, setApplying] = useState(false)
  const [entered, setEntered] = useState(false)
  const requestConsent = useRequestConsent(id ?? '')
  const [consentKey] = useState(() => crypto.randomUUID())

  if (q.isPending) return <p aria-live="polite">Loading…</p>
  if (q.isError || !q.data) {
    const missing = q.error instanceof ApiError && q.error.status === 404
    return (
      <div className="stack"><h1>{missing ? 'Requisition not found' : 'Requisition unavailable'}</h1>
        <p role="alert" className="notice notice-danger">{explain(q.error)}</p>
        <Link to="/requisitions" className="btn btn-quiet" style={{ alignSelf: 'flex-start', paddingLeft: 0 }}>Back to requisitions</Link></div>
    )
  }
  const { requisition: r, pipeline, onboarding, access } = q.data
  const canEnter = access.can_enter_applications && r.stage === 'posted' && pipeline.length === 0
  const title = `${r.job_title ?? 'Requisition'}${r.department_name ? `, ${r.department_name}` : ''}`
  return (
    <div className="stack" style={{ gap: 20 }}>
      <Link to="/requisitions" className="btn btn-quiet" style={{ alignSelf: 'flex-start', paddingLeft: 0 }}>Back to requisitions</Link>
      {notice && <p role="status" className="notice">{notice}</p>}
      <div className="spread">
        <div><h1>{title}</h1><div className="row" style={{ marginTop: 8 }}><StageBadge stage={r.stage} /></div></div>
        <div className="row">
          {canEnter && <Button variant="primary" onClick={() => setApplying(true)}>Enter an application</Button>}
          <AuditTrailButton table="job_requisition" id={r.id} title={`Audit trail: ${title}`} />
        </div>
      </div>
      {entered && <p role="status" className="notice">Application entered. Screening runs in the background; the result appears here in a moment.</p>}

      <section className="panel" aria-labelledby="sum">
        <h2 id="sum">Summary</h2>
        <dl className="grid-2" style={{ margin: 0 }}>
          <div className="field"><dt className="field-label">Hiring manager</dt><dd className="field-value" style={{ margin: 0 }}>{r.hiring_manager_name ?? <span className="restricted">Not visible to your role</span>}</dd></div>
          <div className="field"><dt className="field-label">Target start</dt><dd className="field-value" style={{ margin: 0 }}>{shortDate(r.target_start_date)}</dd></div>
          <div className="field"><dt className="field-label">Pay range</dt><dd className="field-value" style={{ margin: 0 }}>{r.posting ? `${money(r.posting.pay_range_min)} to ${money(r.posting.pay_range_max)} a year` : <span className="restricted">Not posted yet</span>}</dd></div>
          <div className="field"><dt className="field-label">Posting</dt><dd className="field-value" style={{ margin: 0 }}>{r.posting?.posted_at ? `Live since ${dateTime(r.posting.posted_at)} on ${r.posting.channel}` : <span className="restricted">Not live</span>}</dd></div>
        </dl>
        {r.approval && <p style={{ marginTop: 16 }}><GateBadge gateId={r.approval.gate_type} status={r.approval.status} showId={false} /> <Link to={`/approvals/${r.approval.id}`} className="btn btn-quiet">Open the approval</Link></p>}
      </section>

      <section aria-labelledby="pipe" className="stack">
        <h2 id="pipe">Candidate</h2>
        {!access.sees_candidates && <p className="notice">Your role cannot see candidates.</p>}
        {access.sees_candidates && pipeline.length === 0 && (
          <p className="panel muted">{r.stage === 'posted' ? 'No application yet. Each hire takes one candidate through screening, interview and offer.' : 'Candidates appear once the budget is approved and the posting is live.'}</p>
        )}
        {pipeline.map((p) => <PipelineCard key={p.application.id} item={p} role={session!.role} seeCandidates={access.sees_candidates} />)}
      </section>

      {onboarding && (
        <section className="panel" aria-labelledby="onb">
          <h2 id="onb">Onboarding</h2>
          <p className="muted" style={{ fontSize: 14 }}>Employee record created. Background check, documents, work authorization, the onboarding checklist, identity and access are visible on their <Link to={`/people/${onboarding.employee_id}`}>person profile</Link> as each step completes.</p>
          {onboarding.awaiting_consent_request && session?.role === 'tenant_hr' && (
            <div style={{ marginTop: 12 }}>
              <p className="muted" style={{ fontSize: 14 }}>The flow is waiting for the new hire's own DPDP consent before it can continue. Once they've granted it (on their My Privacy page), ask the flow to raise the sign-off.</p>
              <Button onClick={() => requestConsent.mutate(consentKey)} busy={requestConsent.isPending}>Request consent sign-off</Button>
              {requestConsent.isError && <p role="alert" className="notice notice-danger" style={{ marginTop: 8 }}>{explain(requestConsent.error)}</p>}
            </div>
          )}
          {!onboarding.awaiting_consent_request && onboarding.instance_status === 'waiting_gate' && onboarding.instance_state === 's12_consent_record' && (
            <p className="notice" style={{ marginTop: 12 }}>Waiting on the new hire's consent approval.</p>
          )}
        </section>
      )}
      {applying && <ApplicationDialog requisitionId={r.id} onClose={() => setApplying(false)} onDone={() => setEntered(true)} />}
    </div>
  )
}
