import { describe, expect, it, vi } from 'vitest'
import { mockBackend, DEMO_PEOPLE } from '../mocks/router'
import { api, setTokenProvider } from './client'
import { ApiError, explain } from './errors'
import * as transport from './transport'
import { configureTransport, modeFor } from './transport'

const as = (id: string) => setTokenProvider(() => `mock-${id}`)

describe('transport', () => {
  it('routes each resource by its own mode', () => {
    configureTransport({ defaultMode: 'mock', overrides: { approvals: 'live' } })
    expect(modeFor('/approvals?status=pending')).toBe('live')
    expect(modeFor('/workflows/instances')).toBe('mock')
  })
  it('sends live resources over fetch with the token and a JSON body', async () => {
    configureTransport({ defaultMode: 'mock', overrides: { hire: 'live' }, base: 'http://api.test' })
    const fetchMock = vi.fn().mockResolvedValue({ status: 201, json: async () => ({ ok: true }) })
    vi.stubGlobal('fetch', fetchMock)
    setTokenProvider(() => 'abc')
    await api.post('/hire/start', { a: 1 }, 'key-1')
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toBe('http://api.test/api/hire/start')
    expect(init.headers).toMatchObject({ Authorization: 'Bearer abc', 'Idempotency-Key': 'key-1', 'Content-Type': 'application/json' })
    expect(JSON.parse(init.body)).toEqual({ a: 1 })
    vi.unstubAllGlobals()
  })
})

describe('client', () => {
  it('turns error replies into ApiError with a code', async () => {
    as('id-hr')
    await expect(api.get('/workflows/instances/nope')).rejects.toBeInstanceOf(ApiError)
    setTokenProvider(() => null)
    await expect(api.get('/approvals')).rejects.toMatchObject({ status: 401, code: 'not_signed_in' })
  })
  it('explains codes in plain words and never leaks internals', () => {
    expect(explain(new ApiError(403, 'maker_checker', 'x'))).toMatch(/someone else/)
    expect(explain(new ApiError(500, 'database_error', 'The database could not complete this request.'))).toMatch(/database/)
    expect(explain(new Error('boom'))).toBe('Something went wrong. Try again.')
  })
  it('adds an idempotency key to every command', async () => {
    const spy = vi.spyOn(transport, 'send')
    as('id-hr')
    await api.post('/tables/position', { status: 'open' })
    expect((spy.mock.calls[0]![2] as transport.SendInit).headers?.['Idempotency-Key']).toBeTruthy()
  })
})

describe('mock backend follows the real API rules', () => {
  it('signs in the nine people-facing roles', async () => {
    expect(DEMO_PEOPLE).toHaveLength(9)
    const r = await mockBackend.handle('POST', '/auth/dev-login', { body: { email: 'rohan.mehta@acme.test' } })
    expect(r.status).toBe(200)
    expect((await mockBackend.handle('POST', '/auth/dev-login', { body: { email: 'x@y.z' } })).status).toBe(401)
  })

  it('limits reads by the contract, not by hand-written rules', async () => {
    as('id-employee')
    await expect(api.get('/tables/position')).rejects.toMatchObject({ code: 'forbidden' })
    as('id-hr')
    const rows = await api.get<{ rows: unknown[]; total: number }>('/tables/position?status=open')
    expect(rows.total).toBe(3)
    await expect(api.get('/tables/position?bogus=1')).rejects.toMatchObject({ code: 'invalid_filter' })
  })

  it('limits workflow timelines to the five roles the database allows', async () => {
    for (const id of ['id-manager', 'id-employee', 'id-it']) { as(id); await expect(api.get('/workflows/instances')).rejects.toMatchObject({ code: 'workflow_not_visible' }) }
    for (const id of ['id-founder', 'id-hr', 'id-payroll', 'id-ops', 'id-auditor']) { as(id); await expect(api.get('/workflows/instances')).resolves.toBeTruthy() }
  })

  it('runs the same hire path as the backend: start, approve as founder, workflow moves on', async () => {
    as('id-hr')
    const started = await api.post<{ instance_id: string; requisition_id: string }>('/hire/start', {
      position_id: 'pos-1', hiring_manager_id: 'e-meera', target_start_date: '2026-12-01', pay_range_min: 1800000, pay_range_max: 2600000 }, 'k1')
    const again = await api.post<{ instance_id: string; replayed?: boolean }>('/hire/start', {
      position_id: 'pos-1', hiring_manager_id: 'e-meera', target_start_date: '2026-12-01', pay_range_min: 1800000, pay_range_max: 2600000 }, 'k1')
    expect(again).toMatchObject({ instance_id: started.instance_id, replayed: true })

    const pending = (await api.get<{ approvals: { id: string; subject_id: string; can_resolve: boolean }[] }>('/approvals?status=pending')).approvals
    const mine = pending.find((a) => a.subject_id === started.requisition_id)!
    expect(mine.can_resolve).toBe(false) // HR is not the approver
    await expect(api.post(`/approvals/${mine.id}/resolve`, { decision: 'approved' })).rejects.toMatchObject({ code: 'wrong_approver_role' })

    as('id-founder')
    await api.post(`/approvals/${mine.id}/resolve`, { decision: 'approved', note: 'ok' })
    await expect(api.post(`/approvals/${mine.id}/resolve`, { decision: 'approved' })).rejects.toMatchObject({ code: 'already_resolved' })
    const wf = await api.get<{ instance: { state: string; status: string } }>(`/workflows/instances/${started.instance_id}`)
    expect(wf.instance).toMatchObject({ state: 's04_job_posting', status: 'running' })
  })

  it('refuses seats that are not open and roles that cannot open requisitions', async () => {
    as('id-hr')
    await expect(api.post('/hire/start', { position_id: 'pos-4', hiring_manager_id: 'e-meera', target_start_date: '2026-12-01', pay_range_min: 1, pay_range_max: 2 })).rejects.toMatchObject({ code: 'no_open_seat' })
    as('id-employee')
    await expect(api.post('/hire/start', { position_id: 'pos-1' })).rejects.toMatchObject({ code: 'forbidden' })
  })

  it('only allows direct writes to allowed tables and fields', async () => {
    as('id-hr')
    await expect(api.post('/tables/job_requisition', { status: 'draft' })).rejects.toMatchObject({ code: 'not_directly_writable' })
    await expect(api.post('/tables/position', { tenant_id: 'x' })).rejects.toMatchObject({ code: 'invalid_fields' })
    const made = await api.post<{ id: string }>('/tables/position', { status: 'open', budgeted_fte: 1 }, 'same')
    const replay = await api.post<{ id: string; replayed?: boolean }>('/tables/position', { status: 'open', budgeted_fte: 1 }, 'same')
    expect(replay).toMatchObject({ id: made.id, replayed: true })
  })
})
