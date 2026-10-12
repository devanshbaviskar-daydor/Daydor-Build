# FE-1 notes

## Built

- **Approvals inbox:** counts per tab, what you can act on first, filter by kind, link to details.
- **Approval details:** decision card with note, the workflow timeline (roles that can read it) or a one-sentence status line (everyone else), automated pre-check results, audit trail.
- **Workflows:** list with status filter, detail page with steps, transition log and the details the workflow carries.
- **API:** `GET /audit/subject`, `GET /evaluations`, a workflow link on `GET /approvals/{id}`, subject filters on the approvals list, and `capabilities.workflow_timeline` on the session.
- **Tests:** 37 API tests, 63 frontend tests (incl. accessibility on the approval, workflow and inbox pages), and 3 live end-to-end tests on real Postgres with the queue worker.

## Decisions made on the frontend side

| Decision | Reason |
| --- | --- |
| Names on the audit trail only for founder, HR, IT and Daydor ops; everyone else sees "A person" | Those roles can already read `app_user` broadly. Employees can read approvals, and a founder's name is not something the database shows them |
| Audit trail is assembled from approvals, workflow transitions and `audit_log` | The backend's `audit_log` only records data-access events (consent, decrypt), so on its own it would show nothing for approvals |
| Evaluations never return inputs, hash or raw output | Only the decision, confidence, threshold and mode are needed; the rest stays in the database |
| Starting a hire for a position that already has one returns the existing hire (`existing: true`) | Found by testing: the backend raised an unhandled workflow error on a second start (double click, or two people). The API now returns the existing hire and maps any remaining workflow error to a 409 |

## Found in the backend (nothing requested)

1. A second `start_hire` for the same position raises `WorkflowError` instead of returning the existing instance. Worked around in the API.
2. The engine logs an extra `waiting_gate` transition row when it parks at a gate, so a workflow's log has one more row than its moves. The UI shows it as "Paused for approval".
3. Nothing produces gate evaluations for the Hire flow yet (the two soft gates belong to payroll and access requests), so the pre-check panel will be empty on live Hire data until those flows land. The sample data includes one to show the design.
4. Only the founder can resolve `g_requisition_budget`, so an HR admin who raises a hire cannot approve it. Maker-checker is therefore only visible for requests raised by a person; agent-raised requests have no requester.

## Fixed after delivery

- The first FE-1 preview crashed ("Cannot read properties of undefined (reading 'workflow_timeline')") for anyone whose browser still held a session saved by the FE-0 preview, because that saved session had no `capabilities`. The app now versions its saved session, discards a saved session with the wrong shape, and guards the field. Two regression tests cover it. Lesson: any change to the session shape needs a storage version bump.

## Not done or not verified

- No screenshots (no browser available); layout is verified by tests and the accessibility checker.
- Audit trail has no pagination (fine for one record; revisit if a subject grows large).
- Polling every 15 seconds; no push channel exists.
- `.github/workflows/ci.yml` still has not run.

## Asks for the backend

None.
