import type { ReactNode } from 'react'
import { column as columnDef, humanize, isMoneyColumn, labelFor, type Row, type TableName } from '../contract'
import { FieldValue } from './Field'

export type Lookups = Partial<Record<string, Record<string, Row>>>

/** A table whose cells follow the contract: access rules per column, references shown by label,
 *  money in rupees. `cells` overrides a column with custom content. */
export function ModelTable({ table, rows, columns, role, lookups = {}, cells = {}, labels = {}, empty, rowKey = 'id', caption, actions }: {
  table: TableName; rows: Row[]; columns: string[]; role: string; lookups?: Lookups
  cells?: Record<string, (row: Row) => ReactNode>; labels?: Record<string, string>
  empty?: ReactNode; rowKey?: string; caption: string; actions?: (row: Row) => ReactNode
}) {
  if (rows.length === 0) return <p className="muted">{empty ?? 'Nothing to show yet.'}</p>
  return (
    <div className="table-wrap">
      <table className="data">
        <caption className="sr-only">{caption}</caption>
        <thead><tr>{columns.map((c) => <th key={c} scope="col">{labels[c] ?? humanize(c.replace(/_id$/, ''))}</th>)}{actions && <th scope="col"><span className="sr-only">Actions</span></th>}</tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={String(r[rowKey])}>
              {columns.map((c) => {
                if (cells[c]) return <td key={c}>{cells[c]!(r)}</td>
                const fk = columnDef(table, c)?.fk
                const target = fk ? lookups[fk]?.[String(r[c] ?? '')] : undefined
                return (
                  <td key={c}>
                    {fk && r[c] ? (target ? labelFor(fk, target) : <span className="muted">Not visible</span>)
                      : <FieldValue table={table} column={c} value={r[c]} role={role} currency={isMoneyColumn(c) ? String(r.currency ?? 'INR') : undefined} />}
                  </td>
                )
              })}
              {actions && <td>{actions(r)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
