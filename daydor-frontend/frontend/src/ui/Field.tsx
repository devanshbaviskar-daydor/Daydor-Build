import { column, fieldState, humanize, type TableName } from '../contract'
import { Badge } from './Badge'
import { ConsentRequired, type ConsentState } from './ConsentRequired'

export const DEFAULT_LOCALE = 'en-IN'

interface Props {
  table: TableName
  column: string
  value: unknown
  /** The signed-in person's database role. */
  role: string
  label?: string
  /** For personal data that needs the employee's consent before it exists. */
  consent?: ConsentState | 'granted'
  currency?: string
  locale?: string
  showClass?: boolean
}

function format(type: string, value: unknown, locale: string, currency?: string): string {
  if (value !== null && typeof value === 'object') return JSON.stringify(value)
  if (typeof value === 'boolean' || type === 'bool') return value ? 'Yes' : 'No'
  if (type === 'enum') return humanize(String(value))
  if (type === 'date') return new Date(String(value)).toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' })
  if (type === 'ts') return new Date(String(value)).toLocaleString(locale, { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' })
  if (type === 'numeric' || type === 'int') {
    const n = Number(value)
    return currency ? new Intl.NumberFormat(locale, { style: 'currency', currency, maximumFractionDigits: 0 }).format(n) : new Intl.NumberFormat(locale).format(n)
  }
  return String(value)
}

/** Just the value, shown the way the backend's access rules say this role may see it. Used by Field and
 *  by tables. A value the role cannot see is never rendered, even if one was passed in. */
export function FieldValue({ table, column, value, role, consent, currency, locale = DEFAULT_LOCALE }: Omit<Props, 'label' | 'showClass'>) {
  const st = fieldState(table, column, role)
  if (st.kind === 'hidden') return <span className="restricted">Your role cannot see this.</span>
  if (st.kind === 'aggregate') return <span className="restricted">Only totals are available to your role.</span>
  if (value === null || value === undefined || value === '') {
    return st.encrypted && consent && consent !== 'granted'
      ? <ConsentRequired state={consent} />
      : <span className="restricted">Not set</span>
  }
  return <>{format(fieldTypeOf(table, column), value, locale, currency)}{st.kind === 'masked' && <> <Badge tone="outline" title="Part of this value is hidden for your role.">Masked</Badge></>}</>
}

/** One labelled value. */
export function Field({ table, column, value, role, label, consent, currency, locale = DEFAULT_LOCALE, showClass }: Props) {
  const st = fieldState(table, column, role)
  return (
    <div className="field" data-access={st.kind}>
      <span className="field-label">{label ?? humanize(column)}{showClass && <span className="field-class" aria-label={`Data class ${st.cls}`}>{st.cls}</span>}</span>
      <span className="field-value"><FieldValue table={table} column={column} value={value} role={role} consent={consent} currency={currency} locale={locale} /></span>
    </div>
  )
}

function fieldTypeOf(table: TableName, col: string): string {
  return column(table, col)?.t ?? 'text'
}
