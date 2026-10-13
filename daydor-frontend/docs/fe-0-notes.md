# FE-0 notes

## Built

- `api/`: FastAPI layer (sign-in, role-scoped reads and writes, approvals, workflows, start hire), identity and idempotency tables in its own schema, queue worker runner, dev seed, enum scanner. 29 tests against real Postgres.
- `frontend/`: shell, role-aware navigation, sign-in, Overview and Approvals screens, nine shared primitives, generated contract (82 tables, 10 roles, 23 gates), mock backend, mock/live transport, 47 tests including accessibility checks.
- End to end: the frontend's client signed in, started a hire, the worker raised the approval, the founder approved it and the workflow advanced, all on real Postgres.

## Differs from the approved plan

| Plan | What was built | Why |
| --- | --- | --- |
| MSW for mocking | A small fetch-level mock router behind the same transport | MSW needs a service worker file, which a hosted preview cannot serve. Same code path as live calls, so the plan's reason still holds |
| Storybook | A `Design primitives` page in the app | Lighter, reviewable in the hosted preview, covered by an accessibility test. Storybook can be added later |
| Tailwind | Design tokens as CSS variables and plain CSS | One fewer build dependency; carries the mockup look |
| Playwright end-to-end | Not yet | No browser could be installed in the build environment. The live test exercises the same client without a browser |
| API confirms the `app_user` row on every sign-in | Done for roles that can read `app_user`; payroll and managers (no read access) are confirmed when the identity is provisioned | The database gives those two roles no access to the table |
| "Always the caller's role" | Flow starts run as the `hire-intake` platform actor (a `worker_*` role) with the person's user id in the session | Workflow instances can only be inserted by worker roles. No owner or bypass role is used |

## Found in the backend (no change requested; the frontend works around each)

1. Nothing runs the queue workers. Handlers are registered only in tests. `api/src/daydor_api/worker.py` is the runner.
2. Starting a hire also needs the comp band, proposed base (and equity) and interview details at start time, not only interviewer and time, because later steps read them from the workflow context.
3. `app.timer` is readable by `daydor_ops` only.
4. Workflow context holds candidate name, email and phone. The API returns an allowlist of keys only.
5. Enum values: 14 of 88 enum columns have values discoverable in the backend's code. The rest are unlisted; the UI shows raw values and free-text inputs for them.

## Not done or not verified

- No screenshots were taken (no browser available), so layout is verified by tests and the accessibility checker only.
- `.github/workflows/ci.yml` has never run.
- Dark mode, non-English locales and the phone layout of the Approvals table were not exercised.

## Asks for the backend

None.
