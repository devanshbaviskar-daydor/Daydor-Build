import { useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useDevUsers } from '../../api/hooks'
import { useSession } from '../../api/session'
import { explain } from '../../api/errors'
import { Button } from '../../ui'

export function SignInPage() {
  const { session, signIn } = useSession()
  const users = useDevUsers()
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const from = (useLocation().state as { from?: string } | null)?.from
  if (session) return <Navigate to={from && from !== '/sign-in' ? from : '/'} replace />

  const go = async (email: string) => {
    setBusy(email); setError(null)
    try { await signIn(email) } catch (e) { setError(explain(e)) } finally { setBusy(null) }
  }
  return (
    <div className="main" style={{ maxWidth: 640, margin: '0 auto' }}>
      <div className="brand" style={{ padding: 0 }}><span className="brand-mark" aria-hidden="true">D</span>Daydor</div>
      <h1>Sign in</h1>
      <p className="muted">This is the development sign-in: pick an account to continue. A company sign-in replaces it before launch.</p>
      {error && <p role="alert" className="notice notice-danger">{error}</p>}
      {users.isPending && <p aria-live="polite">Loading accounts…</p>}
      {users.isError && <p role="alert" className="notice notice-danger">Accounts could not be loaded. {explain(users.error)}</p>}
      <ul className="list panel" style={{ listStyle: 'none', margin: 0 }}>
        {users.data?.users.map((u) => (
          <li key={u.id} className="list-row">
            <div><strong>{u.display_name}</strong><div className="muted" style={{ fontSize: 13 }}>{u.role_label} · {u.email}</div></div>
            <Button variant="primary" busy={busy === u.email} disabled={busy !== null} onClick={() => void go(u.email)} aria-label={`Sign in as ${u.display_name}`}>Sign in</Button>
          </li>
        ))}
      </ul>
    </div>
  )
}
