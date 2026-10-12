import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'jest-axe'
import { describe, expect, it, vi } from 'vitest'
import hireDefinition from '../mocks/hireDefinition.json'
import { ApprovalCard, AuditDrawer, ConsentRequired, Field, GateBadge, TimerCountdown, WorkflowTimeline, describeRemaining, isPassThrough, orderedStates, whyNot, type ApprovalView, type WorkflowDefinition } from './index'

const def = hireDefinition as unknown as WorkflowDefinition

describe('Field', () => {
  it('shows the value to a role that can read it', () => {
    render(<Field table="work_authorization" column="auth_type" value="I-9" role="tenant_hr" />)
    expect(screen.getByText('I-9')).toBeInTheDocument()
  })
  it('marks masked values', () => {
    render(<Field table="work_authorization" column="auth_type" value="I-9" role="tenant_founder" />)
    expect(screen.getByText('Masked')).toBeInTheDocument()
  })
  it('never draws a value the role cannot see, even when one is passed in', () => {
    const { container } = render(<Field table="work_authorization" column="auth_type" value="SECRET-VALUE" role="tenant_manager" />)
    expect(container).not.toHaveTextContent('SECRET-VALUE')
    expect(screen.getByText('Your role cannot see this.')).toBeInTheDocument()
  })
  it('explains an empty protected value by consent state', () => {
    render(<Field table="employee" column="pan_encrypted" value={null} role="tenant_hr" consent="missing" />)
    expect(screen.getByRole('note')).toHaveTextContent('Not collected until the employee gives consent.')
  })
  it('formats money and dates for India', () => {
    render(<><Field table="position" column="budgeted_cost" value={2400000} role="tenant_hr" currency="INR" /><Field table="position" column="opened_at" value="2026-09-01" role="tenant_hr" /></>)
    expect(screen.getByText('₹24,00,000')).toBeInTheDocument()
    expect(screen.getByText('1 Sept 2026')).toBeInTheDocument()
  })
  it('treats an unknown column as hidden', () => {
    render(<Field table="position" column="nope" value="x" role="tenant_hr" />)
    expect(screen.getByText('Your role cannot see this.')).toBeInTheDocument()
  })
})

describe('GateBadge', () => {
  it('uses the model label, a status word and the id', () => {
    render(<GateBadge gateId="g_requisition_budget" status="pending" />)
    expect(screen.getByText('Requisition budget sign-off')).toBeInTheDocument()
    expect(screen.getByText('Waiting for approval')).toBeInTheDocument()
    expect(screen.getByText('g_requisition_budget')).toBeInTheDocument()
  })
  it('labels soft gates as shadow mode', () => {
    render(<GateBadge gateId="sg_payroll_anomaly_precheck" status="recorded" />)
    expect(screen.getByText('Shadow mode, not applied')).toBeInTheDocument()
  })
})

describe('WorkflowTimeline', () => {
  it('walks the definition in order', () => {
    expect(orderedStates(def)).toEqual(['start', 's01_position', 's02_job_requisition', 's03_approval_request', 's04_job_posting', 's05_application', 's06_screening_result', 's07_interview', 's08_offer', 'done'])
  })
  it('detects pass-through steps', () => {
    expect(isPassThrough(def, 's01_position')).toBe(true)
    expect(isPassThrough(def, 's03_approval_request')).toBe(false)
    expect(isPassThrough(def, 'start')).toBe(false)
  })
  it('shows a paused instance with its gate and earlier steps done', () => {
    render(<WorkflowTimeline definition={def} instance={{ state: 's03_approval_request', status: 'waiting_gate' }} transitions={[]} />)
    const items = screen.getAllByRole('listitem')
    expect(within(items[1]!).getByText('Recorded for the audit trail')).toBeInTheDocument()
    const current = items.find((i) => i.getAttribute('aria-current') === 'step')!
    expect(within(current).getByText('Waiting on a person to approve')).toBeInTheDocument()
    expect(within(current).getByText('Requisition budget sign-off')).toBeInTheDocument()
  })
  it('marks every step done when completed', () => {
    render(<WorkflowTimeline definition={def} instance={{ state: 'done', status: 'completed' }} transitions={[]} />)
    expect(screen.queryByText('not reached')).toBeNull()
  })
})

