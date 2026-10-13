# ADR-005: Laya as the soft-gate engine

Status: accepted, Oct 12 2026. Supersedes the Jev parts of ADR-003; its hard-gate, fail-closed and
shadow-mode decisions stand. **Implementation status (Oct 13 2026): interface, runner and database rules
built; never run against a real checkpoint.** See "Implementation" below.

## Context
ADR-003 put Jev (TypeSafe's hosted typed-decision API) in front of hard gates. We are using Laya
(Convai Innovations, Apache-2.0) instead: a local encoder that returns typed answers with
probabilities, with no API key and no data leaving our infrastructure.

## Decision
- Soft gates call a `DeciderClient` interface. `LayaClient` is the implementation. The engine kind
  recorded for a gate is `decider`, not the engine name, so a future swap does not rewrite the registry.
- Gates threshold on `answer_confidence` only. `confidence` (a different scale) and
  `action.act_probability` (no usable signal) are never used.
- The database refuses `mode='enforce'` without a `calibration_version`, checks that an evaluation
  comes from the gate's engine, and stores the calibration used.
- Loading unpinned weights is refused. Truncated input fails closed. Yes/no is sent as a two-option choice.
- Decisions stay at 20 options or fewer.

## Consequences
- No third-party transfer, and about 6 to 8 times lower latency on GPU. On CPU the latency is similar to Jev's.
- Base checkpoints are near chance and over-confident, so fine-tuning, calibration and a labelled-data
  pipeline are required before any gate enforces. This is real work, not a drop-in swap.
- The restricted-data rule is unchanged in code. Its justification has shifted from vendor transfer to
  discrimination and purpose-limitation risk; any relaxation for C3 is a separate, per-gate decision.
- ADR-003's description of Jev and the earlier input-hash-only rule are superseded where they conflict.

## Implementation (Oct 13 2026)
- Built: `daydor.gates.decider` (`DeciderClient`, `LayaClient`, typed `Choice`/`Score`/`Truth`), `daydor.gates.soft`
  and `WorkflowEngine(decider=...)` written against the interface, `0030_laya_decider.sql` (engine, checkpoint and
  `calibration_version` on `app.gate_definition`; calibration required to enforce; the engine is checked on every
  evaluation; each evaluation records the calibration that decided it). `jev.py` is removed.
- Both wired soft gates (`sg_payroll_anomaly_precheck`, `sg_access_request_precheck`) default to `LayaClient()`, which
  refuses to load without `LAYA_REVISION`, so they fail closed to `escalate` until a checkpoint is pinned.
- Smoke test against a real pinned checkpoint passed Oct 13 2026 (`tests/test_laya_smoke.py`, results in
  `docs/laya-runbook.md`): parsing, distributions, pinning and truncation are sound; the base checkpoint's judgement
  is poor, as expected, so gates stay in shadow mode.
- Not done: pinning and vendoring for production, the labelled-example store, calibration and the
  shadow-versus-human report.
- Old `app.gate_evaluation` rows may carry engine `jev`; nothing wrote real Jev rows.
