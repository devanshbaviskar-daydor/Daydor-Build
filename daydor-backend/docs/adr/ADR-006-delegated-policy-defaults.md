# ADR-006: Defaults for the open policy decisions

Status: accepted as the working default, Oct 13 2026. These were open decisions that the project owner
delegated ("assume your best decision"), so each one is a conservative default, not a settled legal or product
position. The first, second and fourth below deserve a human review (legal and HR) before anything relies on them.
Any item can be reversed by a new ADR; none loosens a rule that existed before.

## 1. Irreversible workers with no hard gate
Four registry workers have an irreversible external effect and no hard gate covering their tables:
`i9-e-verify-initiator`, `tax-filing-submitter`, `device-purchase-initiator`, `in-country-tax-remitter`.
- All four stay `autonomy=approve` (already enforced by the registry rules).
- `device-purchase-initiator` and `in-country-tax-remitter` have no flow and no code (wave 4). They start
  **disabled** (`enabled_by_default: false`, migration `0032`), so a job for them fails closed. Enabling one is a
  reviewed change that also adds its gate. A registry rule enforces this for any future worker in the same position.
- `i9-e-verify-initiator` and `tax-filing-submitter` stay enabled: they sit in the hire and payroll flows and talk only
  to mock adapters. **Before a real vendor adapter replaces either mock, a hard gate for it must exist** (for filings, an
  approval by payroll or the founder on `filing_record`; for E-Verify, HR on `work_authorization`). No gate is added
  now, because it would change two built flows and nothing irreversible happens against a mock.

## 2. candidate-screener and resume text
Resume text, and every other C3 field, is **never a model input**.
- The worker's `llm` assist ("resume field extraction") is removed: an LLM reading a resume sends C3 to a third-party API.
- The decider sees structured, non-restricted features only, is **shadow only**, and cannot enforce. `g_aedt` stays a human
  gate. The registry flag changes from `needs-policy-decision` to `c3-inputs-excluded`, which the registry tests validate:
  no model assist, `autonomy=approve`, `shadow-only`, no soft gate.
- Enforcing would need a new ADR, a bias audit and legal review of automated employment decision tools.

## 3. Restricted data and models
- C4 and encrypted columns are never inputs to any model (the soft-gate runner already refuses them).
- C3 is closed by default. It may open **per gate** only through a recorded decision, a local model only, and its own bias
  audit. Nothing is opened today.
- LLM workers go through a third-party API and keep the strict rule for C3 and C4.
- Reason: discrimination and purpose-limitation risk exist wherever the model runs, not only when data leaves us.

## 4. Training on tenant data
No tenant's decisions or data train a model that serves another tenant without an explicit contractual opt-in. Start
from synthetic and Daydor-owned data. A labelled-example store, when built, is per gate, access-controlled and
retention-limited, and off by default. Nothing is stored for training today (inputs are hashed only).

## 5. Guards on `expense.reimbursed_at` and `leave_request.fmla_designation`
Migration `0031` (and the regenerated `0007` for fresh installs) makes the database refuse these two columns without an
approved `g_expense` / `g_fmla` request for the same row.
- `leave_request.status` is deliberately **not** guarded: it is NOT NULL with a default, and a guard fires on the NULL to
  value transition, so it would block every insert.
- No service writes either column, so nothing changes today. No worker holds `reimbursed_at` (nobody reimburses yet), and
  the model gives agents no write on `fmla_designation` (HR reads it; the employee's write is capped by finding 23), so
  the guard there is exercised through the table owner. Findings 23 and 29 record the gap.

## Consequences
- Policy items 2 to 4 are recorded and mostly already enforced in code; they need human sign-off, not more code.
- Item 1 adds a runtime off-switch (`enabled`) that earlier ADRs did not have a use for.
- Item 5 closes the "no gate guard" half of finding 23.
