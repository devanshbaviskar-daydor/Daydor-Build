# Pushing the repo's model deviations back into the artifact

Written Oct 13 2026 (Sprint 13). Nothing here has been applied: this is the plan, and it needs a decision (below)
before anyone edits `model/source_artifact.html`.

The data model's source of truth is the "Daydor: Data Model and Access Map" artifact, exported by
`scripts/export_model.js` into `model/daydor_model.json`. The backend has deviated from it in places the findings call
"push back into the artifact". Each deviation lives in the repo as one of three kinds of mechanism, and the kind decides
how risky the push-back is.

## A. Additive and generated: low risk
The repo already applies these on top of the exported model and the generated SQL already contains them. Moving them
into the artifact should change **no generated file**, which the drift tests (`tests/test_model_drift.py`) verify.

| Finding | Deviation | Mechanism today | Artifact change |
|---|---|---|---|
| 1 | `approval_request.requested_by_user_id`, `requested_by_agent_run_id`, `decision_note` | `columns` in `model/extensions.json` | add the three columns to the table; delete the `columns` entries |
| 2, 23 | the employee role is capped on `employee`, `timecard`, `expense`, `leave_request`, `benefit_election`, `checklist`, `life_event`, `training_assignment` | `grant_caps` in `model/extensions.json`, generated into `0024` | lower the employee column access in the artifact's access rules; delete the `grant_caps` entries. `0003` stays the uncapped baseline, so the loader's `apply_caps=False` path goes away only if `0003` is also regenerated (see C) |
| 9, 11 | gates `g_requisition_budget`, `g_timecard`, `g_expense` | `PLATFORM_HARD_GATES` in `daydor.gates.registry` | add them to the artifact's gate list with `source: platform`; drop the constant. `0007` regenerates identically |

## B. Hand-written structure: needs a model concept first
These are real schema deviations applied by hand-written migrations, so the artifact has no way to say them today.

| Finding | Deviation | Mechanism | What the artifact needs |
|---|---|---|---|
| 19 | `derived` columns need a defined way to be set | SECURITY DEFINER functions in `0021` | a `derived` column should also say how it is computed: an aggregate over a named table, or an opaque input |
| 20 | `final_settlement.approval_request_id` nullable; the g_pay_disburse / g_finalpay guard columns; `cobra_event.notice_sent_at` guard | `0022` | nullable flag on the column; the guard-column assignment per gate |
| 7, 28 | aggregate-only access (level 1) and who may call the report | `0038` function, `AGGREGATE_ONLY` | a "report" object that names the table, its minimum cell size and its callers |
| (Sprint 12) | `expense.reimbursed_at` and `leave_request.fmla_designation` guards | `0031` | the guard-column assignment per gate, as above |

## C. Changes the pinned baseline migrations: the real decision
These alter what `0002` or `0003` would generate, and those are applied, drift-tested migrations.

| Finding | Deviation | Why it is hard |
|---|---|---|
| 10 | `employee`'s four encrypted columns are nullable | `0012` relaxes them by hand; regenerating `0002` with them nullable changes an applied migration (the repo does this in place for `0007` and `0025`/`0028`, with an incremental for already-migrated databases, so there is a precedent, but not for table DDL) |
| 18 | `statutory_rate_rule.employee_rate` and `employer_rate` are `numeric(8,6)`, not `numeric(14,2)` | `0020` widens them by hand; the generator maps every numeric to `numeric(14,2)`, so the artifact needs a rate or percentage physical type before the DDL can say it |
| 19, 20 | derived and nullable columns above | same: `0002`/`0003` encode the old shape |

## Decisions needed
1. **Where does the artifact live?** The export header says `claude.ai/artifact/HYiKD99BWaHX8gbmKuQGvt`, not this repo.
   `model/source_artifact.html` is a local copy. Editing the copy changes what `export_model.js` produces here but does not change
   the artifact the design team sees. Should the push-back be a local edit only, or also an update to the hosted artifact (which
   is outward-facing, so I have not touched it)?
2. **Group A now, C later?** Group A is safe to do together, in one pass, with the drift tests as the check. Group C needs a
   decision on regenerating applied baselines. I recommend A now, B once the artifact has the concepts, and C last, as a
   reviewed change that regenerates `0002`/`0003` and adds incrementals, as was done for `0007`.
3. **Who owns the artifact edit?** It is a 100 KB hand-maintained page whose data arrays (`T`, `GATES`, `FLOWS`) are read by
   `export_model.js`; a careless edit silently changes the export. I would do group A as a scripted, reviewable diff.

## How to check a push-back
Edit the artifact, run `node scripts/export_model.js model/source_artifact.html model/daydor_model.json`, delete the now-redundant
`extensions.json` entries, run `python -m daydor.model.ddl migrations/sql` and `pytest`. `tests/test_model_drift.py` must stay green
with no generated file changed; if one changes, the deviation was not purely additive and belongs in group C.
