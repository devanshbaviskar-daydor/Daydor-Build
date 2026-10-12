import { useState } from 'react'
import { useCreateRow, useLookups, useTable, useUpdateRow } from '../../api/hooks'
import { explain } from '../../api/errors'
import { useSession } from '../../api/session'
import { canReadTable, humanize, writableColumns, type Row, type TableName } from '../../contract'
import { Button, Dialog, ModelForm, ModelTable } from '../../ui'

interface Spec { table: TableName; title: string; columns: string[]; labels?: Record<string, string>; blurb: string }
const SPECS: Spec[] = [
  { table: 'job_profile', title: 'Job profiles', columns: ['title', 'job_family', 'level', 'description'], blurb: 'What each job is. Positions and comp bands point at these.' },
  { table: 'comp_band', title: 'Comp bands', columns: ['job_profile_id', 'location_id', 'band_min', 'band_mid', 'band_max', 'effective_from'], labels: { band_min: 'Minimum', band_mid: 'Midpoint', band_max: 'Maximum' }, blurb: 'The pay range for a job. An offer outside its band goes to the founder.' },
  { table: 'access_role_template', title: 'Access templates', columns: ['job_profile_id', 'department_id', 'app_bundle'], blurb: 'The apps a new hire gets by default for a job. Anything outside the template needs approval.' },
  { table: 'skill', title: 'Skills', columns: ['name', 'category'], blurb: 'The skills catalogue people can be rated against.' },
  { table: 'leave_policy', title: 'Leave policies', columns: ['legal_entity_id', 'leave_type', 'carry_forward_cap'], blurb: 'Accrual runs against these (days per month, read from accrual_rule) until the carry-forward cap.' },
  { table: 'benefit_plan', title: 'Benefit plans', columns: ['legal_entity_id', 'plan_type', 'carrier', 'plan_year', 'employer_contribution'], blurb: 'What employees can elect into on the Benefits tab of Time and leave.' },
  { table: 'statutory_rate_rule', title: 'Statutory rates', columns: ['scheme', 'jurisdiction_code', 'effective_from', 'wage_ceiling', 'employee_rate', 'employer_rate'], blurb: "Global, not tenant-owned -- Daydor ops maintains these jurisdiction packs. Payroll's gross-to-net computation reads them, not hardcoded numbers. Illustrative, not compliance-grade." },
  { table: 'pt_slab_rule', title: 'PT slabs (India)', columns: ['state_code', 'effective_from', 'slab_min', 'slab_max', 'monthly_amount'], blurb: 'Global professional-tax slabs by state, maintained by Daydor ops.' },
]

export function ReferenceDataPage() {
  const { session } = useSession()
  const role = session!.role
  const specs = SPECS.filter((s) => canReadTable(s.table, role))
  const [active, setActive] = useState(specs[0]?.table ?? 'job_profile')
  const spec = specs.find((s) => s.table === active) ?? specs[0]
  const { lookups } = useLookups(['job_profile', 'department', 'location', 'legal_entity'])
  const q = useTable(spec?.table ?? 'job_profile', { limit: '200' })
  const create = useCreateRow(spec?.table ?? 'job_profile')
  const update = useUpdateRow(spec?.table ?? 'job_profile')
  const [editing, setEditing] = useState<Row | 'new' | null>(null)
  const [key, setKey] = useState(() => crypto.randomUUID())
  if (!spec) return <div className="stack"><h1>Reference data</h1><p className="notice">Your role cannot see reference data.</p></div>
  // Per-column access, not the table-level summary: a table's own grant can look like write
  // (e.g. statutory_rate_rule's table_acl shows daydor_ops at write level) while every actual
  // column grant for that role is read-only -- the same "summary isn't the real picture" shape
  // as finding 16 (benefit_election) and the time_punch finding, confirmed by inspecting the
  // backend's own GRANT statements (docs/integration-notes.md).
  const canEdit = writableColumns(spec.table, role).length > 0
  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="spread"><h1>Reference data</h1>{canEdit && <Button variant="primary" onClick={() => { setKey(crypto.randomUUID()); setEditing('new') }}>Add {humanize(spec.table).toLowerCase()}</Button>}</div>
      <div className="tabs" role="group" aria-label="Reference data">
        {specs.map((s) => <button key={s.table} type="button" className="tab" aria-pressed={s.table === spec.table} onClick={() => { setActive(s.table); setEditing(null) }}>{s.title}</button>)}
      </div>
      <section className="panel" aria-label={spec.title} aria-live="polite">
        <p className="muted" style={{ marginBottom: 12 }}>{spec.blurb}{!canEdit && ' Your role can view this but not change it.'}</p>
        {q.isPending && <p>Loading…</p>}
        {q.isError && <p role="alert" className="notice notice-danger">{explain(q.error)}</p>}
        {q.data && (
          <ModelTable table={spec.table} caption={spec.title} role={role} rows={q.data.rows} lookups={lookups} columns={spec.columns} labels={spec.labels}
            cells={spec.table === 'access_role_template' ? { app_bundle: (r) => ((r.app_bundle as { apps?: string[] } | null)?.apps ?? []).join(', ') || 'None' } : {}}
            empty="Nothing here yet."
            actions={canEdit ? (r) => <Button variant="quiet" onClick={() => { setKey(crypto.randomUUID()); setEditing(r) }} aria-label={`Edit ${humanize(spec.table).toLowerCase()}`}>Edit</Button> : undefined} />
        )}
      </section>
      <Dialog open={editing !== null} title={`${editing === 'new' ? 'Add' : 'Edit'} ${humanize(spec.table).toLowerCase()}`} onClose={() => setEditing(null)}>
        {editing !== null && (
          <ModelForm table={spec.table} role={role} lookups={lookups} fields={spec.columns} initial={editing === 'new' ? {} : editing} submitLabel={editing === 'new' ? 'Add' : 'Save changes'}
            labels={spec.labels} busy={create.isPending || update.isPending} error={create.isError ? explain(create.error) : update.isError ? explain(update.error) : null}
            onCancel={() => setEditing(null)}
            onSubmit={(values) => editing === 'new' ? create.mutate({ values, key }, { onSuccess: () => setEditing(null) }) : update.mutate({ id: String(editing.id), values }, { onSuccess: () => setEditing(null) })} />
        )}
      </Dialog>
    </div>
  )
}
