import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useCreateRow, useTable, useUpdateRow } from '../../api/hooks'
import { explain } from '../../api/errors'
import { canWriteTable, column, fieldState, humanize, jurisdictionColumns, labelFor, money, table as contractTable, writableColumns, type Row, type TableName } from '../../contract'
import { Badge, Button, ConsentRequired, Dialog, FieldValue, MockAdapterBadge, ModelForm, ModelTable, type Lookups } from '../../ui'
import { consentCategories } from '../privacy/PrivacyPage'
import { dateTime, shortDate } from '../shared'

interface TabProps { employeeId: string; role: string; lookups: Lookups; country: string | null; employee: Row }
const Err = ({ e }: { e: unknown }) => <p role="alert" className="notice notice-danger">{explain(e)}</p>

function Labelled({ table, col, row, role, lookups }: { table: TableName; col: string; row: Row; role: string; lookups: Lookups }) {
  const fk = column(table, col)?.fk
  const st = fieldState(table, col, role)
  return (
    <div className="field"><dt className="field-label">{humanize(col)}</dt>
      <dd className="field-value" style={{ margin: 0 }}>
        {fk && row[col] && st.kind !== 'hidden' ? (lookups[fk]?.[String(row[col])] ? labelFor(fk, lookups[fk]![String(row[col])]!) : <span className="restricted">Not visible</span>) : <FieldValue table={table} column={col} value={row[col]} role={role} />}
      </dd></div>
  )
}

export function OverviewTab({ employeeId, role, lookups, country, employee }: TabProps) {
  const consent = useTable('consent_record', { employee_id: employeeId })
  const cols = ['full_name', 'work_email', 'employment_type', 'department_id', 'location_id', 'state_code', 'date_of_joining', 'date_of_birth', 'personal_address', ...(country === 'IN' || !country ? ['aadhaar_last4'] : [])]
  const cats = consentCategories(country)
  const latest = (key: string) => (consent.data?.rows ?? []).filter((c) => c.data_category === key).sort((a, b) => String(b.granted_at).localeCompare(String(a.granted_at)))[0]
  return (
    <div className="stack" style={{ gap: 20 }}>
      <section className="panel" aria-labelledby="det"><h2 id="det">Details</h2><dl className="grid-2" style={{ margin: 0 }}>{cols.map((c) => <Labelled key={c} table="employee" col={c} row={employee} role={role} lookups={lookups} />)}</dl></section>
      <section className="panel" aria-labelledby="sens">
        <h2 id="sens">Sensitive details</h2>
        <p className="muted" style={{ fontSize: 14, marginBottom: 12 }}>Stored encrypted. They are only shown for an approved purpose, and only after the employee has given consent.</p>
        <dl className="grid-2" style={{ margin: 0 }}>
          {cats.map((c) => {
            const st = fieldState('employee', c.column, role)
            const rec = latest(c.key)
            return (
              <div key={c.key} className="field"><dt className="field-label">{humanize(c.key)}</dt>
                <dd className="field-value" style={{ margin: 0 }}>
                  {st.kind === 'hidden' ? <span className="restricted">Your role cannot see this.</span>
                    : consent.isError ? <span className="restricted">Consent status is not visible to your role.</span>
                    : rec?.status === 'granted' ? <>Collected. <span className="muted">Consent given {shortDate(rec.granted_at)}.</span></>
                    : <ConsentRequired state={rec?.status === 'withdrawn' ? 'withdrawn' : 'missing'} />}
                </dd></div>
            )
          })}
        </dl>
      </section>
    </div>
  )
}

