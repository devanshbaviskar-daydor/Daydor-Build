import { useState } from 'react'
import hireDefinition from '../../mocks/hireDefinition.json'
import { roleName, type TableName } from '../../contract'
import {
  ApprovalCard, AuditDrawer, Badge, Button, ConsentRequired, Field, GateBadge, MockAdapterBadge,
  ShadowModeBadge, TimerCountdown, WorkflowTimeline, describeApproval, type ApprovalView, type WorkflowDefinition,
} from '../../ui'

const def = hireDefinition as unknown as WorkflowDefinition
const hours = (h: number) => new Date(Date.now() + h * 3_600_000).toISOString()
const base: ApprovalView = { id: 'demo-1', gate_type: 'g_requisition_budget', subject_table: 'job_requisition', subject_id: 'a1b2c3d4-0000', status: 'pending', created_at: hours(-3), resolved_at: null, decision_note: null, allowed_roles: ['tenant_founder'], requested_by_me: false, can_resolve: true }
const ROLES = ['tenant_hr', 'tenant_founder', 'tenant_manager', 'daydor_admin']

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return <section className="panel" aria-labelledby={`s-${title}`}><h2 id={`s-${title}`}>{title}</h2>{hint && <p className="muted" style={{ fontSize: 14 }}>{hint}</p>}<div className="stack" style={{ marginTop: 14 }}>{children}</div></section>
}

export function PrimitivesPage() {
  const [drawer, setDrawer] = useState(false)
  return (
    <div className="stack" style={{ gap: 24 }}>
      <div><h1>Design primitives</h1><p className="muted" style={{ marginTop: 6 }}>Every shared component in each of its states. Review here before screens use them.</p></div>

      <Section title="Field" hint="The same value, passed to four roles. The model's access levels decide what each person sees; a value a role cannot see is never drawn.">
        <div className="table-wrap"><table className="data"><thead><tr><th>Role</th><th>Work authorization type</th><th>Employee PAN, no consent yet</th><th>Employee PAN, consent withdrawn</th></tr></thead>
          <tbody>{ROLES.map((r) => (
            <tr key={r}><td>{roleName(r)}</td>
              <td><Field table={'work_authorization' as TableName} column="auth_type" value="I-9" role={r} showClass /></td>
              <td><Field table={'employee' as TableName} column="pan_encrypted" value={null} role={r} consent="missing" /></td>
              <td><Field table={'employee' as TableName} column="pan_encrypted" value={null} role={r} consent="withdrawn" /></td></tr>))}</tbody></table></div>
        <div className="grid-2">
          <Field table={'position' as TableName} column="budgeted_cost" value={2400000} role="tenant_hr" currency="INR" label="Budgeted cost (India format)" />
          <Field table={'position' as TableName} column="opened_at" value="2026-09-01" role="tenant_hr" />
          <Field table={'position' as TableName} column="current_employee_id" value={null} role="tenant_hr" label="Current holder" />
        </div>
      </Section>

      <Section title="Gate badge" hint="Status always has a mark and words, never colour alone. Soft gates are labelled as shadow mode.">
        <div className="stack" style={{ gap: 10 }}>
          <GateBadge gateId="g_requisition_budget" status="pending" />
          <GateBadge gateId="g_offer_band" status="approved" />
          <GateBadge gateId="g_bg_adverse" status="rejected" />
          <GateBadge gateId="g_pay_anomaly" status="expired" />
          <GateBadge gateId="sg_payroll_anomaly_precheck" status="recorded" />
          <GateBadge gateId="sg_payroll_anomaly_precheck" status="recorded" mode="enforce" />
        </div>
      </Section>

      <Section title="Workflow timeline" hint="Read from the workflow definition. Pass-through steps are marked as recorded for the audit trail.">
        <div className="row" style={{ alignItems: 'flex-start', gap: 40 }}>
          <div style={{ flex: '1 1 280px' }}><h3 style={{ marginBottom: 10 }}>Paused at a gate</h3>
            <WorkflowTimeline definition={def} instance={{ state: 's03_approval_request', status: 'waiting_gate' }} transitions={[]} /></div>
          <div style={{ flex: '1 1 280px' }}><h3 style={{ marginBottom: 10 }}>Finished</h3>
            <WorkflowTimeline definition={def} instance={{ state: 'done', status: 'completed' }} transitions={[]} /></div>
        </div>
      </Section>

      <Section title="Approval card" hint="What the person can do, or why they cannot.">
        <div className="list">
          <ApprovalCard approval={base} myRole="tenant_founder" onResolve={() => {}} />
          <ApprovalCard approval={{ ...base, id: 'demo-2', can_resolve: false, requested_by_me: true }} myRole="tenant_founder" />
          <ApprovalCard approval={{ ...base, id: 'demo-3', can_resolve: false }} myRole="tenant_hr" />
          <ApprovalCard approval={{ ...base, id: 'demo-4', status: 'approved', can_resolve: false, resolved_at: hours(-1), decision_note: 'Within plan' }} myRole="tenant_founder" />
        </div>
      </Section>

      <Section title="Status line" hint="All a role without workflow access sees: one sentence that stands on its own.">
        <ul className="list" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
          {(['pending', 'approved', 'rejected', 'expired'] as const).map((st) => (
            <li key={st} className="list-row"><span>{describeApproval({ ...base, status: st, resolved_at: st === 'pending' ? null : hours(-1), decision_note: st === 'approved' ? 'Within plan' : null })}</span></li>
          ))}
        </ul>
      </Section>

      <Section title="Consent, timers, honesty badges">
        <div className="row"><ConsentRequired state="missing" /></div>
        <div className="row"><TimerCountdown dueAt={hours(72)} label="I-9" /><TimerCountdown dueAt={hours(20)} label="I-9" /><TimerCountdown dueAt={hours(-30)} label="I-9" /></div>
        <div className="row"><MockAdapterBadge vendor="E-Verify" /><MockAdapterBadge vendor="bank" /><ShadowModeBadge /></div>
      </Section>

      <Section title="Buttons and badges">
        <div className="row"><Button variant="primary">Approve</Button><Button>Save draft</Button><Button variant="danger">Reject</Button><Button variant="quiet">View history</Button><Button variant="primary" busy>Approve</Button><Button disabled>Disabled</Button></div>
        <div className="row"><Badge>Neutral</Badge><Badge tone="accent">Accent</Badge><Badge tone="ok">Done</Badge><Badge tone="warn">Needs attention</Badge><Badge tone="danger">Blocked</Badge><Badge tone="outline">Outline</Badge></div>
      </Section>

      <Section title="Audit drawer">
        <div><Button onClick={() => setDrawer(true)}>Open audit trail</Button></div>
        <AuditDrawer open={drawer} title="Audit trail" onClose={() => setDrawer(false)}
          entries={[{ id: '1', at: hours(-3), actor: 'Requisition approval router', action: 'Raised the budget approval' }, { id: '2', at: hours(-1), actor: 'Rohan Mehta', action: 'Approved the budget' }]} />
      </Section>
    </div>
  )
}
