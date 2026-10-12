import { humanize } from './index'

export type Row = Record<string, unknown>
const str = (v: unknown) => (v === null || v === undefined ? '' : String(v))

const inr = (n: unknown, currency = 'INR') => new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: 0 }).format(Number(n))

/** A short human label for a row of a table, used wherever a reference to it is shown or picked. */
export function labelFor(table: string, row: Row): string {
  switch (table) {
    case 'department': case 'location': case 'skill': return str(row.name)
    case 'job_profile': return `${str(row.title)}${row.level ? ` (${str(row.level)})` : ''}`
    case 'employee': return str(row.full_name)
    case 'comp_band': return `${inr(row.band_min, str(row.currency) || 'INR')} to ${inr(row.band_max, str(row.currency) || 'INR')}`
    case 'candidate': return str(row.full_name)
    case 'legal_entity': return str(row.name)
    default: return `${humanize(table)} ${str(row.id).slice(0, 6)}`
  }
}

export const money = inr
export const isMoneyColumn = (col: string) => /(_cost$|_base$|_equity$|^band_|^pay_range_|^ctc_|^basic_|^gross|^net_pay$|^tax_withheld$|^amount$|_allowances)/.test(col)