export function JobTab({ employeeId, role, lookups, country }: TabProps) {
  const records = useTable('employment_record', { employee_id: employeeId })
  const extra = country ? jurisdictionColumns('employment_record', country as 'IN' | 'US').map((c) => c.n) : []
  return (
    <section className="panel" aria-labelledby="job">
      <h2 id="job">Employment</h2>
      {records.isPending && <p>Loading…</p>}{records.isError && <Err e={records.error} />}
      {records.data && <ModelTable table="employment_record" caption="Employment records" role={role} rows={records.data.rows} lookups={lookups}
        columns={['job_profile_id', 'comp_band_id', 'fte', 'ctc_annual', 'basic_da_monthly', 'effective_from', 'effective_to', ...extra]}
        labels={{ ctc_annual: 'Cost to company a year', basic_da_monthly: 'Basic a month' }} empty="No employment record yet." />}
    </section>
  )
}

export function ContactsTab({ employeeId, role }: TabProps) {
  const q = useTable('emergency_contact', { employee_id: employeeId })
  const create = useCreateRow('emergency_contact'); const update = useUpdateRow('emergency_contact')
  const [editing, setEditing] = useState<Row | 'new' | null>(null)
  const [key, setKey] = useState(() => crypto.randomUUID())
  const can = canWriteTable('emergency_contact', role)
  return (
    <section className="panel" aria-labelledby="ec">
      <div className="spread"><h2 id="ec">Emergency contacts</h2>{can && <Button variant="primary" onClick={() => { setKey(crypto.randomUUID()); setEditing('new') }}>Add a contact</Button>}</div>
      {q.isPending && <p>Loading…</p>}{q.isError && <Err e={q.error} />}
      {q.data && <ModelTable table="emergency_contact" caption="Emergency contacts" role={role} rows={q.data.rows} columns={['priority', 'contact_name', 'relationship', 'phone']} empty="No emergency contact yet."
        actions={can ? (r) => <Button variant="quiet" onClick={() => { setKey(crypto.randomUUID()); setEditing(r) }} aria-label={`Edit ${String(r.contact_name)}`}>Edit</Button> : undefined} />}
      {!can && <p className="muted" style={{ fontSize: 14, marginTop: 12 }}>Only HR and the employee can change these.</p>}
      <Dialog open={editing !== null} title={editing === 'new' ? 'Add an emergency contact' : 'Edit emergency contact'} onClose={() => setEditing(null)}>
        {editing !== null && <ModelForm table="emergency_contact" role={role} fields={['contact_name', 'relationship', 'phone', 'priority']} fixed={{ employee_id: employeeId }} initial={editing === 'new' ? {} : editing}
          submitLabel={editing === 'new' ? 'Add contact' : 'Save changes'} busy={create.isPending || update.isPending} error={create.isError ? explain(create.error) : update.isError ? explain(update.error) : null} onCancel={() => setEditing(null)}
          onSubmit={(values) => editing === 'new' ? create.mutate({ values, key }, { onSuccess: () => setEditing(null) }) : update.mutate({ id: String(editing.id), values: Object.fromEntries(Object.entries(values).filter(([k]) => k !== 'employee_id')) }, { onSuccess: () => setEditing(null) })} />}
      </Dialog>
    </section>
  )
}

export function SkillsTab({ employeeId, role, lookups }: TabProps) {
  const q = useTable('employee_skill', { employee_id: employeeId })
  const create = useCreateRow('employee_skill')
  const [adding, setAdding] = useState(false)
  const [key, setKey] = useState(() => crypto.randomUUID())
  const canRate = writableColumns('employee_skill', role).some((c) => c.n === 'proficiency_level')
  return (
    <section className="panel" aria-labelledby="sk">
      <div className="spread"><h2 id="sk">Skills</h2>{canRate && <Button variant="primary" onClick={() => { setKey(crypto.randomUUID()); setAdding(true) }}>Rate a skill</Button>}</div>
      {q.isPending && <p>Loading…</p>}{q.isError && <Err e={q.error} />}
      {q.data && <ModelTable table="employee_skill" caption="Skills" role={role} rows={q.data.rows} lookups={lookups} columns={['skill_id', 'proficiency_level', 'source', 'last_updated']} labels={{ skill_id: 'Skill', proficiency_level: 'Level (1 to 5)' }} empty="No skills rated yet." />}
      {!canRate && <p className="muted" style={{ fontSize: 14, marginTop: 12 }}>Only HR can rate skills. You can add one to the catalogue under Reference data if HR has not yet.</p>}
      <Dialog open={adding} title="Rate a skill" onClose={() => setAdding(false)}>
        <ModelForm table="employee_skill" role={role} lookups={lookups} fields={['skill_id', 'proficiency_level', 'source']} fixed={{ employee_id: employeeId, last_updated: new Date().toISOString() }}
          labels={{ skill_id: 'Skill', proficiency_level: 'Level (1 to 5)' }} submitLabel="Save rating" busy={create.isPending} error={create.isError ? explain(create.error) : null} onCancel={() => setAdding(false)}
          onSubmit={(values) => create.mutate({ values, key }, { onSuccess: () => setAdding(false) })} />
      </Dialog>
    </section>
  )
}

