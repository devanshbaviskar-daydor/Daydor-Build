import { useState, type FormEvent } from 'react'
import { column as columnDef, enumValues, humanize, labelFor, writableColumns, type Row, type TableName } from '../contract'
import { Button } from './Button'
import type { Lookups } from './ModelTable'

interface Props {
  table: TableName; role: string
  /** The columns to ask for, in order. Columns the role may not write are left out. */
  fields: string[]
  initial?: Row
  /** Values sent with every save but never shown, such as the employee the record belongs to. */
  fixed?: Row
  lookups?: Lookups
  labels?: Record<string, string>
  help?: Record<string, string>
  submitLabel: string
  busy?: boolean
  error?: string | null
  onSubmit: (values: Row) => void
  onCancel?: () => void
}

const toLocalInput = (iso: unknown) => (iso ? String(iso).slice(0, 16) : '')

/** A form generated from the contract. Each field's widget follows the column's type: a reference
 *  becomes a picker, a listed enum a select, an unlisted enum free text. Required means "not nullable". */
export function ModelForm({ table, role, fields, initial = {}, fixed = {}, lookups = {}, labels = {}, help = {}, submitLabel, busy, error, onSubmit, onCancel }: Props) {
  const allowed = new Set(writableColumns(table, role).map((c) => c.n))
  const shown = fields.filter((f) => allowed.has(f))
  const [values, setValues] = useState<Row>(() => Object.fromEntries(shown.map((f) => [f, f in initial ? (columnDef(table, f)?.t === 'ts' ? toLocalInput(initial[f]) : initial[f]) : ''])))
  const [problems, setProblems] = useState<Record<string, string>>({})
  const set = (k: string, v: unknown) => setValues((x) => ({ ...x, [k]: v }))

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const out: Row = { ...fixed }
    const errs: Record<string, string> = {}
    for (const f of shown) {
      const def = columnDef(table, f)!
      const raw = values[f]
      if (raw === '' || raw === undefined || raw === null) {
        if (!def.null && !(f in initial)) errs[f] = 'Required'
        continue
      }
      if (def.t === 'numeric' || def.t === 'int') { const n = Number(raw); if (Number.isNaN(n)) { errs[f] = 'Enter a number'; continue } out[f] = n }
      else if (def.t === 'ts') out[f] = new Date(String(raw)).toISOString()
      else if (def.t === 'jsonb') { try { out[f] = typeof raw === 'string' ? JSON.parse(raw) : raw } catch { errs[f] = 'Enter valid JSON' } }
      else out[f] = raw
    }
    setProblems(errs)
    if (Object.keys(errs).length === 0) onSubmit(out)
  }

  return (
    <form onSubmit={submit} className="stack" noValidate>
      {shown.map((f) => {
        const def = columnDef(table, f)!
        const id = `f-${table}-${f}`
        const label = labels[f] ?? humanize(f.replace(/_id$/, ''))
        const required = !def.null && !(f in initial)
        const common = { id, 'aria-invalid': problems[f] ? true : undefined, 'aria-describedby': problems[f] || help[f] ? `${id}-help` : undefined } as const
        let widget
        if (def.fk) {
          const rows = Object.values(lookups[def.fk] ?? {})
          widget = (
            <select {...common} className="input" value={String(values[f] ?? '')} onChange={(e) => set(f, e.target.value)}>
              <option value="">{rows.length ? 'Choose…' : 'Nothing to choose from'}</option>
              {rows.map((r) => <option key={String(r.id)} value={String(r.id)}>{labelFor(def.fk!, r)}</option>)}
            </select>
          )
        } else if (def.t === 'bool') {
          widget = <input {...common} type="checkbox" checked={!!values[f]} onChange={(e) => set(f, e.target.checked)} style={{ width: 22, height: 22 }} />
        } else if (def.t === 'enum' && enumValues(table, f)) {
          widget = (
            <select {...common} className="input" value={String(values[f] ?? '')} onChange={(e) => set(f, e.target.value)}>
              <option value="">Choose…</option>
              {enumValues(table, f)!.map((v) => <option key={v} value={v}>{humanize(v)}</option>)}
            </select>
          )
        } else if (def.t === 'jsonb') {
          widget = <textarea {...common} className="input" rows={4} value={typeof values[f] === 'string' ? String(values[f]) : JSON.stringify(values[f] ?? '', null, 1)} onChange={(e) => set(f, e.target.value)} />
        } else {
          const type = def.t === 'date' ? 'date' : def.t === 'ts' ? 'datetime-local' : def.t === 'numeric' || def.t === 'int' ? 'number' : def.t === 'citext' ? 'email' : 'text'
          widget = <input {...common} className="input" type={type} step={def.t === 'numeric' ? 'any' : undefined} value={String(values[f] ?? '')} onChange={(e) => set(f, e.target.value)} />
        }
        const note = def.t === 'enum' && !enumValues(table, f) ? 'The model does not list the allowed values yet, so this is free text.' : help[f]
        return (
          <div key={f}>
            <label className="label" htmlFor={id}>{label}{required && <span aria-hidden="true"> *</span>}</label>
            {widget}
            {(problems[f] || note) && <p id={`${id}-help`} className="help" style={problems[f] ? { color: 'var(--danger)' } : undefined}>{problems[f] ?? note}</p>}
          </div>
        )
      })}
      {shown.length === 0 && <p className="muted">Your role cannot change any of these fields.</p>}
      {error && <p role="alert" className="notice notice-danger">{error}</p>}
      <div className="row">
        <Button type="submit" variant="primary" busy={busy} disabled={shown.length === 0}>{submitLabel}</Button>
        {onCancel && <Button onClick={onCancel}>Cancel</Button>}
      </div>
    </form>
  )
}
