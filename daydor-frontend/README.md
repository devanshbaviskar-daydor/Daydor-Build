# Daydor frontend

The web app for Daydor's HR platform, in one repo with two parts:

| Folder | What it is |
| --- | --- |
| `frontend/` | React + TypeScript app (Vite). Screens, shared components, a typed contract generated from the backend's model, and a mock backend for building ahead of the API. |
| `api/` | A thin Python (FastAPI) layer that turns an HTTP request into a database session as the signed-in person, then calls the backend's own functions. It never edits the backend. |

The backend (`daydor-backend`) is a separate repo. This repo imports it as a library and reads its model. The expected layout is two folders side by side:

```
common-folder/
  daydor-backend/     the backend
  daydor-frontend/    this repo (frontend/, api/, docs/)
```

After placing them, one command syncs everything from the backend and runs every check (Postgres 16 must be running):

```bash
cd daydor-frontend && bash scripts/sync-from-backend.sh
```

Status: **FE-0 to FE-6 are complete, and the Hire flow runs live end to end.** A hire goes from a new requisition through offer, background check, consent (resolved by the new hire's own sign-in), documents, work authorization or identity documents, onboarding, access and payroll profile -- the backend's real queue workers doing the work, not sample data. A Payroll run (build, anomaly check, disbursal, payslip issuance) can take that employee through to a real first payslip via `/payroll/runs*`, though Payroll, Exit, Time and leave and Reference data each have their own screens too (FE-7 to FE-13). See `docs/fe-0-notes.md`, `docs/fe-1-notes.md`, `docs/fe-2-to-6-notes.md` and `docs/integration-notes.md` (the last is the current source of truth for what's live versus still sample data, and why).

## Run it with sample data (no setup beyond Node)

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, sample data, nothing is saved
```

Sign in as any of the nine demo accounts. `Design primitives` in the sidebar shows every shared component in each state. Demo scripts: `docs/fe-0-demo-script.md`, `docs/fe-1-demo-script.md`, `docs/fe-2-to-6-demo-script.md`.

## Run it against the real backend

You need Postgres 16, Node 20 (`.nvmrc` pins it; a newer Node fails every frontend test on a jsdom/undici incompatibility) and the backend repo. Use a Python virtual environment (`python3 -m venv .venv && source .venv/bin/activate`); `scripts/sync-from-backend.sh` creates one for you. If another Postgres instance is already on 5432, point these at whatever port your PG16 actually listens on.

```bash
# 1. Backend: install and migrate (from the backend repo)
pip install -e ../daydor-backend
export DAYDOR_DATABASE_URL=postgresql+psycopg://daydor_owner:dev@localhost:5432/daydor_dev
(cd ../daydor-backend && alembic upgrade head)

# 2. API layer: install, create its own tables, seed a demo company
cd api
pip install -e ".[dev]"
python -m daydor_api.seed_dev

# 3. Run the API and the queue worker (two terminals)
uvicorn daydor_api.app:get_app --factory --port 8000
python -m daydor_api.worker

# 4. Frontend, with approvals, workflows and hire live
cd ../frontend
VITE_API_MODE=live npm run dev
# or mix: VITE_RESOURCE_MODES=auth:live,approvals:live,workflows:live,hire:live,tables:live,meta:live
```

The queue worker matters: the backend ships handlers but no process that runs them, so nothing moves a workflow forward without it -- `api/src/daydor_api/worker.py` registers every Hire-flow handler (all 18 steps). Payroll isn't workflow-engine-driven, so its steps are `POST /payroll/runs*` actions instead (see `api/README.md`), not something the worker runs on its own.

## Tests

```bash
cd frontend && npm test            # 111 tests (+7 live-only), includes accessibility checks
cd frontend && npm run typecheck && npm run lint
cd api && pytest                   # 59 tests against real Postgres and the backend's migrations
# Live end-to-end check (API and worker running, database seeded) -- drives a hire from start
# through a real first payslip, with the new hire resolving their own consent gate:
cd frontend && DAYDOR_LIVE_API=http://localhost:8000 npx vitest run src/api/live.test.ts
```

## How the pieces fit

- **Contract.** `npm run contract` generates `frontend/src/contract/generated/` from `frontend/contract-src/` (a copy of the backend's `model/daydor_model.json` and `extensions.json`). Tables, columns, sensitivity classes, per-role access levels, jurisdiction tags and gates all come from there. `npm run contract:sync` refreshes the copies (set `DAYDOR_BACKEND_ROOT`).
- **Mock or live, per resource.** `frontend/src/api/transport.ts` routes each resource (`auth`, `meta`, `tables`, `approvals`, `workflows`, `hire`) to the mock backend or the real API. Same client, same errors, same idempotency keys either way. The mock's simulated hire flow currently stops at the offer (it was not extended to match steps 9-18 going live) -- the sample-data preview build therefore does not demo background check through payslip; use the live backend for that (see `docs/integration-notes.md`).
- **The database is the security boundary.** The UI hides what a role cannot do and explains why; it never assumes it is the one enforcing. The API opens each request as the caller's role and never uses an owner or row-security-bypassing role.
- **Provisional enums.** The model lists no enum values. `api/scripts/gen_enums.py` scans the backend for the values it writes, and a test fails if that goes stale.

## Preview build

`npm run build:preview` makes one self-contained `dist/index.html` that runs on sample data only (a hosted page cannot reach a database).