export function AccessTab({ employeeId, role, lookups }: TabProps) {
  const ids = useTable('identity_account', { employee_id: employeeId })
  const accountIds = (ids.data?.rows ?? []).map((a) => String(a.id)).join(',')
  const grants = useTable('app_access_grant', accountIds ? { identity_account_id__in: accountIds } : { identity_account_id__in: '-' })
  return (
    <div className="stack" style={{ gap: 20 }}>
      <section className="panel" aria-labelledby="ia">
        <div className="row"><h2 id="ia">Single sign-on account</h2><MockAdapterBadge vendor="identity provider" /></div>
        {ids.isPending && <p>Loading…</p>}{ids.isError && <Err e={ids.error} />}
        {ids.data && <ModelTable table="identity_account" caption="Identity accounts" role={role} rows={ids.data.rows} lookups={lookups} columns={['directory_provider', 'external_id', 'status', 'provisioned_at']} labels={{ directory_provider: 'Provider', external_id: 'Account name' }} empty="No account yet. It is created during onboarding." />}
      </section>
      <section className="panel" aria-labelledby="ag">
        <h2 id="ag">App access</h2>
        {grants.data && <ModelTable table="app_access_grant" caption="App access" role={role} rows={grants.data.rows} columns={['app_name', 'permission_level', 'source', 'granted_at', 'approval_request_id']} labels={{ app_name: 'App', permission_level: 'Level', approval_request_id: 'Approval' }}
          cells={{ approval_request_id: (g) => (g.approval_request_id ? <Link to={`/approvals/${String(g.approval_request_id)}`} className="btn btn-quiet" style={{ paddingLeft: 0, minHeight: 32 }}>Open approval</Link> : <span className="muted">Standard access</span>) }} empty="No access granted yet." />}
        <p className="muted" style={{ fontSize: 14, marginTop: 12 }}>Access outside the job’s template goes to IT for approval first.</p>
      </section>
    </div>
  )
}

