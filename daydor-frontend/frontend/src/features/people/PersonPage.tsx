import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useLookups, useTable } from '../../api/hooks'
import { explain } from '../../api/errors'
import { useSession } from '../../api/session'
import { canReadTable, labelFor, type TableName } from '../../contract'
import { AccessTab, ContactsTab, DocumentsTab, JobTab, OverviewTab, PayTab, SkillsTab } from './PersonTabs'

const TABS: { id: string; label: string; table: TableName; Panel: typeof OverviewTab }[] = [
  { id: 'overview', label: 'Overview', table: 'employee', Panel: OverviewTab },
  { id: 'job', label: 'Job and pay', table: 'employment_record', Panel: JobTab },
  { id: 'contacts', label: 'Emergency contacts', table: 'emergency_contact', Panel: ContactsTab },
  { id: 'skills', label: 'Skills', table: 'employee_skill', Panel: SkillsTab },
  { id: 'access', label: 'Access', table: 'identity_account', Panel: AccessTab },
  { id: 'pay', label: 'Payroll and payslips', table: 'payroll_profile', Panel: PayTab },
  { id: 'docs', label: 'Consent and documents', table: 'consent_record', Panel: DocumentsTab },
]

export function PersonPage() {
  const { id } = useParams()
  const { session } = useSession()
  const role = session!.role
  const emp = useTable('employee', { id: id ?? '' })
  const { lookups } = useLookups(['department', 'location', 'job_profile', 'skill', 'comp_band', 'employee'])
  const tabs = useMemo(() => TABS.filter((t) => canReadTable(t.table, role)), [role])
  const [active, setActive] = useState('overview')
  const employee = emp.data?.rows[0]
  const country = employee ? String(lookups.location?.[String(employee.location_id)]?.country_code ?? '') || null : null
  const tab = tabs.find((t) => t.id === active) ?? tabs[0]

  if (emp.isPending) return <p aria-live="polite">Loading…</p>
  if (emp.isError || !employee || !tab) {
    return (
      <div className="stack"><h1>{emp.isError ? 'Person unavailable' : 'Person not visible'}</h1>
        {emp.isError ? <p role="alert" className="notice notice-danger">{explain(emp.error)}</p> : <p className="notice">Your role cannot see this person’s record. The People page shows what your role may see about colleagues.</p>}
        <Link to="/people" className="btn btn-quiet" style={{ alignSelf: 'flex-start', paddingLeft: 0 }}>Back to people</Link></div>
    )
  }
  const Panel = tab.Panel
  return (
    <div className="stack" style={{ gap: 20 }}>
      <Link to="/people" className="btn btn-quiet" style={{ alignSelf: 'flex-start', paddingLeft: 0 }}>Back to people</Link>
      <div><h1>{labelFor('employee', employee)}</h1>
        <p className="muted" style={{ marginTop: 6 }}>{lookups.department?.[String(employee.department_id)] ? labelFor('department', lookups.department[String(employee.department_id)]!) : ''}{country ? ` · ${country === 'IN' ? 'India' : country === 'US' ? 'United States' : country}` : ''}</p></div>
      <div role="tablist" aria-label="Person sections" className="tabs">
        {tabs.map((t) => <button key={t.id} id={`tab-${t.id}`} role="tab" type="button" className="tab" aria-selected={t.id === tab.id} aria-controls={`panel-${t.id}`} onClick={() => setActive(t.id)}
          style={t.id === tab.id ? { background: 'var(--accent)', borderColor: 'var(--accent)', color: 'var(--accent-ink)' } : undefined}>{t.label}</button>)}
      </div>
      <div role="tabpanel" id={`panel-${tab.id}`} aria-labelledby={`tab-${tab.id}`}>
        <Panel employeeId={String(employee.id)} role={role} lookups={lookups} country={country} employee={employee} />
      </div>
    </div>
  )
}
