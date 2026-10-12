// One seam between the app and its data. Each resource (the first path segment, such as
// "approvals") is either `mock` or `live`, so a flow step moves to the real API by changing
// configuration, not code. Both modes go through the same client, so error handling, tokens and
// idempotency keys behave identically.
import { mockBackend } from '../mocks/router'

export type Mode = 'mock' | 'live'
export interface Reply { status: number; json: unknown }
export interface SendInit { body?: unknown; token?: string | null; headers?: Record<string, string> }

function parseModes(raw: string | undefined): Record<string, Mode> {
  const out: Record<string, Mode> = {}
  for (const pair of (raw ?? '').split(',')) {
    const [k, v] = pair.split(':').map((s) => s.trim())
    if (k && (v === 'mock' || v === 'live')) out[k] = v
  }
  return out
}

const env = import.meta.env
let defaultMode: Mode = env.VITE_API_MODE === 'live' ? 'live' : 'mock'
let overrides = parseModes(env.VITE_RESOURCE_MODES)
let base: string = env.VITE_API_BASE ?? 'http://localhost:8000'

export function configureTransport(c: { defaultMode?: Mode; overrides?: Record<string, Mode>; base?: string }) {
  if (c.defaultMode) defaultMode = c.defaultMode
  if (c.overrides) overrides = c.overrides
  if (c.base) base = c.base
}
export const resourceOf = (path: string) => path.replace(/^\//, '').split(/[/?]/)[0] ?? ''
export const modeFor = (path: string): Mode => overrides[resourceOf(path)] ?? defaultMode
export const isFullyMock = () => defaultMode === 'mock' && Object.values(overrides).every((m) => m === 'mock')
export const modeSummary = (): { resource: string; mode: Mode }[] =>
  ['auth', 'meta', 'tables', 'approvals', 'workflows', 'hire'].map((resource) => ({ resource, mode: modeFor(resource) }))

export async function send(method: string, path: string, init: SendInit = {}): Promise<Reply> {
  if (modeFor(path) === 'mock') return mockBackend.handle(method, path, init)
  const res = await fetch(`${base}/api${path}`, {
    method,
    headers: {
      ...(init.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(init.token ? { Authorization: `Bearer ${init.token}` } : {}),
      ...init.headers,
    },
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  })
  let json: unknown = null
  try { json = await res.json() } catch { /* empty body */ }
  return { status: res.status, json }
}
