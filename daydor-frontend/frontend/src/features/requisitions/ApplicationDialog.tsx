import { useState, type FormEvent } from 'react'
import { useEnterApplication } from '../../api/hooks'
import { explain } from '../../api/errors'
import { Button, Dialog } from '../../ui'

/** HR enters the application for now: the backend's trigger is a candidate applying, and there is no apply page yet. */
export function ApplicationDialog({ requisitionId, onClose, onDone }: { requisitionId: string; onClose: () => void; onDone: () => void }) {
  const enter = useEnterApplication(requisitionId)
  const [v, setV] = useState({ full_name: '', email: '', phone: '', source: 'hr_entry' })
  const [errs, setErrs] = useState<Record<string, string>>({})
  const [key] = useState(() => crypto.randomUUID())
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const bad: Record<string, string> = {}
    if (!v.full_name.trim()) bad.full_name = 'Enter the candidate’s name'
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v.email)) bad.email = 'Enter a valid email address'
    if (v.phone.trim().length < 3) bad.phone = 'Enter a phone number'
    setErrs(bad)
    if (Object.keys(bad).length) return
    enter.mutate({ body: { ...v, full_name: v.full_name.trim() }, key }, { onSuccess: () => { onDone(); onClose() } })
  }
  const f = (id: keyof typeof v, label: string, type = 'text', help?: string) => (
    <div><label className="label" htmlFor={`a-${id}`}>{label}</label>
      <input id={`a-${id}`} className="input" type={type} value={v[id]} aria-invalid={errs[id] ? true : undefined} onChange={(e) => setV((x) => ({ ...x, [id]: e.target.value }))} />
      {(errs[id] || help) && <p className="help" style={errs[id] ? { color: 'var(--danger)' } : undefined}>{errs[id] ?? help}</p>}</div>
  )
  return (
    <Dialog open title="Enter an application" onClose={onClose}>
      <form onSubmit={submit} noValidate className="stack">
        <p className="muted" style={{ fontSize: 14 }}>There is no application page for candidates yet, so HR enters it here. Screening runs in the background and the result appears on this page.</p>
        {f('full_name', 'Full name')}{f('email', 'Email', 'email')}{f('phone', 'Phone')}{f('source', 'Where they came from', 'text', 'Free text for now: the model does not list the sources yet.')}
        {enter.isError && <p role="alert" className="notice notice-danger">{explain(enter.error)}</p>}
        <div className="row"><Button type="submit" variant="primary" busy={enter.isPending}>Enter application</Button><Button onClick={onClose}>Cancel</Button></div>
      </form>
    </Dialog>
  )
}
