# FE-1 demo script

Approvals and workflow core. Preview (sample data) first, then live.

## Preview

1. Sign in as **Rohan Mehta** (Founder). **Overview** shows "Waiting for you" and a **Workflows** summary.
2. **Approvals**: tabs show counts; the requests Rohan can decide come first (budget, offer band). Use the kind filter to show only offer-band requests.
3. Open **Details** on the budget request. **Where this stands** shows the workflow paused at the approval step. Approve with a note: the steps move on to *Job posting* and the note appears on the card.
4. **View audit trail**: asked for approval, approved (with the note, by "You"), paused, moved on, in time order.
5. **Workflows**: list, filter by status, open the workflow: steps, what happened, and the details it carries. Note the line saying some values stay in the database.
6. Switch to **Kavya Menon** (HR). The identity-account request shows "You raised this request, so someone else has to approve it." with no Approve button. Open the access-request approval: the **Automated pre-check** panel shows the result as shadow mode, not applied.
7. Switch to **Sana Qureshi** (IT). The same access request shows a one-sentence status instead of a timeline, no pre-check panel, and Approve works.
8. Switch to **Meera Iyer** (manager). No Workflows entry; opening `/workflows` explains why. The audit trail says workflow steps are not listed for her role, and names show as "A person".

## Live

Follow the README, then `VITE_API_MODE=live npm run dev`. Start a hire as HR (Positions come in FE-2; until then use `DAYDOR_LIVE_API=http://localhost:8000 npx vitest run src/api/live.test.ts`, which does it). As Rohan, the new request appears within seconds; approve it and watch the timeline move.

## What to look for

- A request the database refuses shows a plain sentence, never a database message.
- Roles see only what the database lets them read; nothing is fetched and then hidden.
- Soft-gate results are always labelled "Shadow mode, not applied".
