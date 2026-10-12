import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api, setTokenProvider, setUnauthorizedHandler } from './client'
import type { Session } from './types'

// Bump the version when the stored shape changes, so an old saved session is dropped instead of crashing the app.
const KEY = 'daydor.session.v3'
interface Stored { token: string; session: Session }

function valid(v: unknown): v is Stored {
  const s = (v as Stored | null)?.session
  return typeof (v as Stored | null)?.token === 'string' && !!s && typeof s.role === 'string' && typeof s.capabilities?.workflow_timeline === 'boolean' && typeof s.capabilities?.directory === 'boolean'
}
function load(): Stored | null {
  try {
    localStorage.removeItem('daydor.session') // the pre-v2 key
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    if (valid(parsed)) return parsed
    localStorage.removeItem(KEY)
    return null
  } catch { return null }
}
function save(v: Stored | null) {
  try { if (v) localStorage.setItem(KEY, JSON.stringify(v)); else localStorage.removeItem(KEY) } catch { /* storage unavailable: stay signed in for this tab only */ }
}

interface Ctx { session: Session | null; signIn: (email: string) => Promise<void>; signOut: () => void }
const SessionContext = createContext<Ctx | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const [stored, setStored] = useState<Stored | null>(load)
  const qc = useQueryClient()
  setTokenProvider(() => stored?.token ?? null)

  const signOut = useCallback(() => { save(null); setStored(null); qc.clear() }, [qc])
  useEffect(() => { setUnauthorizedHandler(signOut) }, [signOut])

  const signIn = useCallback(async (email: string) => {
    const r = await api.post<{ token: string; session: Session }>('/auth/dev-login', { email })
    const next = { token: r.token, session: r.session }
    setTokenProvider(() => next.token)
    save(next); setStored(next); qc.clear()
  }, [qc])

  const value = useMemo(() => ({ session: stored?.session ?? null, signIn, signOut }), [stored, signIn, signOut])
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): Ctx {
  const c = useContext(SessionContext)
  if (!c) throw new Error('useSession must be used inside SessionProvider')
  return c
}
