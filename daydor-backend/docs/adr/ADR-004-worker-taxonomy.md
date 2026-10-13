# ADR-004: Worker taxonomy and what may use a model

Status: accepted, Oct 8 2026

## Context
The model names 89 workers. They differ widely in risk: payroll arithmetic, bank transfers,
drafting a job description and flagging a policy breach should not run on the same machinery.

## Decision
Every worker has one kind, chosen by what its core job is:

- `rule`: deterministic code (55). Payroll, tax, accruals, templates, routing.
- `integration`: external API calls (15). Retries and idempotency come from the queue.
- `monitor`: detection on a schedule or event (10).
- `decider`: a typed soft decision feeding a hard gate (4).
- `llm`: generation or extraction from unstructured input (5), with typed output validation.

Eligibility is decided from the model's data classes, not from the worker's name. A worker may
use a model (as its kind or as an assist) only if no table in its scope has C3, C4 or encrypted
columns. This overturned several name-based guesses: `case-intake-router`, `qle-validator`,
`background-check-flagger` and the leave processors handle C4 data and are rules.

Autonomy is `auto`, `review` or `approve`. Irreversible external effects are always `approve`.
LLM workers may not take external actions, and may not send messages autonomously. Tenants can
lower a worker's autonomy but never raise it.

## Enforcement
`registry/worker_classification.json` holds the judgments; scope, gates, flows and data classes
are derived from the model. `tests/test_registry.py` enforces the rules and includes mutation tests
that prove each rule can fail.

## Consequences
Most of the system is testable code. Models sit at the edges (drafting, extraction, soft
decisions) where a wrong answer is recoverable and logged. Changing a worker's kind or autonomy
is a reviewed change to one JSON file.

Amended Oct 12 2026 (ADR-005): the kind formerly called `jev` is now `decider`, because the engine changed to Laya.
