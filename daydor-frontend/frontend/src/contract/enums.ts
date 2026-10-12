// Provisional enum values, scanned from the backend's code (see api/scripts/gen_enums.py). The model
// lists none of its 88 enum columns' values, so most columns are unlisted here: for those, labels fall
// back to the raw value and forms use free text. Delete this file when the model carries value lists.
import raw from './generated/enums.json'
import { humanize } from './access'

const enums = raw as unknown as { enums: Record<string, { values: string[] }>; unlisted: string[]; enum_column_count: number }

export const enumColumnCount = enums.enum_column_count
export function enumValues(table: string, column: string): string[] | null {
  return enums.enums[`${table}.${column}`]?.values ?? null
}
export function isEnumListed(table: string, column: string): boolean {
  return enumValues(table, column) !== null
}
/** A readable label; an unknown value is shown as-is, never hidden or crashing. */
export function enumLabel(_table: string, _column: string, value: string): string {
  return humanize(value)
}
export const listedEnumCount = Object.keys(enums.enums).length
