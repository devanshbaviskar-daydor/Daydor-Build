import { useLookups, useTable } from '../../api/hooks'
import { explain } from '../../api/errors'
import { useSession } from '../../api/session'
import { enumLabel, humanize, labelFor, type Row } from '../../contract'
import { Badge, MockAdapterBadge, TimerCountdown } from '../../ui'
import { shortDate } from '../shared'

const isDone = (t: Row) => !!t.completed_at

export function OnboardingPage() {
  const { session } = useSession()
  const checklists = useTable('checklist', { limit: '100' })
  const ids = (checklists.data?.rows ?? []).map((c) => String(c.id)).join(',')
  const tasks = useTable('checklist_task', ids ? { checklist_id__in: ids, limit: '200' } : { checklist_id__in: '-' })
  const identities = useTable('identity_account', { limit: '100' })
  const { lookups } = useLookups(['employee'])
  void session
  return (
    <div className="stack" style={{ gap: 20 }}>
      <h1>Onboarding</h1>
      {checklists.isPending && <p aria-live="polite">Loading…</p>}
      {checklists.isError && <p role="alert" className="notice notice-danger">{explain(checklists.error)}</p>}
      {checklists.data && checklists.data.rows.length === 0 && <p className="panel muted">Nobody is onboarding right now. A checklist appears once a new hire reaches the onboarding step of the hire flow.</p>}
      {(checklists.data?.rows ?? []).map((c) => {
        const mine = (tasks.data?.rows ?? []).filter((t) => t.checklist_id === c.id)
        const done = mine.filter(isDone).length
        const who = lookups.employee?.[String(c.employee_id)]
        const identity = (identities.data?.rows ?? []).find((i) => i.employee_id === c.employee_id)
        const owners = [...new Set(mine.map((t) => String(t.owner_domain)))]
        return (
          <article key={String(c.id)} className="panel" aria-label={`Onboarding for ${who ? labelFor('employee', who) : 'a new hire'}`}>
            <div className="spread">
              <div><h2>{who ? labelFor('employee', who) : 'New hire'}</h2><p className="muted" style={{ fontSize: 14 }}>{humanize(String(c.kind))} checklist · due {shortDate(c.due_date)}</p></div>
              <div className="row"><Badge tone={done === mine.length && mine.length > 0 ? 'ok' : 'accent'}>{done} of {mine.length} tasks done</Badge><Badge>{enumLabel('checklist', 'status', String(c.status))}</Badge></div>
            </div>
            {identity && (
              <p style={{ marginTop: 12 }}>Single sign-on account: <strong>{enumLabel('identity_account', 'status', String(identity.status))}</strong> <MockAdapterBadge vendor="identity provider" /></p>
            )}
            {owners.map((o) => (
              <section key={o} aria-label={`${humanize(o)} tasks`} style={{ marginTop: 16 }}>
                <h3>{humanize(o)}</h3>
                <ul className="list" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                  {mine.filter((t) => t.owner_domain === o).map((t) => (
                    <li key={String(t.id)} className="list-row">
                      <div><span style={{ fontWeight: 600 }}>{String(t.title)}</span>{t.blocking ? <> <Badge tone="outline" title="This has to be finished before the first day.">Needed before day one</Badge></> : null}</div>
                      {isDone(t) ? <Badge tone="ok">Done {shortDate(t.completed_at)}</Badge> : <TimerCountdown dueAt={String(t.due_at)} label="Due" />}
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </article>
        )
      })}
    </div>
  )
}
