import { useState } from 'react'
import { useCreateRow, useLookups, useTable, useUpdateRow } from '../../api/hooks'
import { explain } from '../../api/errors'
import { useSession } from '../../api/session'
import { humanize, table as contractTable } from '../../contract'
import { Badge, Button, Dialog } from '../../ui'
import { shortDate } from '../shared'

export interface Category { key: string; column: string; jurisdiction: string | null; purpose: string; why: string }
const WHY: Record<string, string> = {
  pan: 'Needed to work out and report your income tax.',
  aadhaar: 'Needed to verify your identity and set up provident fund.',
  ssn: 'Needed for US tax reporting.',
  bank_account: 'Needed to pay your salary.',
}
/** The personal values the platform stores encrypted, taken from the model's encrypted employee columns. */
export function consentCategories(country: string | null): Category[] {
  return contractTable('employee').columns
    .filter((c) => c.enc && c.n !== 'note_body')
    .map((c) => {
      const key = c.n.replace(/_encrypted$/, '').replace(/_ekyc_ref$/, '')
      return { key, column: c.n, jurisdiction: c.jur ?? null, purpose: key === 'bank_account' ? 'payroll_disbursal' : 'identity_verification', why: WHY[key] ?? 'Needed for your employment records.' }
    })
    .filter((c) => !c.jurisdiction || !country || c.jurisdiction === country)
}

export function PrivacyPage() {
  const { session } = useSession()
  const me = session!.employee_id
  const emp = useTable('employee', { id: me ?? '' })
  const { lookups } = useLookups(['location'])
  const consent = useTable('consent_record', { employee_id: me ?? '' })
  const create = useCreateRow('consent_record')
  const update = useUpdateRow('consent_record')
  const [withdrawing, setWithdrawing] = useState<Category | null>(null)
  const [err, setErr] = useState<string | null>(null)
  if (!me) return <div className="stack"><h1>My privacy</h1><p className="notice">This page is for employees.</p></div>
  const country = emp.data?.rows[0] ? String(lookups.location?.[String(emp.data.rows[0].location_id)]?.country_code ?? '') || null : null
  const cats = consentCategories(country)
  const latest = (key: string) => (consent.data?.rows ?? []).filter((c) => c.data_category === key).sort((a, b) => String(b.granted_at).localeCompare(String(a.granted_at)))[0]
  const busy = create.isPending || update.isPending

  const give = (c: Category) => { setErr(null); create.mutate({ key: crypto.randomUUID(), values: { employee_id: me, data_category: c.key, purpose: c.purpose, status: 'granted', granted_at: new Date().toISOString(), consent_artifact_ref: 'web-form' } }, { onError: (e) => setErr(explain(e)) }) }
  const withdraw = (c: Category) => {
    const rec = latest(c.key); if (!rec) return
    update.mutate({ id: String(rec.id), values: { status: 'withdrawn', withdrawn_at: new Date().toISOString() } }, { onSuccess: () => setWithdrawing(null), onError: (e) => { setErr(explain(e)); setWithdrawing(null) } })
  }
  return (
    <div className="stack" style={{ gap: 20 }}>
      <div><h1>My privacy</h1><p className="muted" style={{ marginTop: 6 }}>These details are stored encrypted and only used for the reason given. You decide whether we collect them.</p></div>
      {err && <p role="alert" className="notice notice-danger">{err}</p>}
      <section className="panel" aria-labelledby="consent-h" aria-live="polite">
        <h2 id="consent-h" className="sr-only">Details we ask your consent for</h2>
        {(emp.isPending || consent.isPending) && <p>Loading…</p>}
        {consent.isError && <p role="alert" className="notice notice-danger">{explain(consent.error)}</p>}
        <ul className="list" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
          {cats.map((c) => {
            const rec = latest(c.key)
            const granted = rec?.status === 'granted'
            return (
              <li key={c.key} className="list-row">
                <div style={{ flex: '1 1 320px' }}>
                  <h3>{humanize(c.key)}</h3>
                  <p className="muted" style={{ fontSize: 14 }}>{c.why}</p>
                  <p style={{ marginTop: 6 }}>{granted ? <Badge tone="ok">Consent given {shortDate(rec!.granted_at)}</Badge> : rec?.status === 'withdrawn' ? <Badge tone="warn" mark="◔">Withdrawn {shortDate(rec.withdrawn_at)}</Badge> : <Badge>Not given</Badge>}</p>
                </div>
                {granted
                  ? <Button variant="danger" disabled={busy} onClick={() => setWithdrawing(c)} aria-label={`Withdraw consent for ${humanize(c.key)}`}>Withdraw</Button>
                  : <Button variant="primary" busy={busy} onClick={() => give(c)} aria-label={`Give consent for ${humanize(c.key)}`}>Give consent</Button>}
              </li>
            )
          })}
        </ul>
      </section>
      <Dialog open={withdrawing !== null} title={`Withdraw consent: ${withdrawing ? humanize(withdrawing.key) : ''}`} onClose={() => setWithdrawing(null)}>
        <p>Once you withdraw, this detail is no longer collected or used. You can give consent again later.</p>
        <div className="row" style={{ marginTop: 16 }}><Button variant="danger" busy={update.isPending} onClick={() => withdrawing && withdraw(withdrawing)}>Withdraw consent</Button><Button onClick={() => setWithdrawing(null)}>Keep consent</Button></div>
      </Dialog>
    </div>
  )
}
