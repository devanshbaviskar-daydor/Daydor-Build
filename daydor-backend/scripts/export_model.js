// Exports the data model from the "Daydor — Data Model & Access Map" artifact
// to model/daydor_model.json. Uses the artifact's own access engine (tblLevel,
// capOf, colLevel) so computed access levels match the artifact exactly.
// Usage: node scripts/export_model.js model/source_artifact.html model/daydor_model.json
const fs = require('fs');
const [,, src, out] = process.argv;
const html = fs.readFileSync(src, 'utf8');
const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const code = scripts.sort((a, b) => b.length - a.length)[0];
const cut = code.indexOf('/* =========================================================\n   DDL generator');
const engine = code.slice(0, cut);
const fn = new Function(engine + `
  const ROLE_IDS = RID;
  const tables = T.map(tb => ({
    id: tb.id, domain: tb.d, source: tb.src, jurisdiction: tb.j || null, description: tb.desc,
    global: !!tb.global, null_tenant: !!tb.nullTenant, append_only: !!tb.appendOnly,
    table_acl: Object.fromEntries(ROLE_IDS.map(r => [r, tblLevel(tb, r)])),
    columns: tb.cols.map(c => ({
      name: c.n, type: c.ty, cls: c.cl, fk: c.fk || null, nullable: !!c.null, pk: !!c.pk,
      unique: !!c.uniq, encrypted: !!c.enc, masked: !!c.mask, derived: !!c.der,
      jurisdiction: c.j || null,
      access: Object.fromEntries(ROLE_IDS.map(r => [r, colLevel(tb, c, r)]))
    })),
    writers: (WK[tb.id] || [[], []])[0], readers: (WK[tb.id] || [[], []])[1]
  }));
  return { domains: DOM, domain_order: DOM_ORDER, classes: CLASSES, levels: LV, roles: ROLES,
           class_caps: CAPS, tables, gates: GATES, flows: FLOWS };
`);
const model = fn();
model.meta = { exported_at: new Date().toISOString(), table_count: model.tables.length,
               source: 'claude.ai/artifact/HYiKD99BWaHX8gbmKuQGvt' };
fs.writeFileSync(out, JSON.stringify(model, null, 2));
console.log(`exported ${model.tables.length} tables, ${model.gates.length} gates, ${model.flows.length} flows`);
