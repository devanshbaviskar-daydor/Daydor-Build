# ADR-003: Hard gates in the database, soft gates in front of them

Status: accepted, Oct 8 2026. The Jev parts are superseded by ADR-005 (Laya); the hard-gate, write-guard,
fail-closed and shadow-mode decisions stand.

## Decision
- **Hard gates** (the model's 20) are rows in `app.gate_definition`; each instance is a
  `public.approval_request`. A trigger enforces: approver role from the registry, maker-checker
  (requester taken from the session, resolver must differ), signed-in resolver, immutability once
  resolved. Resolution goes through `app.resolve_approval()`; agents cannot execute it.
- **Write guards** (`app.gate_guard`) make the database refuse irreversible writes unless an
  approved request exists for that exact row: payroll disbursal, final settlement, contractor
  payment, GL posting, deprovisioning, ER adjudication. Guarded columns are final once set.
- **Soft gates** run a typed-decision engine (Jev here, Laya per ADR-005) on typed questions and can only decide whether an extra hard review is
  needed. They never resolve a hard gate. Inputs are declared model columns capped at a class
  limit (C3/C4 never allowed), only an input hash is stored (ADR-005 revisits the reasoning), any error escalates, and shadow mode
  always escalates. The database computes the effective decision from the gate's mode and threshold.

## Rollout of a soft gate
1. Shadow mode: the engine's answer is logged next to the human decision.
2. Compare agreement and calibration from `app.gate_evaluation` against approval outcomes.
3. Switch to enforce with a threshold chosen from that data; keep shadow logging for drift.

## Consequences
Conditional gates (out-of-band offers, AP above materiality, 409A staleness) are decided in
application code because the condition needs data the trigger should not own.
