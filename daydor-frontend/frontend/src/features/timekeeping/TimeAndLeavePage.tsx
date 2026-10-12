import { useState } from 'react'
import { useAccrueLeave, useBuildTimecard, useCreateRow, useElectBenefit, useLookups, useSubmitExpense, useTable } from '../../api/hooks'
import { explain } from '../../api/errors'
import { useSession } from '../../api/session'
import { canReadTable, enumLabel, labelFor, money } from '../../contract'
import { Badge, Button, GateBadge, ModelTable } from '../../ui'
import { dateTime, shortDate } from '../shared'

type Tab = 'time' | 'leave' | 'benefits' | 'expenses'

export function TimeAndLeavePage() {
  const { session } = useSession()
  const role = session!.role
  const me = session!.employee_id ?? null
  const [tab, setTab] = useState<Tab>('time')
  const tabs: { id: Tab; label: string }[] = [
    { id: 'time', label: 'Time' },
    { id: 'leave', label: 'Leave' },
    { id: 'benefits', label: 'Benefits' },
    { id: 'expenses', label: 'Expenses' },
  ]
  return (
    <div className="stack" style={{ gap: 20 }}>
      <h1>Time and leave</h1>
      <div className="tabs" role="group" aria-label="Time and leave">
        {tabs.map((t) => <button key={t.id} type="button" className="tab" aria-pressed={t.id === tab} onClick={() => setTab(t.id)}>{t.label}</button>)}
      </div>
      {tab === 'time' && <TimeTab role={role} me={me} />}
      {tab === 'leave' && <LeaveTab role={role} me={me} />}
      {tab === 'benefits' && <BenefitsTab role={role} me={me} />}
      {tab === 'expenses' && <ExpensesTab me={me} />}
    </div>
  )
}

function TimeTab({ role, me }: { role: string; me: string | null }) {
  const punches = useTable('time_punch', me ? { employee_id: me, limit: '20' } : { employee_id: '-' })
  const timecards = useTable('timecard', me ? { employee_id: me, limit: '20' } : { employee_id: '-' })
  const createPunch = useCreateRow('time_punch')
  const buildTimecard = useBuildTimecard()
  const [punchKey, setPunchKey] = useState(() => crypto.randomUUID())
  const [buildKey, setBuildKey] = useState(() => crypto.randomUUID())
  const [period, setPeriod] = useState({ start: '', end: '' })

  const punch = (kind: 'in' | 'out') => {
    if (!me) return
    setPunchKey(crypto.randomUUID())
    createPunch.mutate({ values: { employee_id: me, punched_at: new Date().toISOString(), kind, source: 'web' }, key: punchKey })
  }
  if (!me) return <p className="notice">Time punches are self-service; your role has no employee record to punch for.</p>
  const lastPunch = punches.data?.rows[0]
  const clockedIn = lastPunch?.kind === 'in'
  return (
    <div className="stack" style={{ gap: 20 }}>
      <section className="panel">
        <h2>Punch</h2>
        <p className="muted" style={{ fontSize: 14 }}>{clockedIn ? 'You are clocked in.' : 'You are clocked out.'} {lastPunch ? `Last punch ${dateTime(lastPunch.punched_at)}.` : ''}</p>
        <div className="row" style={{ marginTop: 8 }}>
          <Button variant="primary" disabled={clockedIn} busy={createPunch.isPending} onClick={() => punch('in')}>Punch in</Button>
          <Button disabled={!clockedIn} busy={createPunch.isPending} onClick={() => punch('out')}>Punch out</Button>
        </div>
        {createPunch.isError && <p role="alert" className="notice notice-danger" style={{ marginTop: 8 }}>{explain(createPunch.error)}</p>}
      </section>
      <section className="panel">
        <h2>Build a timecard</h2>
        <p className="muted" style={{ fontSize: 14 }}>Turns this period's punches into a timecard and sends it to your manager for approval (g_timecard). There's no in-between: once built, it always needs sign-off.</p>
        <div className="row" style={{ alignItems: 'flex-end', marginTop: 8 }}>
          <div><label className="label" htmlFor="pstart">Period start</label><input id="pstart" className="input" type="date" value={period.start} onChange={(e) => setPeriod((p) => ({ ...p, start: e.target.value }))} /></div>
          <div><label className="label" htmlFor="pend">Period end</label><input id="pend" className="input" type="date" value={period.end} onChange={(e) => setPeriod((p) => ({ ...p, end: e.target.value }))} /></div>
          <Button busy={buildTimecard.isPending} disabled={!period.start || !period.end}
            onClick={() => { setBuildKey(crypto.randomUUID()); buildTimecard.mutate({ body: { employee_id: me, period_start: period.start, period_end: period.end }, key: buildKey }) }}>
            Build timecard
          </Button>
        </div>
        {buildTimecard.isError && <p role="alert" className="notice notice-danger" style={{ marginTop: 8 }}>{explain(buildTimecard.error)}</p>}
        {buildTimecard.isSuccess && <p role="status" className="notice" style={{ marginTop: 8 }}>Timecard built and sent for approval.</p>}
      </section>
      <section className="panel" aria-label="Your timecards">
        <h2>Your timecards</h2>
        {timecards.isPending && <p>Loading…</p>}
        {timecards.data && (
          <ModelTable table="timecard" caption="Your timecards" role={role} rows={timecards.data.rows}
            columns={['period_start', 'period_end', 'regular_hours', 'overtime_hours', 'status']}
            cells={{
              period_start: (r) => shortDate(r.period_start), period_end: (r) => shortDate(r.period_end),
              status: (r) => <Badge tone={r.status === 'approved' ? 'ok' : r.status === 'rejected' ? 'danger' : 'warn'}>{enumLabel('timecard', 'status', String(r.status))}</Badge>,
            }}
            empty="No timecards yet." />
        )}
      </section>
      {punches.data && (
        <section className="panel" aria-label="Recent punches">
          <h2>Recent punches</h2>
          <ModelTable table="time_punch" caption="Recent punches" role={role} rows={punches.data.rows} columns={['punched_at', 'kind', 'source']}
            cells={{ punched_at: (r) => dateTime(r.punched_at), kind: (r) => <Badge tone={r.kind === 'in' ? 'ok' : 'neutral'}>{String(r.kind)}</Badge> }}
            empty="No punches yet." />
        </section>
      )}
    </div>
  )
}

