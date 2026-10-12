# daydor-api

Thin HTTP layer over the Daydor backend. Python 3.11+, FastAPI.

```bash
pip install -e ../../daydor-backend      # the backend sits next to this repo; it is not on PyPI
pip install -e ".[dev]"
python -m daydor_api.migrate               # creates the `api` schema (identity, idempotency)
python -m daydor_api.seed_dev              # demo company and nine sign-ins
uvicorn daydor_api.app:get_app --factory --port 8000
python -m daydor_api.worker                # runs the backend's queue handlers
pytest
```

## Endpoints (all under `/api`)

| Endpoint | Purpose |
| --- | --- |
| `POST /auth/dev-login`, `GET /auth/dev-users`, `GET /auth/me` | Development sign-in (disabled unless `DAYDOR_API_ENV=dev`) |
| `GET /meta/enums`, `/meta/gates`, `/meta/workflows/{name}` | Provisional enums, gate catalog, active workflow definition |
| `GET /tables/{table}`, `POST /tables/{table}`, `PATCH /tables/{table}/{id}` | Model-driven reads for any table (filters: `col=value`, `col__in=a,b`); writes only for tables people may edit directly (reference data, contacts, skills, consent, checklist tasks) |
| `GET /approvals`, `GET /approvals/{id}`, `POST /approvals/{id}/resolve` | Approvals and the backend's resolve function |
| `GET /workflows/instances`, `GET /workflows/instances/{id}` | Workflow state, transition log and definition (five roles only) |
| `GET /audit/subject?table=&id=` | Audit trail for one record: approvals, workflow transitions and audit-log rows the role may read, in time order |
| `GET /evaluations` | Automated pre-check results (decision, confidence, threshold, mode); inputs and raw output are never returned |
| `GET /hire/requisitions`, `GET /hire/requisitions/{id}` | Requisitions with a plain stage, one with its candidate pipeline (screening, interview, offer) and, once an employee row exists, an `onboarding` block (employee id, workflow state/status, whether the flow is waiting on `request-consent`) |
| `POST /hire/requisitions/{id}/applications` | HR enters an application (runs the backend's `submit_application`); only while the posting is live |
| `POST /hire/requisitions/{id}/request-consent` | HR-only. `consent_record` has no agent writer by design -- this tells the flow the new hire has granted their own consent, raising the `dpdp_consent` approval for them to resolve themselves |
| `GET /directory` | The backend's employee_directory view |
| `POST /hire/start` | Starts a hire through the backend's `start_hire`. A second start for the same position returns the existing hire |
| `POST /payroll/runs` | Builds a payroll run for a legal entity and period (every active employee under it) and runs its anomaly pre-check in the same call -- shadow mode always escalates, so there is no decision point in between |
| `POST /payroll/runs/{id}/request-disbursal`, `POST /payroll/runs/{id}/disburse`, `POST /payroll/runs/{id}/issue-payslips` | Disbursal (gated: impossible without an approved `g_pay_disburse` request, enforced in Postgres, not here) and payslip issuance. Payroll is not workflow-engine-driven, so these are direct actions, not something the queue worker runs on its own -- see `daydor.payroll.run_builder`'s module docstring |

Errors always look like `{"error": {"code", "message"}}`. Every POST accepts an `Idempotency-Key` header.

## Rules

- Never edits backend code, migrations or the model.
- Each request runs as the caller's own database role through `tenant_session`. Flow starts and payroll actions run as the matching agent role (`agent_ta`, `agent_pay`) with the person's user id in the session, because workflow instances (and most backend domain writes) can only be made by agent roles. Never an owner, `daydor_system` or a row-security-bypassing role.
- One exception, by necessity: a new hire's own sign-in (`app_user` plus this package's own `api.identity` row) is provisioned automatically when their `employee` row is created (`onboarding.py`), as `tenant_founder` -- the model's `dpdp_consent` gate can only be resolved by the employee themselves, and the backend's own SSO step (which would otherwise provision this) runs *after* consent, so sign-in has to exist earlier for the gate to ever be resolvable through this API at all. `tenant_founder`, not the more obviously IT-flavored `tenant_it`, because IT's own column grant on `app_user` excludes `email`.
- Workflow context is returned through an allowlist: candidate names, emails, phones and compensation stay in the database.
- Encrypted columns are never selected.
- `worker.py` registers every Hire-flow handler (all 18 steps, background check through payroll profile); nothing is registered for Payroll (not workflow-engine-driven, see above) or Exit (no screens built yet).

## Configuration

`DAYDOR_DATABASE_URL`, `DAYDOR_API_ENV` (`dev` or other), `DAYDOR_API_SECRET` (required outside dev), `DAYDOR_API_TOKEN_TTL`, `DAYDOR_API_CORS`. In production the connecting database user should be a dedicated login role that is a member of the tenant roles, not an owner.
