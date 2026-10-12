// Runs the frontend's own client against a real API, worker and Postgres. Skipped unless
// DAYDOR_LIVE_API is set (see docs/fe-0-demo-script.md). This is the FE-0 exit check.
import { beforeEach, describe, expect, it } from 'vitest'
import { api, setTokenProvider } from './client'
import { configureTransport } from './transport'

const base = process.env.DAYDOR_LIVE_API
type Approval = { id: string; subject_id: string; gate_type: string; can_resolve: boolean; status: string }

async function until<T>(fn: () => Promise<T | undefined>, what: string, ms = 20_000): Promise<T> {
  const end = Date.now() + ms
  while (Date.now() < end) {
    const v = await fn()
    if (v !== undefined) return v
    await new Promise((r) => setTimeout(r, 500))
  }
  throw new Error(`timed out waiting for ${what}`)
}

/** A fresh open seat for this run: a position can only have one hire in progress. The hiring
 *  manager is always Meera Iyer, the seeded manager -- picking `/tables/employee`'s first row
 *  used to work by accident (nothing else ever became an employee live), but Phase 2 makes real
 *  hires complete far enough to create new employee rows, so an unfiltered pick is no longer
 *  stable run over run. */
async function freshSeat() {
  const open = (await api.get<{ rows: { department_id: string; job_profile_id: string }[] }>('/tables/position?status=open')).rows[0]!
  const seat = await api.post<{ id: string }>('/tables/position', { department_id: open.department_id, job_profile_id: open.job_profile_id, status: 'open', budgeted_fte: 1, budgeted_cost: 1800000, opened_at: '2026-10-01' })
  const manager = (await api.get<{ rows: { id: string; work_email: string }[] }>('/tables/employee')).rows.find((r) => r.work_email === 'meera.iyer@acme.test')!
  return { positionId: seat.id, managerId: manager.id }
}

