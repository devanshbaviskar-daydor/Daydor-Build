# FE-0 demo script

Ten minutes. Two parts: the preview (sample data, nothing to install) and the live path.

## Part 1: preview (sample data)

1. Open the preview. A "Sample data" badge shows in the top bar. Sign in as **Rohan Mehta** (Founder).
2. **Overview** lists what is waiting for him: two approvals.
3. Open **Approvals**. Approve the *Requisition budget sign-off* with a note. It moves to **Resolved** with the note.
4. Use the account switcher (top right) to become **Kavya Menon** (HR). The same request is there, with no Approve button and the line "Waiting for Founder / owner."
5. Switch to **Arjun Rao** (Employee). Approvals show; Positions are not listed under "Coming next".
6. Switch to **Daydor Admin**. Approvals show a plain "Your role does not have access to this."
7. Open **Design primitives**. Check the Field table: one value passed to four roles; the manager and Daydor admin never see it.

## Part 2: live (real Postgres, API and queue worker)

Follow "Run it against the real backend" in the README, then:

1. `VITE_API_MODE=live npm run dev`. The badge now reads "Live: auth, meta, tables, approvals, workflows, hire".
2. Sign in as **Kavya Menon**. In a terminal, start a hire (or use the live test, which does exactly this):
   `DAYDOR_LIVE_API=http://localhost:8000 npx vitest run src/api/live.test.ts`
3. Sign in as **Rohan Mehta**. Within a couple of seconds the queue worker has raised the budget approval. Approve it.
4. The worker log shows the workflow advancing; `GET /api/workflows/instances/{id}` as the founder shows state `s04_job_posting`.

## What to look for

- The same screens behave identically in mock and live (same error codes, same role limits).
- A request the database refuses (wrong role, already resolved) shows a plain sentence, never a database message.
- Nothing personal appears in workflow context: candidate names, emails and phone numbers stay in the database.
