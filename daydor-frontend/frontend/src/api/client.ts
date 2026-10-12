import { ApiError } from './errors'
import { send } from './transport'

let tokenProvider: () => string | null = () => null
let onUnauthorized: () => void = () => {}
export function setTokenProvider(fn: () => string | null) { tokenProvider = fn }
export function setUnauthorizedHandler(fn: () => void) { onUnauthorized = fn }

async function request<T>(method: string, path: string, body?: unknown, headers?: Record<string, string>): Promise<T> {
  const reply = await send(method, path, { body, token: tokenProvider(), headers })
  if (reply.status >= 200 && reply.status < 300) return reply.json as T
  const err = (reply.json as { error?: { code?: string; message?: string } } | null)?.error
  if (reply.status === 401 && err?.code !== 'unknown_account') onUnauthorized()
  throw new ApiError(reply.status, err?.code ?? 'error', err?.message ?? 'The request failed.')
}

const newKey = () => (globalThis.crypto?.randomUUID?.() ?? `k-${Date.now()}-${Math.random().toString(16).slice(2)}`)

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown, idempotencyKey: string = newKey()) =>
    request<T>('POST', path, body, { 'Idempotency-Key': idempotencyKey }),
  patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
}
