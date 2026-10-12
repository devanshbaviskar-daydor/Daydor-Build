// A framework-free stand-in for the API layer. It sits behind the same transport as live calls
// and follows the same rules: the same error codes, the same role limits (read from the generated
// contract, not retyped), the same idempotency behaviour. It is for building screens before their
// backend step is live, for tests, and for the hosted preview.
import { canReadTable, canWriteTable, enumValues, gate, gates, tableLevel, visibleColumns, writableColumns, type TableName } from '../contract'
import { REPORTS, T as TENANT, ago as agoMs, seedTables } from './seed'
import enums from '../contract/generated/enums.json'
import hireDefinition from './hireDefinition.json'
import type { Reply, SendInit } from '../api/transport'

type Row = Record<string, unknown>
const WORKFLOW_READERS = ['daydor_ops', 'tenant_founder', 'tenant_hr', 'tenant_payroll', 'external_auditor']
const DIRECT_WRITE = ['position', 'job_profile', 'comp_band', 'access_role_template', 'skill', 'employee_skill', 'emergency_contact', 'consent_record', 'checklist_task']
const T = TENANT

export const DEMO_PEOPLE = [
  { id: 'id-founder', email: 'rohan.mehta@acme.test', display_name: 'Rohan Mehta', role: 'tenant_founder', role_letter: 'F', role_label: 'Founder', user_id: 'u-founder', employee_id: null },
  { id: 'id-hr', email: 'kavya.menon@acme.test', display_name: 'Kavya Menon', role: 'tenant_hr', role_letter: 'H', role_label: 'HR admin', user_id: 'u-hr', employee_id: null },
  { id: 'id-payroll', email: 'dev.patel@acme.test', display_name: 'Dev Patel', role: 'tenant_payroll', role_letter: 'P', role_label: 'Payroll and finance', user_id: 'u-payroll', employee_id: null },
  { id: 'id-it', email: 'sana.qureshi@acme.test', display_name: 'Sana Qureshi', role: 'tenant_it', role_letter: 'I', role_label: 'IT admin', user_id: 'u-it', employee_id: null },
  { id: 'id-manager', email: 'meera.iyer@acme.test', display_name: 'Meera Iyer', role: 'tenant_manager', role_letter: 'M', role_label: 'People manager', user_id: 'u-manager', employee_id: 'e-meera' },
  { id: 'id-employee', email: 'arjun.rao@acme.test', display_name: 'Arjun Rao', role: 'tenant_employee', role_letter: 'E', role_label: 'Employee', user_id: 'u-employee', employee_id: 'e-arjun' },
  { id: 'id-ops', email: 'ops@daydor.test', display_name: 'Daydor Ops', role: 'daydor_ops', role_letter: 'O', role_label: 'Daydor ops', user_id: null, employee_id: null },
  { id: 'id-admin', email: 'admin@daydor.test', display_name: 'Daydor Admin', role: 'daydor_admin', role_letter: 'A', role_label: 'Daydor admin', user_id: null, employee_id: null },
  { id: 'id-auditor', email: 'imran.khan@audit.test', display_name: 'Imran Khan', role: 'external_auditor', role_letter: 'U', role_label: 'External auditor', user_id: null, employee_id: null },
].map((p) => ({
  ...p, tenant_id: p.role === 'daydor_admin' ? null : T, tenant_name: p.role === 'daydor_admin' ? null : 'Acme Technologies',
  capabilities: { workflow_timeline: WORKFLOW_READERS.includes(p.role), directory: !['daydor_admin', 'external_auditor'].includes(p.role) },
}))
type Person = (typeof DEMO_PEOPLE)[number]

const NAME_VISIBLE = ['daydor_ops', 'tenant_founder', 'tenant_hr', 'tenant_it']
const ago = agoMs
const H = 3_600_000

function err(status: number, code: string, message: string): Reply {
  return { status, json: { error: { code, message } } }
}
const ok = (json: unknown, status = 200): Reply => ({ status, json })

const EMPLOYEE_COL: Record<string, string> = {
  employee: 'id', app_user: 'employee_id', consent_record: 'employee_id', emergency_contact: 'employee_id', employee_skill: 'employee_id',
  checklist: 'employee_id', identity_account: 'employee_id', payroll_profile: 'employee_id', payslip: 'employee_id',
  work_authorization: 'employee_id', employment_record: 'employee_id', candidate: 'converted_employee_id',
  job_requisition: 'hiring_manager_id', interview: 'interviewer_employee_id',
}
const SCOPED_ROLES = ['tenant_employee', 'tenant_manager']
const ALL_APPROVERS_FOR_GATE = (g: string) => gate(g)?.approvers ?? []