describe('TimerCountdown', () => {
  const now = new Date('2026-10-08T12:00:00Z')
  it('describes time left and overdue plainly', () => {
    expect(describeRemaining('2026-10-11T12:00:00Z', now)).toEqual({ text: '3 days left', tone: 'warn' })
    expect(describeRemaining('2026-10-20T12:00:00Z', now)).toEqual({ text: '12 days left', tone: 'ok' })
    expect(describeRemaining('2026-10-08T20:00:00Z', now)).toEqual({ text: '8 hours left', tone: 'warn' })
    expect(describeRemaining('2026-10-06T12:00:00Z', now)).toEqual({ text: 'Overdue by 2 days', tone: 'danger' })
  })
  it('renders with a label', () => {
    render(<TimerCountdown dueAt="2026-10-08T20:00:00Z" now={now} label="I-9" />)
    expect(screen.getByText(/I-9:/)).toBeInTheDocument()
  })
})

describe('ApprovalCard', () => {
  const a: ApprovalView = { id: 'a1', gate_type: 'g_requisition_budget', subject_table: 'job_requisition', subject_id: 'abcdef12345', status: 'pending', created_at: '2026-10-08T10:00:00Z', resolved_at: null, decision_note: null, allowed_roles: ['tenant_founder'], requested_by_me: false, can_resolve: true }
  it('offers approve and reject with an optional note when the person can resolve', async () => {
    const onResolve = vi.fn()
    render(<ApprovalCard approval={a} myRole="tenant_founder" onResolve={onResolve} />)
    await userEvent.type(screen.getByLabelText('Note (optional)'), 'Within plan')
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))
    expect(onResolve).toHaveBeenCalledWith('approved', 'Within plan')
  })
  it('explains maker-checker and wrong-role cases instead of showing dead buttons', () => {
    expect(whyNot({ ...a, can_resolve: false, requested_by_me: true }, 'tenant_founder')).toMatch(/someone else has to approve/)
    expect(whyNot({ ...a, can_resolve: false }, 'tenant_hr')).toBe('Waiting for Founder / owner.')
    render(<ApprovalCard approval={{ ...a, can_resolve: false }} myRole="tenant_hr" />)
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull()
    expect(screen.getByText('Waiting for Founder / owner.')).toBeInTheDocument()
  })
  it('shows server errors in an alert', () => {
    render(<ApprovalCard approval={a} myRole="tenant_founder" error="Someone already resolved this request." onResolve={() => {}} />)
    expect(screen.getByRole('alert')).toHaveTextContent('already resolved')
  })
})

describe('AuditDrawer and ConsentRequired', () => {
  it('closes on Escape and on the close button, and starts with focus inside', async () => {
    const onClose = vi.fn()
    render(<AuditDrawer open title="Audit trail" entries={[{ id: '1', at: '2026-10-08T10:00:00Z', actor: 'Rohan', action: 'Approved' }]} onClose={onClose} />)
    expect(screen.getByRole('dialog', { name: 'Audit trail' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus()
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })
  it('says so when nothing is recorded', () => {
    render(<AuditDrawer open title="Audit trail" entries={[]} onClose={() => {}} />)
    expect(screen.getByText('Nothing has been recorded for this yet.')).toBeInTheDocument()
  })
  it('has no automated accessibility violations', async () => {
    const { container } = render(<main><h1>Test</h1><ConsentRequired state="withdrawn" /><GateBadge gateId="g_offer_band" status="approved" /></main>)
    expect(await axe(container)).toHaveNoViolations()
  })
})
