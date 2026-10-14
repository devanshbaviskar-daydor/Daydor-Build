# Deployment and operations

What exists, what is untested, and what a real deployment still needs. Written Oct 14 2026 (Phase F). Read `open-issues.md` next to this.

## The pieces
| Piece | What it is |
|---|---|
| `Dockerfile` | One image for the API (`uvicorn daydor_api.app:get_app --factory`) and the queue worker (`python -m daydor_api.worker`). Runs as an unprivileged user. Installs the backend editable, because `registry/`, `model/` and `migrations/` are read from the source tree. |
| `docker-compose.yml` | Postgres 16, a one-shot `migrate` job (alembic, the API's schema, then the password bootstrap), the API and the worker. A production-shaped stack on one machine, not a deploy pipeline. |
| `.env.example` | Every setting, with what is optional. |
| CI (`.github/workflows/ci.yml`) | Backend tests, golden-set replay, API tests, frontend tests, contract drift, and an image build that fails if the Dockerfile stops working. |

## First start
1. `cp .env.example .env`, fill in `DAYDOR_OWNER_PASSWORD`, `DAYDOR_APP_PASSWORD` (20+ characters, not `dev`) and `DAYDOR_API_SECRET`.
2. `docker compose up --build`. `migrate` runs the migrations **as the owner** (they create roles), sets the application password, and exits; the API and worker then
   connect as `daydor_app`, never as the owner.
3. The API refuses to start outside development if it connects as the owner or with the development password (`daydor_api.config.check_database_login`); migration
   0001 creates `daydor_app` with the password `dev`, which is why the bootstrap step exists.

## Operating it
- **Health:** `GET /api/health` (liveness and database). `GET /api/ops/health` returns the platform's aggregate numbers and alerts; `GET /api/ops/metrics` is the same in
  Prometheus text format. Both need a `daydor_admin` token. Alerts: an open circuit (critical), dead jobs, a queue backlog over 15 minutes, failed webhook events, agent
  failures, tenants at 80% of their AI cap, approvals past deadline.
- **Logs:** one JSON line per request (`request_id`, method, route template, status, ms). Never the raw path, query, headers or body: a webhook URL carries a secret and
  bodies can hold personal data. Every response carries `X-Request-ID`.
- **Webhooks:** ops creates an endpoint per tenant and integration (`app.create_webhook_endpoint('bank')` returns the URL secret once; only its hash is stored) and gives the
  vendor `https://<host>/api/webhooks/bank/<secret>` and a shared signing secret set in `DAYDOR_WEBHOOK_SECRETS`. Events are stored once, signature-checked, and kept even
  when no handler exists yet (`ignored`); `app.replay_webhook` puts one back on the queue.
- **Vendor outages:** wrap an adapter with `daydor.adapters.resilient.guard(adapter, "bank", conn)`. An open breaker defers the job without spending an attempt.
- **Turning the model on:** `DAYDOR_MODEL_PROVIDER=claude` and `ANTHROPIC_API_KEY`, then per tenant: the front door (`app.frontdoor_tenant`), each LLM worker's rollout stage
  (`daydor.agents.rollout`), a monthly cap (`app.tenant_ai_budget`). See `agent-harness.md`.

## Not verified or not built (all in `open-issues.md`)
- **Verified Oct 14 on a laptop:** `docker build` succeeds; `docker compose up` migrated a fresh database, set the application password, started the API as `daydor_app` (healthy,
  `env: production`, `dev-login` returns 404) and the worker (12 queues). Not verified: any cloud, TLS, a real tenant, or the model.
- **There is no production sign-in.** `POST /auth/dev-login` exists only when `DAYDOR_API_ENV=dev`. Real sign-in (SSO/OIDC, session handling, MFA) is not built.
- Alert *delivery* (paging, email, chat) is not built; alerts are read from `/api/ops/health`.
- Backups, point-in-time recovery, secrets management, TLS termination, autoscaling and multi-region are the platform's, not the code's, and need decisions.
- Webhook signature scheme is one generic HMAC; each real vendor will need its own header names and verification.
