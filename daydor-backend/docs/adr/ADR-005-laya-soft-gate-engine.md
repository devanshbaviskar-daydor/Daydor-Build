# ADR-005: Laya as the soft-gate engine

Status: accepted, Oct 12 2026. Supersedes the Jev parts of ADR-003; its hard-gate, fail-closed and
shadow-mode decisions stand. **Implementation status: not built.** The code still has the Jev stub
(`src/daydor/gates/jev.py`); see "Implementation" below.

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

## Implementation (repo state when this was adopted)
- Today: `daydor.gates.jev` (`JevClient`, `HttpJevClient` stub, `JevResult`), `daydor.gates.soft`,
  `app.gate_evaluation.engine` (documented as `'jev'`), `WorkflowEngine(..., jev=...)`, and
  `daydor.payroll.anomaly` (the only soft gate wired). Tests use `FakeJev`.
- To do: rename to `DeciderClient` / `DeciderResult`, add `LayaClient`, and add a **new forward-only
  migration** (0025 or later; 0011 is the privacy migration) for the `calibration_version` column and the
  enforce and engine checks. Applied migrations are never edited.
- ADR-005 originally referred to an ADR-004 (worker classification) that does not exist in this repo.
  Nothing here depends on it.
