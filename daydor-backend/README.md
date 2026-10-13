# Daydor backend

Backend for Daydor, an HR platform for SMEs (50 to 100 employees) that runs HR work through
domain agents. This repo holds the data model, database access control, the Postgres-based
job queue and state machines, and the gate service (hard human gates plus soft gates).

## Layout

| Path | What it is |
|---|---|
| `model/daydor_model.json` | Source of truth for the 82-table model, exported from the Data Model & Access Map artifact |
| `model/source_artifact.html` | The artifact the model was exported from |
| `scripts/export_model.js` | Re-exports the model from the artifact (uses the artifact's own access engine) |
| `src/daydor/model/` | Model loader and the DDL generator (tables, RLS, grants, views) |
| `src/daydor/db/` | Engine and per-transaction session context (tenant, role, actor, purpose) |
| `src/daydor/queue/` | Postgres job queue, outbox and timers |
| `src/daydor/workflow/` | State-machine runner with transitions stored as data |
| `src/daydor/gates/` | Gate registry, hard-gate service and the soft-gate hook (Jev stub today, Laya per ADR-005) |
| `migrations/` | Alembic migrations |
| `tests/` | Tests run against a real Postgres |
| `docs/` | Backend plan, model findings and architecture decision records |
| `CLAUDE.md` | Conventions for Claude Code |

## Running locally

```bash
pip install -e ".[dev]"
export DAYDOR_DATABASE_URL=postgresql+psycopg://daydor_owner:dev@localhost/daydor_dev
alembic upgrade head
DAYDOR_TEST_DATABASE_URL=postgresql+psycopg://daydor_owner:dev@localhost/daydor_test pytest
```

## Changing the data model

1. Edit the model in the artifact, then re-export: `node scripts/export_model.js model/source_artifact.html model/daydor_model.json`.
2. Add a migration. The model drift test fails until the live schema matches the model.
