import { useMemo, useState } from 'react'
import { useCreateRow, useLookups, useTable, useUpdateRow } from '../../api/hooks'
import { explain } from '../../api/errors'
import { useSession } from '../../api/session'
import { canWriteTable, labelFor, type Row } from '../../contract'
import { Badge, Button, Dialog, ModelForm, ModelTable } from '../../ui'
import { StartHireDialog } from '../requisitions/StartHireDialog'

type Tab = 'open' | 'filled' | 'all'
const isOpenSeat = (p: Row) => p.status === 'open' && !p.current_employee_id

export function PositionsPage() {
  const { session } = useSession()
  const role = session!.role
  const positions = useTable('position', { limit: '200' })
  const { lookups } = useLookups(['department', 'job_profile', 'employee'])
  const [tab, setTab] = useState<Tab>('open')
  const [editing, setEditing] = useState<Row | 'new' | null>(null)
  const [hiring, setHiring] = useState<Row | null>(null)
  const create = useCreateRow('position')
  const update = useUpdateRow('position')
  const [key, setKey] = useState(() => crypto.randomUUID())
  const rows = useMemo(() => positions.data?.rows ?? [], [positions.data])
  const shown = useMemo(() => rows.filter((p) => tab === 'all' || (tab === 'open' ? isOpenSeat(p) : !isOpenSeat(p))), [rows, tab])
  const counts = { open: rows.filter(isOpenSeat).length, filled: rows.filter((p) => !isOpenSeat(p)).length, all: rows.length }
  const canEdit = canWriteTable('position', role)
  const canHire = canWriteTable('job_requisition', role)
  const titleOf = (p: Row) => { const jp = lookups.job_profile?.[String(p.job_profile_id)]; const d = lookups.department?.[String(p.department_id)]; return `${jp ? String(jp.title) : 'Position'}${d ? `, ${String(d.name)}` : ''}` }

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="spread"><h1>Positions</h1>{canEdit && <Button variant="primary" onClick={() => { setKey(crypto.randomUUID()); setEditing('new') }}>New position</Button>}</div>
      <div className="tabs" role="group" aria-label="Filter positions">
        {([['open', `Open seats (${counts.open})`], ['filled', `Filled (${counts.filled})`], ['all', `All (${counts.all})`]] as [Tab, string][]).map(([id, label]) => (
          <button key={id} type="button" className="tab" aria-pressed={tab === id} onClick={() => setTab(id)}>{label}</button>))}
      </div>
      <section className="panel" aria-label="Position list" aria-live="polite">
        {positions.isPending && <p>Loading positions…</p>}
        {positions.isError && <p role="alert" className="notice notice-danger">{explain(positions.error)}</p>}
        {positions.data && (
          <ModelTable table="position" caption="Positions" role={role} rows={shown} lookups={lookups}
            columns={['job_profile_id', 'department_id', 'budgeted_cost', 'budgeted_fte', 'opened_at', 'current_employee_id']}
            labels={{ job_profile_id: 'Job', department_id: 'Department', budgeted_cost: 'Budget a year', budgeted_fte: 'FTE', current_employee_id: 'Held by' }}
            cells={{ current_employee_id: (p) => (p.current_employee_id ? (lookups.employee?.[String(p.current_employee_id)] ? labelFor('employee', lookups.employee[String(p.current_employee_id)]!) : <Badge tone="ok">Filled</Badge>) : <Badge tone="accent">Open seat</Badge>) }}
            empty={tab === 'open' ? 'No open seats.' : 'No positions here.'}
            actions={(p) => (
              <div className="row">
                {canHire && isOpenSeat(p) && <Button variant="primary" onClick={() => setHiring(p)} aria-label={`Start hiring for ${titleOf(p)}`}>Start hiring</Button>}
                {canEdit && <Button variant="quiet" onClick={() => { setKey(crypto.randomUUID()); setEditing(p) }} aria-label={`Edit ${titleOf(p)}`}>Edit</Button>}
              </div>
            )} />
        )}
      </section>

      <Dialog open={editing !== null} title={editing === 'new' ? 'New position' : 'Edit position'} onClose={() => setEditing(null)}>
        {editing !== null && (
          <ModelForm table="position" role={role} lookups={lookups} submitLabel={editing === 'new' ? 'Create position' : 'Save changes'}
            fields={editing === 'new' ? ['department_id', 'job_profile_id', 'budgeted_fte', 'budgeted_cost', 'opened_at'] : ['department_id', 'job_profile_id', 'budgeted_fte', 'budgeted_cost']}
            fixed={editing === 'new' ? { status: 'open' } : {}} initial={editing === 'new' ? {} : editing}
            labels={{ budgeted_cost: 'Budget a year (₹)', budgeted_fte: 'Full-time equivalent' }}
            busy={create.isPending || update.isPending} error={create.isError ? explain(create.error) : update.isError ? explain(update.error) : null}
            onCancel={() => setEditing(null)}
            onSubmit={(values) => editing === 'new'
              ? create.mutate({ values, key }, { onSuccess: () => setEditing(null) })
              : update.mutate({ id: String(editing.id), values }, { onSuccess: () => setEditing(null) })} />
        )}
      </Dialog>
      {hiring && <StartHireDialog position={hiring} title={titleOf(hiring)} onClose={() => setHiring(null)} />}
    </div>
  )
}