describe.skipIf(!base)('live API through the same client the screens use', () => {
  // The global setup resets to mock before every test, so switch to live after it, per test.
  beforeEach(() => configureTransport({ defaultMode: 'live', overrides: {}, base: base ?? '' }))

  const signIn = async (email: string) => {
    const r = await api.post<{ token: string; session: { role: string } }>('/auth/dev-login', { email })
    setTokenProvider(() => r.token)
    return r.session
  }

  it('signs in, starts a hire, approves it as the founder, and the workflow moves on', { timeout: 40_000 }, async () => {
    const hr = await signIn('kavya.menon@acme.test')
    expect(hr.role).toBe('tenant_hr')

    const { positionId, managerId } = await freshSeat()
    const started = await api.post<{ instance_id: string; requisition_id: string }>('/hire/start', {
      position_id: positionId, hiring_manager_id: managerId, target_start_date: '2026-12-01', pay_range_min: 1800000, pay_range_max: 2600000,
    })

    await signIn('rohan.mehta@acme.test')
    const approval = await until(async () => {
      const list = await api.get<{ approvals: Approval[] }>('/approvals?status=pending')
      return list.approvals.find((a) => a.subject_id === started.requisition_id)
    }, 'the budget approval to be raised by the queue worker')
    expect(approval.gate_type).toBe('g_requisition_budget')
    expect(approval.can_resolve).toBe(true)

    await api.post(`/approvals/${approval.id}/resolve`, { decision: 'approved', note: 'Within plan' })
    const wf = await until(async () => {
      const r = await api.get<{ instance: { state: string; status: string } }>(`/workflows/instances/${started.instance_id}`)
      return r.instance.state === 's04_job_posting' ? r : undefined
    }, 'the workflow to move to job posting')
    expect(wf.instance.status).toBe('running')
  })

  it('returns the same error codes the mock does', async () => {
    await signIn('arjun.rao@acme.test')
    await expect(api.get('/tables/position')).rejects.toMatchObject({ status: 403, code: 'forbidden' })
    await expect(api.get('/workflows/instances')).rejects.toMatchObject({ status: 403, code: 'workflow_not_visible' })
    await signIn('kavya.menon@acme.test')
    await expect(api.post('/hire/start', { position_id: '00000000-0000-0000-0000-000000000000', hiring_manager_id: '00000000-0000-0000-0000-000000000000', target_start_date: '2026-12-01', pay_range_min: 1, pay_range_max: 2 })).rejects.toMatchObject({ status: 409, code: 'no_open_seat' })
  })

  it('FE-1: links an approval to its workflow, shows the trail, and limits what other roles see', { timeout: 40_000 }, async () => {
    await signIn('kavya.menon@acme.test')
    const { positionId, managerId } = await freshSeat()
    const body = { position_id: positionId, hiring_manager_id: managerId, target_start_date: '2026-12-01', pay_range_min: 1800000, pay_range_max: 2600000 }
    const started = await api.post<{ instance_id: string; requisition_id: string }>('/hire/start', body)
    const again = await api.post<{ instance_id: string; existing?: boolean }>('/hire/start', body)
    expect(again).toMatchObject({ instance_id: started.instance_id, existing: true })

    const hr = await api.get<{ capabilities: { workflow_timeline: boolean } }>('/auth/me')
    expect(hr.capabilities.workflow_timeline).toBe(true)

    await signIn('rohan.mehta@acme.test')
    const approval = await until(async () => (await api.get<{ approvals: Approval[] }>('/approvals?status=pending')).approvals.find((a) => a.subject_id === started.requisition_id), 'the approval')
    const detail = await api.get<Approval & { workflow_instance_id: string | null }>(`/approvals/${approval.id}`)
    expect(detail.workflow_instance_id).toBe(started.instance_id)
    const parked = await api.get<{ instance: { state: string; status: string }; transitions: { outcome: string }[] }>(`/workflows/instances/${started.instance_id}`)
    expect(parked.instance).toMatchObject({ state: 's03_approval_request', status: 'waiting_gate' })
    expect(parked.transitions.map((t) => t.outcome)).toEqual(['moved', 'moved', 'moved', 'waiting_gate'])

    await api.post(`/approvals/${approval.id}/resolve`, { decision: 'approved', note: 'Within plan' })
    await until(async () => ((await api.get<{ instance: { state: string } }>(`/workflows/instances/${started.instance_id}`)).instance.state === 's04_job_posting' ? true : undefined), 'the workflow to move on')

    const trail = await api.get<{ entries: { actor: string; action: string }[]; sources: { workflow: boolean } }>(`/audit/subject?table=job_requisition&id=${started.requisition_id}`)
    const actions = trail.entries.map((e) => e.action)
    expect(actions).toContain('Asked for approval: Requisition budget sign-off')
    expect(actions).toContain('Approved: Requisition budget sign-off. Note: Within plan')
    expect(actions).toContain('Moved from approval request to job posting')
    expect(trail.entries.find((e) => e.action.startsWith('Approved:'))!.actor).toBe('You')

    await signIn('meera.iyer@acme.test')            // a manager: approvals yes, workflow tables no
    const mgr = await api.get<{ workflow_instance_id: string | null }>(`/approvals/${approval.id}`)
    expect(mgr.workflow_instance_id).toBeNull()
    await expect(api.get('/evaluations')).rejects.toMatchObject({ status: 403, code: 'evaluation_not_visible' })
    const mgrTrail = await api.get<{ entries: { actor: string }[]; sources: { workflow: boolean } }>(`/audit/subject?table=job_requisition&id=${started.requisition_id}`)
    expect(mgrTrail.sources.workflow).toBe(false)
    expect(mgrTrail.entries.every((e) => e.actor !== 'Rohan Mehta')).toBe(true)   // names stay hidden from this role
  })

  /** Start a hire for a fresh seat with the comp band and interview details the backend's later steps read. */
  async function startFullHire(proposedBase: number, extra: Record<string, unknown> = {}) {
    await signIn('kavya.menon@acme.test')
    const { positionId, managerId } = await freshSeat()
    const band = (await api.get<{ rows: { id: string }[] }>('/tables/comp_band')).rows[0]!
    const started = await api.post<{ instance_id: string; requisition_id: string }>('/hire/start', {
      position_id: positionId, hiring_manager_id: managerId, target_start_date: '2026-12-01', channel: 'company_site', pay_range_min: 1800000, pay_range_max: 2600000,
      interviewer_employee_id: managerId, scheduled_at: '2026-11-10T10:00:00Z', comp_band_id: band.id, proposed_base: proposedBase, ...extra,
    })
    const list = await api.get<{ requisitions: { id: string; stage: string; job_title: string }[] }>('/hire/requisitions')
    // Until the queue worker raises the budget approval the requisition is briefly just a draft.
    const mine = list.requisitions.find((r) => r.id === started.requisition_id)!
    expect(['drafting', 'awaiting_budget_approval']).toContain(mine.stage)
    expect(mine.job_title).toBe('Backend Engineer')
    return started
  }
  const approvePending = async (email: string, requisitionId: string, gate: string) => {
    await signIn(email)
    const a = await until(async () => (await api.get<{ approvals: Approval[] }>(`/approvals?status=pending&subject_id=${requisitionId}`)).approvals.find((x) => x.gate_type === gate), `the ${gate} approval`)
    expect(a.can_resolve).toBe(true)
    await api.post(`/approvals/${a.id}/resolve`, { decision: 'approved', note: 'ok' })
  }
  type Pipe = { pipeline: { candidate: { full_name: string } | null; screening: { recommendation: string; approval: { status: string; gate_type: string } | null } | null; interview: { interviewer_name: string | null } | null; offer: { within_band: boolean; approval: { status: string; gate_type: string } | null } | null }[]; requisition: { stage: string } }
  const detail = (id: string) => api.get<Pipe>(`/hire/requisitions/${id}`)

  it('FE-2 and FE-3: opens a requisition, posts it, screens a candidate and makes an in-band offer', { timeout: 60_000 }, async () => {
    const started = await startFullHire(2400000)
    await approvePending('rohan.mehta@acme.test', started.requisition_id, 'g_requisition_budget')

    await signIn('kavya.menon@acme.test')
    await until(async () => ((await detail(started.requisition_id)).requisition.stage === 'posted' ? true : undefined), 'the posting to go live')
    const applied = await api.post<{ status: string }>(`/hire/requisitions/${started.requisition_id}/applications`, { full_name: 'Neha Gupta', email: `neha.${Date.now()}@example.test`, phone: '+91 98450 00000' })
    expect(applied.status).toBe('queued')
    const screened = await until(async () => { const d = await detail(started.requisition_id); return d.pipeline[0]?.screening?.approval ? d : undefined }, 'the screening result')
    expect(screened.pipeline[0]!.candidate!.full_name).toBe('Neha Gupta')
    expect(screened.pipeline[0]!.screening!.approval).toMatchObject({ gate_type: 'g_aedt', status: 'pending' })

    await approvePending('kavya.menon@acme.test', started.requisition_id, 'g_aedt')
    const done = await until(async () => { const d = await detail(started.requisition_id); return d.pipeline[0]?.offer ? d : undefined }, 'the offer')
    expect(done.pipeline[0]!.interview!.interviewer_name).toBe('Meera Iyer')
    expect(done.pipeline[0]!.offer).toMatchObject({ within_band: true, approval: null })

    await signIn('meera.iyer@acme.test')                      // a hiring manager sees the pipeline but not who the candidate is
    const mgr = await detail(started.requisition_id)
    expect(mgr.pipeline[0]!.candidate).toBeNull()
    expect(mgr.pipeline[0]!.offer).toBeTruthy()
  })

  it('FE-3: an out-of-band offer waits for the founder', { timeout: 60_000 }, async () => {
    const started = await startFullHire(4500000)
    await approvePending('rohan.mehta@acme.test', started.requisition_id, 'g_requisition_budget')
    await signIn('kavya.menon@acme.test')
    await until(async () => ((await detail(started.requisition_id)).requisition.stage === 'posted' ? true : undefined), 'the posting')
    await api.post(`/hire/requisitions/${started.requisition_id}/applications`, { full_name: 'Karthik Rao', email: `karthik.${Date.now()}@example.test`, phone: '+91 98450 12345' })
    await until(async () => ((await detail(started.requisition_id)).pipeline[0]?.screening?.approval ? true : undefined), 'the screening')
    await approvePending('kavya.menon@acme.test', started.requisition_id, 'g_aedt')
    await signIn('kavya.menon@acme.test')
    const waiting = await until(async () => { const d = await detail(started.requisition_id); return d.pipeline[0]?.offer?.approval ? d : undefined }, 'the out-of-band approval')
    expect(waiting.pipeline[0]!.offer).toMatchObject({ within_band: false, approval: { gate_type: 'g_offer_band', status: 'pending' } })
    await approvePending('rohan.mehta@acme.test', started.requisition_id, 'g_offer_band')
    await signIn('kavya.menon@acme.test')
    const cleared = await until(async () => { const d = await detail(started.requisition_id); return d.pipeline[0]?.offer?.approval?.status === 'approved' ? d : undefined }, 'the approval to clear')
    expect(cleared.pipeline[0]!.offer!.within_band).toBe(false)
  })

  it('FE-4 and FE-6: employees manage their own contacts and consent, and HR sees them', { timeout: 30_000 }, async () => {
    const me = (await signIn('arjun.rao@acme.test'), (await api.get<{ employee_id: string }>('/auth/me')).employee_id)
    const tag = Date.now()
    await api.post('/tables/emergency_contact', { employee_id: me, contact_name: `Contact ${tag}`, relationship: 'Sibling', phone: '+91 98450 99999', priority: 2 })
    const mine = await api.get<{ rows: { contact_name: string }[] }>(`/tables/emergency_contact?employee_id=${me}`)
    expect(mine.rows.map((r) => r.contact_name)).toContain(`Contact ${tag}`)
    await api.post('/tables/consent_record', { employee_id: me, data_category: 'pan', purpose: 'identity_verification', status: 'granted', granted_at: new Date().toISOString(), consent_artifact_ref: 'web-form' })
    const dir = await api.get<{ rows: { full_name: string }[] }>('/directory?q=meera')
    expect(dir.rows.map((r) => r.full_name)).toContain('Meera Iyer')

    await signIn('kavya.menon@acme.test')
    const seen = await api.get<{ rows: { data_category: string; status: string }[] }>(`/tables/consent_record?employee_id=${me}`)
    expect(seen.rows.some((r) => r.data_category === 'pan' && r.status === 'granted')).toBe(true)
    const skills = await api.get<{ rows: { id: string }[] }>('/tables/skill')
    const rated = await api.post<{ id: string }>('/tables/employee_skill', { employee_id: me, skill_id: skills.rows[0]?.id ?? (await api.post<{ id: string }>('/tables/skill', { name: `Skill ${tag}`, category: 'General' })).id, proficiency_level: 3, source: 'manager_rated', last_updated: new Date().toISOString() })
    expect(rated.id).toBeTruthy()
  })

  it('Phase 3: hire end to end, with the new hire resolving their own consent gate through a real sign-in, to a first payslip', { timeout: 90_000 }, async () => {
    await signIn('kavya.menon@acme.test')
    const location = (await api.get<{ rows: { id: string; legal_entity_id: string; state_code: string | null; country_code: string }[] }>('/tables/location')).rows.find((l) => l.country_code === 'IN')!
    const retention = (await api.get<{ rows: { id: string }[] }>('/tables/retention_policy')).rows[0]!
    const state = location.state_code ?? 'KA'
    const candidateEmail = `priya.${Date.now()}@example.test`
    const started = await startFullHire(2000000, {
      legal_entity_id: location.legal_entity_id, location_id: location.id, state_code: state,
      employment_type: 'full_time', date_of_birth: '1995-04-12', personal_address: '1 MG Road, Bengaluru',
      aadhaar_last4: '1234', basic_da_monthly: 2000000 / 24, tax_regime_election: 'new', retention_class_id: retention.id,
      pay_frequency: 'monthly', payment_method: 'bank_transfer', work_state: state, tax_state: state,
    })
    await approvePending('rohan.mehta@acme.test', started.requisition_id, 'g_requisition_budget')

    await signIn('kavya.menon@acme.test')
    await until(async () => ((await detail(started.requisition_id)).requisition.stage === 'posted' ? true : undefined), 'the posting')
    await api.post(`/hire/requisitions/${started.requisition_id}/applications`, { full_name: 'Priya Nair', email: candidateEmail, phone: '+91 98450 00001' })
    await until(async () => ((await detail(started.requisition_id)).pipeline[0]?.screening?.approval ? true : undefined), 'the screening')
    await approvePending('kavya.menon@acme.test', started.requisition_id, 'g_aedt')
    // in-band offer, clear background check: nothing parks the flow until the consent gate, so
    // the worker runs background_check_initiator, employee_record_writer_create/open, straight through

    type Onboarding = { onboarding: { employee_id: string; awaiting_consent_request: boolean } | null }
    const onboarding = await until(async () => {
      const r = await api.get<Onboarding>(`/hire/requisitions/${started.requisition_id}`)
      return r.onboarding?.awaiting_consent_request ? r.onboarding : undefined
    }, 'the flow to reach the consent step (background check + employee creation ran live)')
    const employeeId = onboarding.employee_id

    const denied = signIn('rohan.mehta@acme.test').then(() => api.post(`/hire/requisitions/${started.requisition_id}/request-consent`, {}))
    await expect(denied).rejects.toMatchObject({ status: 403 })

    await signIn('kavya.menon@acme.test')
    const consentReq = await api.post<{ status: string }>(`/hire/requisitions/${started.requisition_id}/request-consent`, {})
    expect(consentReq.status).toBe('requested')
    const gate = await until(async () => (await api.get<{ approvals: Approval[] }>(`/approvals?status=pending&subject_id=${started.requisition_id}`)).approvals.find((a) => a.gate_type === 'dpdp_consent'), 'the consent approval')

    // The new hire's own sign-in was provisioned automatically when their employee row was
    // created (api/src/daydor_api/onboarding.py) -- this is the actual new hire signing in and
    // resolving their own consent gate, not a stand-in.
    await signIn(candidateEmail)
    const granted = await api.post<{ id: string }>('/tables/consent_record', {
      employee_id: employeeId, data_category: 'aadhaar', purpose: 'identity_verification', status: 'granted',
      granted_at: new Date().toISOString(), consent_artifact_ref: 'test-doc',
    })
    expect(granted.id).toBeTruthy()
    const resolved = await api.post<{ status: string }>(`/approvals/${gate.id}/resolve`, { decision: 'approved' })
    expect(resolved.status).toBe('approved')

    await signIn('kavya.menon@acme.test')
    const finished = await until(async () => {
      const r = await api.get<{ instance: { state: string; status: string } }>(`/workflows/instances/${started.instance_id}`)
      return r.instance.state === 'done' ? r : undefined
    }, 'the flow to run through to payroll_profile and its real terminal state')
    expect(finished.instance.status).toBe('completed')

    // A real payroll run covering this hire, through to a real first payslip. build_payroll_run
    // is idempotent on (legal_entity_id, period_start, period_end), so a fixed period would reuse
    // (and find already-resolved) the same run on a second run of this test against the same
    // database -- a day offset from "now" keeps each run's period genuinely fresh.
    await signIn('dev.patel@acme.test')
    const year = 2030 + (Date.now() % 20)
    const month = String((Date.now() % 12) + 1).padStart(2, '0')
    const run = await api.post<{ payroll_run_id: string; anomaly_check: { approval_request_id: string | null } }>('/payroll/runs', {
      legal_entity_id: location.legal_entity_id, period_start: `${year}-${month}-01`, period_end: `${year}-${month}-28`, retention_class_id: retention.id,
    })
    expect(run.anomaly_check.approval_request_id).toBeTruthy()
    // Maker-checker: the payroll person who built the run cannot also clear its own anomaly check.
    await signIn('ops@daydor.test')
    await api.post(`/approvals/${run.anomaly_check.approval_request_id}/resolve`, { decision: 'approved' })

    await signIn('dev.patel@acme.test')
    const disbursal = await api.post<{ approval_request_id: string }>(`/payroll/runs/${run.payroll_run_id}/request-disbursal`, {})
    const tooEarly = api.post(`/payroll/runs/${run.payroll_run_id}/disburse`, { approval_request_id: disbursal.approval_request_id })
    await expect(tooEarly).rejects.toMatchObject({ status: 409 })

    await signIn('rohan.mehta@acme.test')
    await api.post(`/approvals/${disbursal.approval_request_id}/resolve`, { decision: 'approved' })

    await signIn('dev.patel@acme.test')
    const disbursed = await api.post<{ status: string }>(`/payroll/runs/${run.payroll_run_id}/disburse`, { approval_request_id: disbursal.approval_request_id })
    expect(disbursed.status).toBe('disbursed')
    const issued = await api.post<{ payslip_ids: string[] }>(`/payroll/runs/${run.payroll_run_id}/issue-payslips`, {})
    expect(issued.payslip_ids.length).toBeGreaterThan(0)

    const payslips = await api.get<{ rows: { employee_id: string; gross_pay: string; net_pay: string }[] }>(`/tables/payslip?payroll_run_id=${run.payroll_run_id}`)
    const mine = payslips.rows.find((p) => p.employee_id === employeeId)
    expect(mine).toBeTruthy()
    expect(Number(mine!.gross_pay)).toBeCloseTo(2000000 / 12, 2)
    expect(Number(mine!.net_pay)).toBeLessThan(Number(mine!.gross_pay))
  })
})