function LeaveTab({ role, me }: { role: string; me: string | null }) {
  const balances = useTable('leave_balance', me ? { employee_id: me, limit: '20' } : { employee_id: '-' })
  const { lookups } = useLookups(['leave_policy'])
  const accrue = useAccrueLeave()
  const canAccrue = role === 'tenant_hr' || role === 'tenant_founder' || role === 'daydor_ops'
  const policies = Object.values(lookups.leave_policy ?? {})
  const [policyId, setPolicyId] = useState('')
  if (!me && !canAccrue) return <p className="notice">Your role has no leave balance to show.</p>
  return (
    <div className="stack" style={{ gap: 20 }}>
      {canAccrue && (
        <section className="panel">
          <h2>Run accrual</h2>
          <p className="muted" style={{ fontSize: 14 }}>No scheduler runs this automatically yet; HR/ops triggers it for an employee against a leave policy, as of today.</p>
          <div className="row" style={{ marginTop: 8, alignItems: 'flex-end' }}>
            <div><label className="label" htmlFor="policy">Leave policy</label>
              <select id="policy" className="input" value={policyId} onChange={(e) => setPolicyId(e.target.value)}>
                <option value="">Choose…</option>{policies.map((p) => <option key={String(p.id)} value={String(p.id)}>{labelFor('leave_policy', p)}</option>)}
              </select>
            </div>
            <Button disabled={!policyId || !me} busy={accrue.isPending}
              onClick={() => me && accrue.mutate({ employee_id: me, leave_policy_id: policyId, as_of: new Date().toISOString().slice(0, 10) })}>
              Accrue for me
            </Button>
          </div>
          {accrue.isError && <p role="alert" className="notice notice-danger" style={{ marginTop: 8 }}>{explain(accrue.error)}</p>}
        </section>
      )}
      {me && (
        <section className="panel" aria-label="Your leave balances">
          <h2>Your leave balances</h2>
          {balances.isPending && <p>Loading…</p>}
          {balances.data && (
            <ModelTable table="leave_balance" caption="Your leave balances" role={role} rows={balances.data.rows}
              columns={['leave_policy_id', 'balance_days', 'as_of']} lookups={lookups}
              cells={{ as_of: (r) => shortDate(r.as_of) }} empty="No leave accrued yet." />
          )}
        </section>
      )}
    </div>
  )
}

