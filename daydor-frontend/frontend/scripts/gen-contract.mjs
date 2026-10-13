// Generates src/contract/generated/* from the backend's model.
//
//   npm run contract          builds from the committed copies in contract-src/
//   npm run contract:sync     first refreshes those copies from the backend and API repos
//                             (default: ../../daydor-backend; override with DAYDOR_BACKEND_ROOT), then builds
//
// Nothing here is typed by hand: tables, columns, classes, per-role access levels, jurisdiction
// tags, gates and flows all come from model/daydor_model.json (+ extensions.json).
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const src = join(root, 'contract-src')
const out = join(root, 'src', 'contract', 'generated')
mkdirSync(out, { recursive: true })

if (process.argv.includes('--sync')) {
  // Default layout: <common>/daydor-backend and <common>/daydor-frontend/frontend (this folder).
  const be = process.env.DAYDOR_BACKEND_ROOT ?? resolve(root, '..', '..', 'daydor-backend')
  const api = process.env.DAYDOR_API_ROOT ?? resolve(root, '..', 'api')
  copyFileSync(join(be, 'model', 'daydor_model.json'), join(src, 'daydor_model.json'))
  copyFileSync(join(be, 'model', 'extensions.json'), join(src, 'extensions.json'))
  copyFileSync(join(api, 'src', 'daydor_api', 'enums', 'provisional.json'), join(src, 'enums.provisional.json'))
  console.log('synced contract-src from', be)
}

const model = JSON.parse(readFileSync(join(src, 'daydor_model.json'), 'utf8'))
const ext = JSON.parse(readFileSync(join(src, 'extensions.json'), 'utf8'))
const LETTERS = model.roles.map((r) => r.id) // order of the access string
const ROLE_DB = Object.fromEntries(model.roles.map((r) => [r.id, r.db]))

// Same rule the backend loader uses: an extension column takes the access of an existing column
// of the same class, else the table-level grant.
for (const e of ext.columns ?? []) {
  const t = model.tables.find((x) => x.id === e.table)
  const same = t.columns.find((c) => c.cls === e.cls)
  const access = { ...(same ? same.access : t.table_acl) }
  const col = { ...e, access, pk: false, unique: false, encrypted: false, masked: false, derived: false, jurisdiction: null }
  const at = t.columns.findIndex((c) => c.name === 'created_at')
  t.columns.splice(at < 0 ? t.columns.length : at, 0, col)
}

// Same rule as the backend loader's grant caps (finding 2): lower a role's access on a table's
// columns to at most `cap`, except the listed ones (or only the `columns` listed). The database enforces it; this keeps the UI honest.
for (const e of ext.grant_caps ?? []) {
  for (const c of model.tables.find((x) => x.id === e.table).columns) {
    const inScope = e.columns ? e.columns.includes(c.name) : !(e.except ?? []).includes(c.name)
    if (inScope && (c.access[e.role] ?? 0) > e.cap) c.access[e.role] = e.cap
  }
}

const accessString = (a) => LETTERS.map((l) => String(a[l] ?? 0)).join('')

const tables = {}
for (const t of model.tables) {
  tables[t.id] = {
    domain: t.domain,
    jurisdiction: t.jurisdiction,
    description: t.description,
    global: t.global,
    appendOnly: t.append_only,
    acl: accessString(t.table_acl),
    columns: t.columns.map((c) => ({
      n: c.name, t: c.type, c: c.cls, a: accessString(c.access),
      ...(c.fk ? { fk: c.fk } : {}), ...(c.nullable ? { null: true } : {}),
      ...(c.encrypted ? { enc: true } : {}), ...(c.masked ? { masked: true } : {}),
      ...(c.jurisdiction ? { jur: c.jurisdiction } : {}),
    })),
  }
}

// The platform gate the backend defines outside the model (daydor.gates.registry.PLATFORM_HARD_GATES).
const gates = [
  ...model.gates.map((g) => ({ id: g.id, label: g.label, tables: g.tables, approvers: g.ap.map((a) => ROLE_DB[a]), source: g.src, kind: 'hard' })),
  { id: 'g_requisition_budget', label: 'Requisition budget sign-off', tables: ['job_requisition'], approvers: ['tenant_founder'], source: 'platform', kind: 'hard' },
  { id: 'sg_payroll_anomaly_precheck', label: 'Pre-check: does this payroll run look normal against history?', tables: ['payroll_run'], approvers: [], source: 'platform', kind: 'soft', escalatesTo: 'g_pay_anomaly' },
  { id: 'sg_access_request_precheck', label: "Pre-check: is this access request consistent with the person's role?", tables: ['app_access_grant'], approvers: [], source: 'platform', kind: 'soft', escalatesTo: 'g_it_offtemplate' },
]

const generated = {
  meta: { ...model.meta, generatedFrom: 'contract-src/daydor_model.json' },
  accessOrder: LETTERS,
  roles: model.roles.map((r) => ({ letter: r.id, db: r.db, name: r.name, tier: r.tier })),
  levels: ['none', 'aggregate', 'masked', 'read', 'write'],
  classes: Object.fromEntries(Object.entries(model.classes).map(([k, v]) => [k, v.label])),
  domains: Object.fromEntries(Object.entries(model.domains).map(([k, v]) => [k, v.label])),
  gates,
  flows: model.flows.map((f) => ({ id: f.id, name: f.name, summary: f.sum, steps: f.steps.length })),
  tables,
}
writeFileSync(join(out, 'model.json'), JSON.stringify(generated))
copyFileSync(join(src, 'enums.provisional.json'), join(out, 'enums.json'))

const names = Object.keys(tables)
const gateIds = gates.map((g) => g.id)
writeFileSync(join(out, 'types.ts'), `// GENERATED by scripts/gen-contract.mjs. Do not edit.
export type TableName = ${names.map((n) => `'${n}'`).join(' | ')}
export type RoleLetter = ${LETTERS.map((l) => `'${l}'`).join(' | ')}
export type DbRole = ${model.roles.map((r) => `'${r.db}'`).join(' | ')}
export type GateId = ${gateIds.map((g) => `'${g}'`).join(' | ')}
export const TABLE_NAMES: readonly TableName[] = ${JSON.stringify(names)} as const
`)
console.log(`contract: ${names.length} tables, ${model.roles.length} roles, ${gates.length} gates`)