function createBackend() {
  let seq = 100
  const id = (p: string) => `${p}-${++seq}`
  let tables: Record<string, Row[]> = {}
  let approvals: Row[] = []
  let instances: Row[] = []
  let transitions: Record<string, Row[]> = {}
  let replays: Record<string, unknown> = {}
  let evaluations: Row[] = []
  let ctxOf: Record<string, Row> = {}        // private workflow context (never returned)

  const addT = (inst: string, from: string, to: string, outcome: string, approval: string | null = null, at = new Date().toISOString()) => {
    const list = (transitions[inst] ??= [])
    list.push({ id: list.length + 1, event: 'advance', from_state: from, to_state: to, outcome, approval_request_id: approval, created_at: at })
  }
  const seedPath = (inst: string, steps: [string, string, string][], startAgo: number) => steps.forEach(([f, t, o], i) => addT(inst, f, t, o, null, ago(startAgo - i * 0.02 * H)))

  function reset() {
    seq = 100; replays = {}; transitions = {}; ctxOf = {}
    tables = seedTables()
    const base = (extra: Row): Row => ({ tenant_id: T, required_approver_role: null, requested_by_user_id: null, resolved_by_user_id: null, resolved_at: null, deadline_at: null, decision_note: null, ...extra })
    approvals = [
      base({ id: 'ap-1', gate_type: 'g_requisition_budget', subject_table: 'job_requisition', subject_id: 'req-1', status: 'pending', created_at: ago(2 * H) }),
      base({ id: 'ap-2', gate_type: 'g_offer_band', subject_table: 'job_requisition', subject_id: 'req-3', status: 'pending', created_at: ago(26 * H) }),
      base({ id: 'ap-3', gate_type: 'g_aedt', subject_table: 'job_requisition', subject_id: 'req-3', status: 'approved', resolved_by_user_id: 'u-hr', resolved_at: ago(50 * H), decision_note: 'Notice sent', created_at: ago(72 * H) }),
      base({ id: 'ap-4', gate_type: 'g_it_deprov', subject_table: 'identity_account', subject_id: 'ia-1', status: 'pending', requested_by_user_id: 'u-hr', created_at: ago(5 * H) }),
      base({ id: 'ap-5', gate_type: 'g_it_offtemplate', subject_table: 'app_access_grant', subject_id: 'grant-1', status: 'pending', created_at: ago(0.7 * H) }),
      base({ id: 'ap-9', gate_type: 'g_requisition_budget', subject_table: 'job_requisition', subject_id: 'req-3', status: 'approved', resolved_by_user_id: 'u-founder', resolved_at: ago(8.9 * 24 * H), created_at: ago(9 * 24 * H) }),
      base({ id: 'ap-11', gate_type: 'g_requisition_budget', subject_table: 'job_requisition', subject_id: 'req-4', status: 'approved', resolved_by_user_id: 'u-founder', resolved_at: ago(39 * 24 * H), created_at: ago(40 * 24 * H) }),
      base({ id: 'ap-12', gate_type: 'g_aedt', subject_table: 'job_requisition', subject_id: 'req-4', status: 'approved', resolved_by_user_id: 'u-hr', resolved_at: ago(34 * 24 * H), created_at: ago(35 * 24 * H) }),
    ]
    evaluations = [{ id: 'ev-1', gate_id: 'sg_access_request_precheck', gate_label: "Pre-check: is this access request consistent with the person's role?", subject_table: 'app_access_grant', subject_id: 'grant-1', engine: 'jev', engine_version: '0.1', confidence: 0.41, threshold: 0.9, model_decision: 'escalate', effective_decision: 'escalate', mode: 'shadow', error: null, approval_request_id: 'ap-5', created_at: ago(0.7 * H) }]
    const inst = (id: string, req: string, pos: string, state: string, status: string, waiting: string | null, ver: number, age: number, ctx: Row = {}) => ({
      id, definition_name: 'hire', definition_version: 3, subject_table: 'job_requisition', subject_id: req, state, status, waiting_on_approval: waiting,
      context: { channel: 'company_site', pay_range_min: '1800000', pay_range_max: '2600000', position_id: pos, ...ctx }, context_hidden_keys: [], version: ver, created_at: ago(age), updated_at: ago(age / 2) })
    instances = [
      inst('wf-1', 'req-1', 'pos-1', 's03_approval_request', 'waiting_gate', 'ap-1', 4, 2 * H),
      inst('wf-3', 'req-3', 'pos-3', 's08_offer', 'waiting_gate', 'ap-2', 11, 9 * 24 * H, { pay_range_min: '1200000', pay_range_max: '2000000' }),
      inst('wf-4', 'req-4', 'pos-5', 'done', 'completed', null, 14, 40 * 24 * H, { pay_range_min: '1300000', pay_range_max: '1700000' }),
    ]
    const early: [string, string, string][] = [['start', 's01_position', 'moved'], ['s01_position', 's02_job_requisition', 'moved'], ['s02_job_requisition', 's03_approval_request', 'moved'], ['s03_approval_request', 's03_approval_request', 'waiting_gate']]
    seedPath('wf-1', early, 2 * H)
    seedPath('wf-3', [...early, ['s03_approval_request', 's04_job_posting', 'moved'], ['s04_job_posting', 's05_application', 'moved'], ['s05_application', 's06_screening_result', 'moved'], ['s06_screening_result', 's06_screening_result', 'waiting_gate'],
      ['s06_screening_result', 's07_interview', 'moved'], ['s07_interview', 's08_offer', 'moved'], ['s08_offer', 's08_offer', 'waiting_gate']], 9 * 24 * H)
    seedPath('wf-4', [...early, ['s03_approval_request', 's04_job_posting', 'moved'], ['s04_job_posting', 's05_application', 'moved'], ['s05_application', 's06_screening_result', 'moved'], ['s06_screening_result', 's06_screening_result', 'waiting_gate'],
      ['s06_screening_result', 's07_interview', 'moved'], ['s07_interview', 's08_offer', 'moved'], ['s08_offer', 'done', 'moved']], 40 * 24 * H)
    ctxOf = { 'wf-3': { comp_band_id: 'cb-2', proposed_base: 2800000, interviewer_employee_id: 'e-meera' } }
  }
  reset()

  const catalog = () => [...gates].map((g) => ({ id: g.id, label: g.label, kind: g.kind, tables: g.tables, approver_roles: g.approvers, source: g.source }))
  const personByToken = (token?: string | null): Person | null => DEMO_PEOPLE.find((p) => `mock-${p.id}` === token) ?? null

  // ---- row access, the way the database applies it
  function inScope(table: string, row: Row, who: Person): boolean {
    if (who.tenant_id !== null && row.tenant_id !== who.tenant_id) return false
    if (!SCOPED_ROLES.includes(who.role)) return true
    const col = EMPLOYEE_COL[table]
    if (!col) return true
    const v = row[col]
    if (v === null || v === undefined) return false
    if (v === who.employee_id) return true
    return who.role === 'tenant_manager' && (REPORTS[String(who.employee_id)] ?? []).includes(String(v))
  }
  const rowsFor = (table: string, who: Person): Row[] | null => {
    try { if (!canReadTable(table as TableName, who.role)) return null } catch { return null }
    return (tables[table] ?? []).filter((r) => inScope(table, r, who))
  }
  const project = (table: string, rows: Row[], who: Person): Row[] => {
    const cols = visibleColumns(table as TableName, who.role).map((c) => c.n)
    return rows.map((r) => Object.fromEntries(cols.map((c) => [c, r[c] ?? null])))
  }

  function shapeApproval(a: Row, who: Person) {
    const g = gate(String(a.gate_type))
    const allowed = g?.approvers.length ? [...g.approvers] : a.required_approver_role ? [String(a.required_approver_role)] : []
    const mine = who.user_id !== null && a.requested_by_user_id === who.user_id
    return { ...a, gate_label: g?.label ?? a.gate_type, allowed_roles: allowed, requested_by_me: mine, can_resolve: a.status === 'pending' && allowed.includes(who.role) && !mine }
  }
  const brief = (a: Row | undefined) => (a ? { id: a.id, status: a.status, gate_type: a.gate_type } : null)

  // ---- requisitions, built from the same tables the real API reads
  function requisitionSummary(rq: Row, who: Person) {
    const get = (t: string) => rowsFor(t, who)
    const pos = (get('position') ?? []).find((p) => p.id === rq.position_id)
    const dept = pos ? (get('department') ?? []).find((d) => d.id === pos.department_id) : undefined
    const prof = pos ? (get('job_profile') ?? []).find((p) => p.id === pos.job_profile_id) : undefined
    const mgr = (get('employee') ?? []).find((e) => e.id === rq.hiring_manager_id)
    const post = (get('job_posting') ?? []).find((p) => p.requisition_id === rq.id)
    const appr = approvals.filter((a) => a.subject_id === rq.id && a.gate_type === 'g_requisition_budget').sort((a, b) => String(a.created_at).localeCompare(String(b.created_at))).pop()
    const apps = (get('application') ?? []).filter((a) => a.requisition_id === rq.id)
    const stage = !appr ? 'drafting' : appr.status === 'pending' ? 'awaiting_budget_approval' : appr.status === 'approved' ? (post && post.posted_at ? 'posted' : 'approved') : 'budget_rejected'
    return {
      id: rq.id, status: rq.status, target_start_date: rq.target_start_date, position_id: rq.position_id, hiring_manager_id: rq.hiring_manager_id,
      hiring_manager_name: mgr ? mgr.full_name : null, job_title: prof ? prof.title : null, department_name: dept ? dept.name : null,
      stage, approval: brief(appr), candidate_count: apps.length, created_at: rq.created_at,
      posting: post ? { channel: post.channel, pay_range_min: post.pay_range_min, pay_range_max: post.pay_range_max, pay_transparency_checked: post.pay_transparency_checked, posted_at: post.posted_at } : null,
    }
  }
  function pipeline(rq: Row, who: Person) {
    const get = (t: string) => rowsFor(t, who) ?? []
    const raised = approvals.filter((a) => a.subject_id === rq.id).sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)))
    const byGate = Object.fromEntries(raised.map((a) => [a.gate_type, a]))
    return get('application').filter((a) => a.requisition_id === rq.id).map((a) => {
      const cand = get('candidate').find((c) => c.id === a.candidate_id)
      const s = get('screening_result').find((x) => x.application_id === a.id)
      const i = get('interview').find((x) => x.application_id === a.id)
      const o = get('offer').find((x) => x.application_id === a.id)
      const band = o ? get('comp_band').find((b) => b.id === o.comp_band_id) : undefined
      const iv = i ? get('employee').find((e) => e.id === i.interviewer_employee_id) : undefined
      return {
        application: { id: a.id, stage: a.stage, stage_changed_at: a.stage_changed_at, rejection_reason_code: a.rejection_reason_code },
        candidate: cand ? { id: cand.id, full_name: cand.full_name, email: cand.email, source: cand.source } : null,
        screening: s ? { id: s.id, score: s.score, recommendation: s.recommendation, tool_name: s.tool_name, model_version: s.model_version, candidate_notified_at: s.candidate_notified_at, human_override: s.human_override, approval: brief(byGate.g_aedt) } : null,
        interview: i ? { id: i.id, scheduled_at: i.scheduled_at, interviewer_employee_id: i.interviewer_employee_id, interviewer_name: iv ? iv.full_name : null, recommendation: i.recommendation } : null,
        offer: o ? { id: o.id, proposed_base: o.proposed_base, proposed_equity: o.proposed_equity, within_band: o.within_band, sent_at: o.sent_at, accepted_at: o.accepted_at,
          band: band ? { currency: band.currency, band_min: band.band_min, band_mid: band.band_mid, band_max: band.band_max } : null, approval: brief(byGate.g_offer_band) } : null,
      }
    })
  }

  // ---- what approving a gate does to the workflow, mirroring the backend's hire flow
  function afterResolve(a: Row, decision: string) {
    const inst = instances.find((i) => i.waiting_on_approval === a.id)
    if (!inst) return
    const instId = String(inst.id), from = String(inst.state), ctx = ctxOf[instId] ?? {}
    if (decision !== 'approved') { Object.assign(inst, { status: 'cancelled', waiting_on_approval: null }); addT(instId, from, from, 'rejected', String(a.id)); return }
    if (a.gate_type === 'g_requisition_budget') {
      Object.assign(inst, { state: 's04_job_posting', status: 'running', waiting_on_approval: null }); addT(instId, from, 's04_job_posting', 'moved', String(a.id))
      ;(tables.job_posting ??= []).push({ id: id('post'), tenant_id: T, requisition_id: inst.subject_id, channel: (inst.context as Row).channel, pay_range_min: Number((inst.context as Row).pay_range_min), pay_range_max: Number((inst.context as Row).pay_range_max), pay_transparency_checked: true, posted_at: new Date().toISOString(), closed_at: null, created_at: new Date().toISOString(), updated_at: new Date().toISOString() })
    } else if (a.gate_type === 'g_aedt') {
      const appRow = (tables.application ?? []).find((x) => x.requisition_id === inst.subject_id)
      addT(instId, from, 's07_interview', 'moved', String(a.id)); addT(instId, 's07_interview', 's08_offer', 'moved')
      ;(tables.interview ??= []).push({ id: id('int'), tenant_id: T, application_id: appRow?.id, interviewer_employee_id: ctx.interviewer_employee_id ?? 'e-meera', scheduled_at: ctx.scheduled_at ?? new Date(Date.now() + 5 * 86_400_000).toISOString(), scorecard: null, recommendation: null, created_at: new Date().toISOString(), updated_at: new Date().toISOString() })
      const band = (tables.comp_band ?? []).find((b) => b.id === ctx.comp_band_id)
      const base = Number(ctx.proposed_base ?? 0)
      const within = !!band && base >= Number(band.band_min) && base <= Number(band.band_max)
      const offerId = id('off')
      ;(tables.offer ??= []).push({ id: offerId, tenant_id: T, application_id: appRow?.id, comp_band_id: ctx.comp_band_id ?? null, proposed_base: base, proposed_equity: ctx.proposed_equity ?? null, within_band: within, approval_request_id: null, offer_document_id: null, sent_at: null, accepted_at: null, created_at: new Date().toISOString(), updated_at: new Date().toISOString() })
      if (within) { Object.assign(inst, { state: 'done', status: 'completed', waiting_on_approval: null }); addT(instId, 's08_offer', 'done', 'moved') }
      else {
        const nap = id('ap')
        approvals.unshift({ id: nap, tenant_id: T, gate_type: 'g_offer_band', subject_table: 'job_requisition', subject_id: inst.subject_id, required_approver_role: null, requested_by_user_id: null, resolved_by_user_id: null, resolved_at: null, deadline_at: null, decision_note: null, status: 'pending', created_at: new Date().toISOString() })
        Object.assign(inst, { state: 's08_offer', status: 'waiting_gate', waiting_on_approval: nap }); addT(instId, 's08_offer', 's08_offer', 'waiting_gate')
      }
    } else if (a.gate_type === 'g_offer_band') {
      Object.assign(inst, { state: 'done', status: 'completed', waiting_on_approval: null }); addT(instId, from, 'done', 'moved', String(a.id))
    }
  }

  function handle(method: string, path: string, init: SendInit = {}): Promise<Reply> {
    return Promise.resolve(route(method.toUpperCase(), path, init))
  }

  function route(method: string, path: string, init: SendInit): Reply {
    const url = new URL(path, 'http://mock')
    const p = url.pathname
    const q = url.searchParams
    const body = (init.body ?? {}) as Row
    const key = init.headers?.['Idempotency-Key']

    if (method === 'POST' && p === '/auth/dev-login') {
      const person = DEMO_PEOPLE.find((x) => x.email === String(body.email ?? '').trim())
      return person ? ok({ token: `mock-${person.id}`, session: person }) : err(401, 'unknown_account', 'No active account uses that email.')
    }
    if (method === 'GET' && p === '/auth/dev-users') return ok({ users: DEMO_PEOPLE })

    const who = personByToken(init.token)
    if (!who) return err(401, 'not_signed_in', 'Sign in to continue.')
    if (method === 'GET' && p === '/auth/me') return ok(who)
    if (method === 'GET' && p === '/meta/enums') return ok(enums)
    if (method === 'GET' && p === '/meta/gates') return ok({ gates: catalog() })
    if (method === 'GET' && p === '/meta/workflows/hire') {
      return WORKFLOW_READERS.includes(who.role) ? ok({ name: 'hire', version: 3, definition: hireDefinition }) : err(403, 'workflow_not_visible', 'Your role cannot read workflow definitions.')
    }

    // approvals
    if (p === '/approvals' && method === 'GET') {
      if (!canReadTable('approval_request', who.role)) return err(403, 'forbidden', 'Your role does not have access to this.')
      const status = q.get('status')
      const rows = approvals.filter((a) => (!status || a.status === status) && (!q.get('subject_id') || a.subject_id === q.get('subject_id')) && (!q.get('gate') || a.gate_type === q.get('gate')))
        .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
      return ok({ approvals: rows.map((a) => shapeApproval(a, who)) })
    }
    let m = p.match(/^\/approvals\/([^/]+)(\/resolve)?$/)
    if (m) {
      const a = approvals.find((x) => x.id === m![1])
      if (!a) return err(404, 'not_found', 'That request was not found.')
      if (method === 'GET' && !m[2]) {
        const wf = WORKFLOW_READERS.includes(who.role) ? instances.find((i) => i.waiting_on_approval === a.id || i.subject_id === a.subject_id) : undefined
        return ok({ ...shapeApproval(a, who), workflow_instance_id: wf ? wf.id : null })
      }
      if (method === 'POST' && m[2]) {
        const shaped = shapeApproval(a, who)
        if (a.status !== 'pending') return err(409, 'already_resolved', 'This request has already been resolved.')
        if (shaped.requested_by_me) return err(403, 'maker_checker', 'The person who raised this request cannot approve it.')
        if (!shaped.allowed_roles.includes(who.role)) return err(403, 'wrong_approver_role', 'Your role cannot approve this kind of request.')
        const decision = String(body.decision)
        if (decision !== 'approved' && decision !== 'rejected') return err(422, 'invalid_request', 'Check these fields: decision')
        Object.assign(a, { status: decision, resolved_by_user_id: who.user_id, resolved_at: new Date().toISOString(), decision_note: body.note ?? null })
        afterResolve(a, decision)
        return ok({ id: a.id, status: decision })
      }
    }

    if (method === 'GET' && p === '/evaluations') {
      if (!WORKFLOW_READERS.includes(who.role)) return err(403, 'evaluation_not_visible', 'Your role cannot see automated pre-check results.')
      return ok({ evaluations: evaluations.filter((e) => (!q.get('approval_id') || e.approval_request_id === q.get('approval_id')) && (!q.get('subject_id') || e.subject_id === q.get('subject_id'))) })
    }
    if (method === 'GET' && p === '/audit/subject') {
      const table = q.get('table') ?? ''
      const subject = q.get('id') ?? ''
      const names = NAME_VISIBLE.includes(who.role)
      const label = (userId: unknown, fallback: string) => {
        if (userId && userId === who.user_id) return 'You'
        if (!userId) return fallback
        return (names ? DEMO_PEOPLE.find((x) => x.user_id === userId)?.display_name : undefined) ?? 'A person'
      }
      const entries: { id: string; at: string; kind: string; actor: string; action: string }[] = []
      if (canReadTable('approval_request', who.role)) {
        for (const a of approvals.filter((x) => x.subject_table === table && x.subject_id === subject)) {
          const g = gate(String(a.gate_type))?.label ?? String(a.gate_type)
          entries.push({ id: `ap-${a.id}-req`, at: String(a.created_at), kind: 'approval_requested', actor: label(a.requested_by_user_id, 'An agent'), action: `Asked for approval: ${g}` })
          if (a.resolved_at) entries.push({ id: `ap-${a.id}-res`, at: String(a.resolved_at), kind: 'approval_resolved', actor: label(a.resolved_by_user_id, 'A person'), action: `${a.status === 'approved' ? 'Approved' : 'Rejected'}: ${g}.${a.decision_note ? ` Note: ${a.decision_note}` : ''}` })
        }
      }
      if (WORKFLOW_READERS.includes(who.role)) {
        const state = (s: string) => s.replace(/^s\d+_/, '').replace(/_/g, ' ')
        for (const inst of instances.filter((i) => i.subject_table === table && i.subject_id === subject)) {
          for (const t of transitions[String(inst.id)] ?? []) {
            const text = t.outcome === 'moved' ? `Moved from ${state(String(t.from_state))} to ${state(String(t.to_state))}` : t.outcome === 'waiting_gate' ? `Paused at ${state(String(t.from_state))}, waiting for approval` : `Approval rejected at ${state(String(t.from_state))}`
            entries.push({ id: `wf-${t.id}`, at: String(t.created_at), kind: 'workflow', actor: 'Agent', action: text })
          }
        }
      }
      entries.sort((a, b) => a.at.localeCompare(b.at) || a.id.localeCompare(b.id))
      return ok({ table, subject_id: subject, entries, sources: { approvals: canReadTable('approval_request', who.role), workflow: WORKFLOW_READERS.includes(who.role), audit_log: canReadTable('audit_log', who.role) } })
    }

    // workflows
    if (p.startsWith('/workflows')) {
      if (!WORKFLOW_READERS.includes(who.role)) return err(403, 'workflow_not_visible', 'Your role cannot see workflow timelines. Open the approval to see its status.')
      if (p === '/workflows/instances' && method === 'GET') return ok({ instances: instances.filter((i) => !q.get('status') || i.status === q.get('status')) })
      m = p.match(/^\/workflows\/instances\/([^/]+)$/)
      if (m && method === 'GET') {
        const inst = instances.find((i) => i.id === m![1])
        return inst ? ok({ instance: inst, transitions: transitions[String(inst.id)] ?? [], definition: hireDefinition }) : err(404, 'not_found', 'That workflow was not found.')
      }
    }

    // directory
    if (method === 'GET' && p === '/directory') {
      if (['daydor_admin', 'external_auditor'].includes(who.role)) return err(403, 'forbidden', 'Your role does not have access to this.')
      const needle = (q.get('q') ?? '').toLowerCase()
      const rows = (tables.employee ?? []).filter((e) => e.tenant_id === who.tenant_id && e.is_active && (!needle || String(e.full_name).toLowerCase().includes(needle) || String(e.work_email).toLowerCase().includes(needle)) && (!q.get('department_id') || e.department_id === q.get('department_id')))
        .map((e) => ({ id: e.id, full_name: e.full_name, work_email: e.work_email, department_id: e.department_id, location_id: e.location_id, position_id: e.position_id }))
        .sort((a, b) => String(a.full_name).localeCompare(String(b.full_name)))
      return ok({ rows, total: rows.length })
    }

    // generic tables
    m = p.match(/^\/tables\/([^/]+)(?:\/([^/]+))?$/)
    if (m) {
      const name = m[1] as TableName
      let known = true
      try { tableLevel(name, who.role) } catch { known = false }
      if (!known) return err(404, 'unknown_table', `There is no table called '${name}'.`)
      if (method === 'GET' && !m[2]) {
        if (!canReadTable(name, who.role)) return err(403, 'forbidden', 'Your role does not have access to this.')
        const cols = visibleColumns(name, who.role).map((c) => c.n)
        let rows = rowsFor(name, who) ?? []
        for (const [k, v] of q.entries()) {
          if (['limit', 'offset', 'order'].includes(k)) continue
          if (k.endsWith('__in')) {
            const col = k.slice(0, -4)
            if (!cols.includes(col)) return err(422, 'invalid_filter', `You cannot filter ${name} by '${col}'.`)
            const set = v.split(',').filter(Boolean); rows = rows.filter((r) => set.includes(String(r[col]))); continue
          }
          if (!cols.includes(k)) return err(422, 'invalid_filter', `You cannot filter ${name} by '${k}'.`)
          rows = rows.filter((r) => String(r[k]) === v)
        }
        const out = project(name, rows, who)
        return ok({ table: name, columns: cols, rows: out, total: out.length, limit: 50, offset: 0 })
      }
      if (method === 'POST' || method === 'PATCH') {
        if (!DIRECT_WRITE.includes(name)) return err(403, 'not_directly_writable', 'This record changes through its own flow, not directly.')
        if (!canWriteTable(name, who.role)) return err(403, 'forbidden', 'Your role cannot change this.')
        const allowed = writableColumns(name, who.role).map((c) => c.n)
        const bad = Object.keys(body).filter((k) => !allowed.includes(k))
        if (bad.length) return err(422, 'invalid_fields', `You cannot set: ${bad.sort().join(', ')}`)
        if (method === 'POST') {
          const rk = `POST ${p} ${key ?? ''}`
          if (key && replays[rk]) return ok({ ...(replays[rk] as Row), replayed: true }, 201)
          const row: Row = { id: id(name), tenant_id: who.tenant_id, ...body, created_at: new Date().toISOString(), updated_at: new Date().toISOString() }
          if (!inScope(name, row, who)) return err(403, 'forbidden', 'Your role does not have access to this.')
          ;(tables[name] ??= []).push(row)
          const res = { table: name, id: row.id }
          if (key) replays[rk] = res
          return ok(res, 201)
        }
        const row = (tables[name] ?? []).find((r) => r.id === m![2] && inScope(name, r, who))
        if (!row) return err(404, 'not_found', 'That record was not found.')
        Object.assign(row, body, { updated_at: new Date().toISOString() })
        return ok({ table: name, id: row.id })
      }
    }

    // hire
    if (method === 'POST' && p === '/hire/start') {
      if (!canWriteTable('job_requisition', who.role)) return err(403, 'forbidden', 'Your role cannot open a requisition.')
      const rk = `POST ${p} ${key ?? ''}`
      if (key && replays[rk]) return ok({ ...(replays[rk] as Row), replayed: true }, 201)
      const position = (tables.position ?? []).find((r) => r.id === body.position_id)
      if (!position || position.status !== 'open' || position.current_employee_id) return err(409, 'no_open_seat', 'That position is not an open, vacant, budgeted seat.')
      if (Number(body.pay_range_min) > Number(body.pay_range_max)) return err(422, 'check_violation', 'The pay range minimum cannot be above the maximum.')
      const existing = instances.find((i) => (i.context as Row).position_id === position.id && ['running', 'waiting_gate'].includes(String(i.status)))
      let res: Row
      if (existing) res = { instance_id: existing.id, requisition_id: existing.subject_id, existing: true }
      else {
        const req = id('req'); const wf = id('wf'); const ap = id('ap'); const now = new Date().toISOString()
        ;(tables.job_requisition ??= []).push({ id: req, tenant_id: who.tenant_id, position_id: position.id, hiring_manager_id: body.hiring_manager_id, status: 'draft', target_start_date: body.target_start_date, approval_request_id: ap, created_at: now, updated_at: now })
        approvals.unshift({ id: ap, tenant_id: who.tenant_id, gate_type: 'g_requisition_budget', subject_table: 'job_requisition', subject_id: req, required_approver_role: null, requested_by_user_id: null, resolved_by_user_id: null, resolved_at: null, deadline_at: null, decision_note: null, status: 'pending', created_at: now })
        instances.unshift({ id: wf, definition_name: 'hire', definition_version: 3, subject_table: 'job_requisition', subject_id: req, state: 's03_approval_request', status: 'waiting_gate', waiting_on_approval: ap, context: { channel: body.channel ?? 'company_site', pay_range_min: String(body.pay_range_min), pay_range_max: String(body.pay_range_max), position_id: position.id }, context_hidden_keys: ['comp_band_id', 'proposed_base'], version: 1, created_at: now, updated_at: now })
        ctxOf[wf] = { comp_band_id: body.comp_band_id, proposed_base: body.proposed_base, proposed_equity: body.proposed_equity, interviewer_employee_id: body.interviewer_employee_id, scheduled_at: body.scheduled_at }
        seedPath(wf, [['start', 's01_position', 'moved'], ['s01_position', 's02_job_requisition', 'moved'], ['s02_job_requisition', 's03_approval_request', 'moved'], ['s03_approval_request', 's03_approval_request', 'waiting_gate']], 0)
        res = { instance_id: wf, requisition_id: req }
      }
      if (key) replays[rk] = res
      return ok(res, 201)
    }
    if (method === 'GET' && p === '/hire/requisitions') {
      if (!canReadTable('job_requisition', who.role)) return err(403, 'forbidden', 'Your role does not have access to this.')
      const rows = (rowsFor('job_requisition', who) ?? []).map((rq) => requisitionSummary(rq, who)).sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
      return ok({ requisitions: rows })
    }
    m = p.match(/^\/hire\/requisitions\/([^/]+)(\/applications)?$/)
    if (m) {
      if (method === 'GET' && !m[2]) {
        if (!canReadTable('job_requisition', who.role)) return err(403, 'forbidden', 'Your role does not have access to this.')
        const rq = (rowsFor('job_requisition', who) ?? []).find((r) => r.id === m![1])
        if (!rq) return err(404, 'not_found', 'That requisition was not found.')
        // The mock's simulated hire flow stops at the offer, same as the backend's own flow did
        // before Phase 2's wiring -- no onboarding step exists to simulate here yet.
        return ok({ requisition: requisitionSummary(rq, who), pipeline: pipeline(rq, who), onboarding: null, access: { can_enter_applications: canWriteTable('application', who.role), sees_candidates: canReadTable('application', who.role) } })
      }
      if (method === 'POST' && m[2]) {
        if (!canWriteTable('application', who.role)) return err(403, 'forbidden', 'Your role cannot enter applications.')
        const email = String(body.email ?? '')
        if (!body.full_name || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email) || !body.phone) return err(422, 'invalid_request', 'Check these fields: ' + [!body.full_name && 'full_name', !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email) && 'email', !body.phone && 'phone'].filter(Boolean).join(', '))
        const rk = `POST ${p} ${key ?? ''}`
        if (key && replays[rk]) return ok({ ...(replays[rk] as Row), replayed: true }, 202)
        const inst = instances.find((i) => i.subject_id === m![1])
        if (!inst) return err(404, 'not_found', 'No hire is in progress for that requisition.')
        const live = (tables.job_posting ?? []).some((x) => x.requisition_id === m![1] && x.posted_at)
        if (inst.status !== 'running' || inst.state !== 's04_job_posting' || !live) return err(409, 'not_accepting_applications', 'This requisition is not taking applications right now. It needs an approved budget and a live posting, and only one candidate can go through each hire.')
        const now = new Date().toISOString(); const cand = id('cand'); const app = id('app'); const ap = id('ap'); const instId = String(inst.id)
        ;(tables.candidate ??= []).push({ id: cand, tenant_id: who.tenant_id, full_name: body.full_name, email, phone: body.phone, resume_ref: body.resume_ref ?? 'entered-by-hr', source: body.source ?? 'hr_entry', retain_until: null, converted_employee_id: null, created_at: now, updated_at: now })
        ;(tables.application ??= []).push({ id: app, tenant_id: who.tenant_id, candidate_id: cand, requisition_id: m[1], stage: 'applied', stage_changed_at: now, rejection_reason_code: null, created_at: now, updated_at: now })
        ;(tables.screening_result ??= []).push({ id: id('sr'), tenant_id: who.tenant_id, application_id: app, aedt_audit_id: null, tool_name: 'placeholder-screener', model_version: '0.1', score: 0.78, recommendation: 'advance', candidate_notified_at: null, human_reviewer_user_id: null, human_override: false, created_at: now, updated_at: now })
        approvals.unshift({ id: ap, tenant_id: who.tenant_id, gate_type: 'g_aedt', subject_table: 'job_requisition', subject_id: m[1], required_approver_role: null, requested_by_user_id: null, resolved_by_user_id: null, resolved_at: null, deadline_at: null, decision_note: null, status: 'pending', created_at: now })
        addT(instId, 's04_job_posting', 's05_application', 'moved'); addT(instId, 's05_application', 's06_screening_result', 'moved'); addT(instId, 's06_screening_result', 's06_screening_result', 'waiting_gate')
        Object.assign(inst, { state: 's06_screening_result', status: 'waiting_gate', waiting_on_approval: ap })
        const res = { instance_id: instId, status: 'queued' }
        if (key) replays[rk] = res
        return ok(res, 202)
      }
    }
    return err(404, 'not_found', 'Not found.')
  }

  return { handle, reset, enumValues, ALL_APPROVERS_FOR_GATE }
}

export const mockBackend = createBackend()
