import { NavLink, Outlet } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useDevUsers } from '../../api/hooks'
import { useSession } from '../../api/session'
import { isFullyMock, modeSummary } from '../../api/transport'
import { Badge, Button } from '../../ui'
import { navFor } from './nav'

function ModeBadge() {
  if (isFullyMock()) return <Badge tone="outline" title="Everything on screen is sample data. Nothing is saved to a database.">Sample data</Badge>
  const live = modeSummary().filter((m) => m.mode === 'live').map((m) => m.resource)
  return <Badge tone="accent" title="These parts talk to the real API; the rest is sample data.">Live: {live.join(', ')}</Badge>
}

/** Development only: sign in as another person without typing an email. */
function RoleSwitcher() {
  const { session, signIn } = useSession()
  const qc = useQueryClient()
  const users = useDevUsers()
  if (!session || !users.data) return null
  return (
    <div>
      <label className="sr-only" htmlFor="switch-role">Switch account (development only)</label>
      <select id="switch-role" className="input" style={{ minHeight: 40, width: 'auto' }} value={session.email}
        onChange={async (e) => { await signIn(e.target.value); void qc.invalidateQueries() }}>
        {users.data.users.map((u) => <option key={u.id} value={u.email}>{u.display_name} · {u.role_label}</option>)}
      </select>
    </div>
  )
}

export function Shell() {
  const { session, signOut } = useSession()
  if (!session) return null
  const { ready, soon } = navFor(session.role, session.capabilities ?? { workflow_timeline: false, directory: false }, !!session.employee_id)
  return (
    <div className="shell">
      <nav className="sidebar" aria-label="Primary">
        <div className="brand"><span className="brand-mark" aria-hidden="true">D</span>Daydor</div>
        {ready.map((i) => <NavLink key={i.to} to={i.to} end={i.to === '/'} className="nav-link">{i.label}</NavLink>)}
        <NavLink to="/dev/primitives" className="nav-link">Design primitives</NavLink>
        {soon.length > 0 && <div className="nav-group">Coming next</div>}
        {soon.map((s) => <div key={s} className="nav-soon">{s}</div>)}
      </nav>
      <div className="main">
        <header className="topbar">
          <div className="row"><strong>{session.tenant_name ?? 'Daydor platform'}</strong><ModeBadge /></div>
          <div className="who">
            <RoleSwitcher />
            <span>{session.display_name}<span className="muted"> · {session.role_label}</span></span>
            <Button variant="quiet" onClick={signOut}>Sign out</Button>
          </div>
        </header>
        <main id="main"><Outlet /></main>
      </div>
    </div>
  )
}