export function PayTab({ employeeId, role, country }: TabProps) {
  const profile = useTable('payroll_profile', { employee_id: employeeId })
  const slips = useTable('payslip', { employee_id: employeeId })
  const [open, setOpen] = useState<Row | null>(null)
  const lines = useTable('payslip_line', { payslip_id: open ? String(open.id) : '-' })
  const p = profile.data?.rows[0]
  const common = ['pay_frequency', 'payment_method', 'work_state']
  const specific = country ? jurisdictionColumns('payroll_profile', country as 'IN' | 'US').map((c) => c.n) : []
  return (
    <div className="stack" style={{ gap: 20 }}>
      <section className="panel" aria-labelledby="pp">
        <h2 id="pp">Payroll profile</h2>
        {profile.isPending && <p>Loading…</p>}{profile.isError && <Err e={profile.error} />}
        {profile.data && !p && <p className="muted">No payroll profile yet. It is created when the hire is set up for pay.</p>}
        {p && <dl className="grid-2" style={{ margin: 0 }}>{[...common, ...specific].map((c) => <Labelled key={c} table="payroll_profile" col={c} row={p} role={role} lookups={{}} />)}</dl>}
        {p && country && <p className="muted" style={{ fontSize: 14, marginTop: 12 }}>{country === 'IN' ? 'Showing India fields: provident fund and ESIC numbers.' : 'Showing US fields: state tax and W-4.'}</p>}
      </section>
      <section className="panel" aria-labelledby="slips">
        <div className="row"><h2 id="slips">Payslips</h2><MockAdapterBadge vendor="bank" /><Badge tone="outline" title="One flat rate per statutory scheme, not real slabs, exemptions or YTD caps.">Illustrative tax figures</Badge></div>
        {slips.data && slips.data.rows.length === 0 && <p className="muted">No payslip yet. The first one is issued after the first payroll run.</p>}
        {slips.data && slips.data.rows.length > 0 && (
          <ModelTable table="payslip" caption="Payslips" role={role} rows={slips.data.rows} columns={['issued_at', 'gross_pay', 'tax_withheld', 'net_pay']} labels={{ tax_withheld: 'Tax withheld', net_pay: 'Take-home' }}
            actions={(r) => <Button variant="quiet" onClick={() => setOpen(r)} aria-label={`View payslip issued ${shortDate(r.issued_at)}`}>View</Button>} />
        )}
        <p className="muted" style={{ fontSize: 14, marginTop: 12 }}>Payments are simulated for now: nothing is sent to a bank.</p>
      </section>
      <Dialog open={open !== null} title={`Payslip, ${open ? dateTime(open.issued_at) : ''}`} onClose={() => setOpen(null)}>
        {lines.isPending && <p>Loading…</p>}{lines.isError && <Err e={lines.error} />}
        {lines.data && <table className="data" style={{ minWidth: 0 }}><caption className="sr-only">Payslip lines</caption>
          <thead><tr><th scope="col">Component</th><th scope="col" style={{ textAlign: 'right' }}>Amount</th></tr></thead>
          <tbody>{lines.data.rows.map((l) => <tr key={String(l.id)}><td>{String(l.component_code)}</td><td style={{ textAlign: 'right' }}>{money(l.amount)}</td></tr>)}</tbody></table>}
        {open && <p style={{ marginTop: 12 }}><strong>Take-home {money(open.net_pay)}</strong> <span className="muted">from {money(open.gross_pay)} before deductions.</span></p>}
      </Dialog>
    </div>
  )
}

export function DocumentsTab({ employeeId, role }: TabProps) {
  const consent = useTable('consent_record', { employee_id: employeeId })
  const docs = useTable('document', { subject_id: employeeId })
  return (
    <div className="stack" style={{ gap: 20 }}>
      <section className="panel" aria-labelledby="cn"><h2 id="cn">Consent</h2>
        {consent.isError && <Err e={consent.error} />}
        {consent.data && <ModelTable table="consent_record" caption="Consent" role={role} rows={consent.data.rows} columns={['data_category', 'purpose', 'status', 'granted_at', 'withdrawn_at']} labels={{ data_category: 'Detail' }} empty="No consent recorded yet."
          cells={{ status: (r) => <Badge tone={r.status === 'granted' ? 'ok' : 'warn'} mark={r.status === 'granted' ? '✓' : '◔'}>{humanize(String(r.status))}</Badge> }} />}
      </section>
      <section className="panel" aria-labelledby="dc"><h2 id="dc">Documents</h2>
        {docs.isError && <Err e={docs.error} />}
        {docs.data && <ModelTable table="document" caption="Documents" role={role} rows={docs.data.rows} columns={['document_class', 'signed_at', 'created_at']} labels={{ document_class: 'Document', created_at: 'Added' }} empty="No documents yet." />}
        <p className="muted" style={{ fontSize: 14, marginTop: 12 }}>Documents are listed here; opening them needs the document store, which is not connected yet.</p>
      </section>
    </div>
  )
}
export { contractTable }
