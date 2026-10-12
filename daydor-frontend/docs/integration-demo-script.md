# Integration demo script: Hire end to end, to a first payslip

What Phases 0-3 of the backend integration shipped: the Hire flow's steps 9-18 (background check
through payroll profile) running live, and a real payroll run through to a first payslip. See
`docs/integration-notes.md` for the full write-up; this is the walkthrough.

Needs the real backend: follow the README's "Run it against the real backend" section first
(Postgres running, migrated, seeded; API and worker running; `VITE_API_MODE=live npm run dev`).

## In the browser

1. Sign in as **Kavya Menon** (HR). **Positions** → **Start hiring** on an open seat. Fill the form:
   this dialog now also asks for the new hire's own details (work location, date of birth,
   personal address, Aadhaar last 4, basic + DA, tax regime, pay frequency, payment method) --
   the flow reads these from context when it creates the employee and payroll-profile records
   later, and there's no later point to add them.
2. Sign in as **Rohan Mehta** (Founder), approve the budget in **Approvals**.
3. Back as **Kavya**: open the requisition, **Enter an application**, approve the AEDT sign-off
   once it appears.
4. Wait a few seconds (the queue worker is polling): the requisition's **Background check** step
   fills in on its own -- no approval needed for a clear result. Open the new hire's **person
   profile**: **Job and pay** now shows a real employment record; **Onboarding** shows their
   checklist; **Access** shows their app grants.
5. On the requisition page, a new **Onboarding** section appears once the employee record exists.
   When it says the flow is waiting for consent, click **Request consent sign-off** (HR-only).
6. The new hire's own sign-in now exists (provisioned automatically when their employee record was
   created). Sign in as them (the email they applied with) on **My privacy**, grant a consent
   record, then resolve the `dpdp_consent` approval that's now in their **Approvals** inbox --
   they are the only role who can.
7. Back as **Kavya** or **Rohan**: the requisition's workflow instance reaches its real terminal
   state (`done`). The person profile's **Work authorization** tab shows a real I-9 case for a US
   hire, or stays empty by design for an India hire (work authorization is US-only).

## From the terminal: a real payroll run to a first payslip

No Payroll screen exists yet, so this part is `curl` against the API directly (or the backend's
own `tests/test_payroll_compute.py` fixtures if you'd rather read real numbers than run them).
Sign in and grab a token first:

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/auth/dev-login -H 'content-type: application/json' \
  -d '{"email": "dev.patel@acme.test"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')

# Build the run (every active employee under the legal entity) and its anomaly pre-check in one call
curl -s -X POST localhost:8000/api/payroll/runs -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"legal_entity_id": "<the new hire'\''s legal_entity_id>", "period_start": "2026-12-01", "period_end": "2026-12-31", "retention_class_id": "<a retention_policy id>"}'
```

The anomaly check always escalates in shadow mode, so resolve `g_pay_anomaly` as `daydor_ops`
(not `dev.patel@acme.test` -- maker-checker: the person who built the run cannot also clear it),
request disbursal, resolve `g_pay_disburse` as the founder, disburse, then issue payslips:

```bash
curl -s -X POST localhost:8000/api/payroll/runs/<run_id>/request-disbursal -H "authorization: Bearer $TOKEN"
# resolve g_pay_disburse as rohan.mehta@acme.test via POST /api/approvals/<id>/resolve
curl -s -X POST localhost:8000/api/payroll/runs/<run_id>/disburse -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d '{"approval_request_id": "<the disbursal approval id>"}'
curl -s -X POST localhost:8000/api/payroll/runs/<run_id>/issue-payslips -H "authorization: Bearer $TOKEN"
```

Then open the new hire's **person profile** → **Payroll and payslips**: their first payslip, with
real (illustrative, not compliance-grade) statutory withholding.

`api/tests/test_hire_end_to_end.py` and `frontend/src/api/live.test.ts` run this entire path
(both India and US) through the real API and worker already -- this script is for watching it
happen, not for verifying it works.
