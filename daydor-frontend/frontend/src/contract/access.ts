// Typed access to the generated contract. Every rule here comes from the backend's model: which
// tables a role can touch, which columns it can see, whether a value is masked, which fields are
// tied to a jurisdiction. Nothing is hand-listed.
import raw from './generated/model.json'
import type { DbRole, GateId, RoleLetter, TableName } from './generated/types'

export type Level = 0 | 1 | 2 | 3 | 4
export type AccessKind = 'hidden' | 'aggregate' | 'masked' | 'read' | 'write'
const KINDS: AccessKind[] = ['hidden', 'aggregate', 'masked', 'read', 'write']

export interface ColumnDef { n: string; t: string; c: string; a: string; fk?: string; null?: boolean; enc?: boolean; masked?: boolean; jur?: string }
export interface TableDef { domain: string; jurisdiction: string | null; description: string; global: boolean; appendOnly: boolean; acl: string; columns: ColumnDef[] }
export interface Gate { id: GateId; label: string; tables: string[]; approvers: DbRole[]; source: string; kind: 'hard' | 'soft'; escalatesTo?: string }
export interface Role { letter: RoleLetter; db: DbRole; name: string; tier: string }
export interface FieldState { kind: AccessKind; level: Level; cls: string; encrypted: boolean; masked: boolean; jurisdiction: string | null }

const model = raw as unknown as {
  accessOrder: RoleLetter[]; roles: Role[]; classes: Record<string, string>; gates: Gate[]
  tables: Record<TableName, TableDef>; flows: { id: string; name: string; summary: string; steps: number }[]
}

export const roles: readonly Role[] = model.roles
export const gates: readonly Gate[] = model.gates
export const flows = model.flows
export const classLabels = model.classes
export const tableNames = Object.keys(model.tables) as TableName[]

/** The people-facing roles. Agents never sign in. */
export const HUMAN_ROLES: readonly DbRole[] = roles.filter((r) => r.letter !== 'G').map((r) => r.db)

export function roleInfo(role: string): Role | undefined {
  return roles.find((r) => r.db === role)
}
export const roleName = (role: string) => roleInfo(role)?.name ?? role

const idx = (role: string) => {
  const letter = roleInfo(role)?.letter
  return letter ? model.accessOrder.indexOf(letter) : -1
}
const at = (s: string, role: string): Level => {
  const i = idx(role)
  return (i < 0 ? 0 : Number(s[i] ?? 0)) as Level
}

export function table(name: TableName): TableDef {
  return model.tables[name]
}
export function tableLevel(name: TableName, role: string): Level {
  return at(table(name).acl, role)
}
export function column(name: TableName, col: string): ColumnDef | undefined {
  return table(name).columns.find((c) => c.n === col)
}
export function fieldState(name: TableName, col: string, role: string): FieldState {
  const def = column(name, col)
  if (!def) return { kind: 'hidden', level: 0, cls: '?', encrypted: false, masked: false, jurisdiction: null }
  const level = at(def.a, role)
  return {
    kind: KINDS[level] ?? 'hidden', level, cls: def.c, encrypted: !!def.enc,
    masked: !!def.masked || level === 2, jurisdiction: def.jur ?? null,
  }
}
/** Columns the role may see (masked or better). Encrypted columns are never listed. */
export function visibleColumns(name: TableName, role: string): ColumnDef[] {
  return table(name).columns.filter((c) => at(c.a, role) >= 2 && !c.enc)
}
export function writableColumns(name: TableName, role: string): ColumnDef[] {
  const never = new Set(['id', 'tenant_id', 'created_at', 'updated_at'])
  return table(name).columns.filter((c) => at(c.a, role) >= 4 && !c.enc && !never.has(c.n))
}
export const canWriteTable = (name: TableName, role: string) => tableLevel(name, role) >= 4
export const canReadTable = (name: TableName, role: string) => tableLevel(name, role) >= 2

/** Columns that only apply in one country, from the model's jurisdiction tags. */
export function jurisdictionColumns(name: TableName, jurisdiction: 'IN' | 'US'): ColumnDef[] {
  return table(name).columns.filter((c) => c.jur === jurisdiction)
}

export function gate(id: string): Gate | undefined {
  return gates.find((g) => g.id === id)
}
export const gateLabel = (id: string) => gate(id)?.label ?? humanize(id)

export function humanize(name: string): string {
  const s = name.replace(/^s\d+_/, '').replace(/^g_/, '').replace(/_/g, ' ').trim()
  return s.charAt(0).toUpperCase() + s.slice(1)
}
