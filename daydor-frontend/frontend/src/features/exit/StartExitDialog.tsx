import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLookups, useStartExit } from '../../api/hooks'
import { explain } from '../../api/errors'
import { labelFor } from '../../contract'
import { Button, Dialog } from '../../ui'

/** termination_type/reason_code are unlisted enums (the model carries no value list for them),
 *  same shape as StartHireDialog's channel/employment_type -- free text, with the backend's own
 *  test values as a hint. */
export function StartExitDialog({ onClose }: { onClose: () => void }) {
  const nav = useNavigate()
  const { lookups } = useLookups(['employee'])
  const start = useStartExit()
  const people = Object.values(lookups.employee ?? {}).filter((e) => e.is_active !== false)
  const [v, setV] = useState({ employee: '', type: 'voluntary', reason: 'resignation', notice: '', lastDay: '' })
  const [errs, setErrs] = useState<Record<string, string>>({})
  const [key] = useState(() => crypto.randomUUID())
  const set = (k: keyof typeof v, val: string) => setV((x) => ({ ...x, [k]: val }))

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const bad: Record<string, string> = {}
    if (!v.employee) bad.employee = 'Choose who is leaving'
    if (!v.type) bad.type = 'Enter a termination type'
    if (!v.reason) bad.reason = 'Enter a reason code'
    if (!v.notice) bad.notice = 'Choose the notice date'
    if (!v.lastDay) bad.lastDay = 'Choose the last working day'
    setErrs(bad)
    if (Object.keys(bad).length) return
    start.mutate(
      { body: { employee_id: v.employee, termination_type: v.type, reason_code: v.reason, notice_date: v.notice, last_working_day: v.lastDay }, key },
      { onSuccess: (r) => nav(`/exit/${r.termination_id}`) },
    )
  }
  const field = (id: string, label: string, widget: React.ReactNode, help?: string) => (
    <div><label className="label" htmlFor={id}>{label}</label>{widget}{(errs[id] || help) && <p className="help" style={errs[id] ? { color: 'var(--danger)' } : undefined}>{errs[id] ?? help}</p>}</div>
  )
  return (
    <Dialog open title="Start a termination" onClose={onClose} width={520}>
      <form onSubmit={submit} noValidate className="stack">
        {field('employee', 'Who is leaving', (
          <select id="employee" className="input" value={v.employee} onChange={(e) => set('employee', e.target.value)}>
            <option value="">Choose…</option>{people.map((p) => <option key={String(p.id)} value={String(p.id)}>{labelFor('employee', p)}</option>)}
          </select>
        ))}
        <div className="row">
          <div style={{ flex: 1 }}>{field('type', 'Termination type', <input id="type" className="input" value={v.type} onChange={(e) => set('type', e.target.value)} />, 'Free text: the model does not list the values yet. e.g. voluntary, involuntary')}</div>
          <div style={{ flex: 1 }}>{field('reason', 'Reason code', <input id="reason" className="input" value={v.reason} onChange={(e) => set('reason', e.target.value)} />, 'e.g. resignation, performance')}</div>
        </div>
        <div className="row">
          <div style={{ flex: 1 }}>{field('notice', 'Notice date', <input id="notice" className="input" type="date" value={v.notice} onChange={(e) => set('notice', e.target.value)} />)}</div>
          <div style={{ flex: 1 }}>{field('lastDay', 'Last working day', <input id="lastDay" className="input" type="date" value={v.lastDay} onChange={(e) => set('lastDay', e.target.value)} />)}</div>
        </div>
        {start.isError && <p role="alert" className="notice notice-danger">{explain(start.error)}</p>}
        <div className="row"><Button type="submit" variant="primary" busy={start.isPending}>Start termination</Button><Button onClick={onClose}>Cancel</Button></div>
      </form>
    </Dialog>
  )
}