function BenefitsTab({ role, me }: { role: string; me: string | null }) {
  const elections = useTable('benefit_election', me ? { employee_id: me, limit: '20' } : { employee_id: '-' })
  const { lookups } = useLookups(['benefit_plan'])
  const elect = useElectBenefit()
  const [key, setKey] = useState(() => crypto.randomUUID())
  const plans = Object.values(lookups.benefit_plan ?? {})
  const [form, setForm] = useState({ plan: '', tier: 'self', cost: '', from: '' })
  if (!me) return <p className="notice">Benefit elections are for employees.</p>
  return (
    <div className="stack" style={{ gap: 20 }}>
      <section className="panel">
        <h2>Elect a benefit</h2>
        <p className="muted" style={{ fontSize: 14 }}>You choose; an agent processes and records the election, not your own session directly (the model's table grant looks like self-service, but coverage tier and cost are a more sensitive class than that).</p>
        <div className="row" style={{ marginTop: 8, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div><label className="label" htmlFor="plan">Plan</label>
            <select id="plan" className="input" value={form.plan} onChange={(e) => setForm((f) => ({ ...f, plan: e.target.value }))}>
              <option value="">Choose…</option>{plans.map((p) => <option key={String(p.id)} value={String(p.id)}>{labelFor('benefit_plan', p)}</option>)}
            </select>
          </div>
          <div><label className="label" htmlFor="tier">Coverage tier</label><input id="tier" className="input" value={form.tier} onChange={(e) => setForm((f) => ({ ...f, tier: e.target.value }))} /></div>
          <div><label className="label" htmlFor="cost">Your cost (₹ a month)</label><input id="cost" className="input" type="number" value={form.cost} onChange={(e) => setForm((f) => ({ ...f, cost: e.target.value }))} /></div>
          <div><label className="label" htmlFor="from">Effective from</label><input id="from" className="input" type="date" value={form.from} onChange={(e) => setForm((f) => ({ ...f, from: e.target.value }))} /></div>
          <Button disabled={!form.plan || !form.cost || !form.from} busy={elect.isPending}
            onClick={() => { setKey(crypto.randomUUID()); elect.mutate({ body: { employee_id: me, benefit_plan_id: form.plan, coverage_tier: form.tier, employee_cost: Number(form.cost), effective_from: form.from }, key }) }}>
            Elect
          </Button>
        </div>
        {elect.isError && <p role="alert" className="notice notice-danger" style={{ marginTop: 8 }}>{explain(elect.error)}</p>}
      </section>
      <section className="panel" aria-label="Your benefit elections">
        <h2>Your elections</h2>
        {elections.isPending && <p>Loading…</p>}
        {elections.data && (
          <ModelTable table="benefit_election" caption="Your benefit elections" role={role} rows={elections.data.rows} lookups={lookups}
            columns={['benefit_plan_id', 'coverage_tier', 'employee_cost', 'effective_from']}
            cells={{ employee_cost: (r) => money(r.employee_cost), effective_from: (r) => shortDate(r.effective_from) }}
            empty="No elections yet." />
        )}
      </section>
    </div>
  )
}

function ExpensesTab({ me }: { me: string | null }) {
  const expenses = useTable('expense', { limit: '20' })
  const submit = useSubmitExpense()
  const [key, setKey] = useState(() => crypto.randomUUID())
  const [form, setForm] = useState({ amount: '', category: '' })
  if (!me) return <p className="notice">Expenses are for employees.</p>
  return (
    <div className="stack" style={{ gap: 20 }}>
      <section className="panel">
        <h2>Submit an expense</h2>
        <p className="muted" style={{ fontSize: 14 }}>No backend worker exists for expenses yet (the model names one but it was never built); this submits and raises its g_expense approval in one step, for your manager to resolve.</p>
        <div className="row" style={{ marginTop: 8, alignItems: 'flex-end' }}>
          <div><label className="label" htmlFor="amount">Amount (₹)</label><input id="amount" className="input" type="number" value={form.amount} onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))} /></div>
          <div><label className="label" htmlFor="category">Category</label><input id="category" className="input" value={form.category} onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))} /></div>
          <Button disabled={!form.amount || !form.category} busy={submit.isPending}
            onClick={() => { setKey(crypto.randomUUID()); submit.mutate({ body: { amount: Number(form.amount), category: form.category }, key }, { onSuccess: () => setForm({ amount: '', category: '' }) }) }}>
            Submit
          </Button>
        </div>
        {submit.isError && <p role="alert" className="notice notice-danger" style={{ marginTop: 8 }}>{explain(submit.error)}</p>}
        {submit.isSuccess && <p role="status" className="notice" style={{ marginTop: 8 }}>Submitted and sent to your manager.</p>}
      </section>
      {canReadTable('expense', 'tenant_employee') && expenses.data && (
        <section className="panel" aria-label="Expenses">
          <h2>Expenses</h2>
          <ModelTable table="expense" caption="Expenses" role="tenant_employee" rows={expenses.data.rows}
            columns={['amount', 'category', 'approval_request_id', 'reimbursed_at']}
            cells={{
              amount: (r) => money(r.amount), reimbursed_at: (r) => r.reimbursed_at ? shortDate(r.reimbursed_at) : <Badge tone="warn">Not yet</Badge>,
              approval_request_id: (r) => r.approval_request_id ? <GateBadge gateId="g_expense" status="pending" showId={false} /> : <span className="muted">—</span>,
            }}
            empty="No expenses yet." />
        </section>
      )}
    </div>
  )
}
