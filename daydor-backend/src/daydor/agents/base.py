"""Placeholder for an agentic execution harness.

Nothing here is wired into the queue yet, and no sprint currently depends on it. It exists so the
shape of the eventual seam is visible and doesn't get invented ad hoc the first time a worker
actually needs model judgment instead of deterministic logic.

Some hire-flow workers read, in the model's own words, as something an agent would do
("requisition-drafter: drafted from the hiring manager's input", "candidate-screener"). They are
implemented as plain deterministic Python for now (see e.g. src/daydor/hire/requisition.py) —
there is no prompt, model or eval story yet, and bolting one on today would be speculative. This
module is where that story plugs in once it exists, the same way src/daydor/gates/decider.py is
the interface for soft-gate AI evaluation (`DeciderClient`; `daydor.gates.soft` is written against
the interface, not an implementation).

Sketch, not implementation:
  - `AgentTask` bounds what an agent may see by data class, the same C0-C4 discipline
    `app.decrypt_pii` enforces and a soft gate's `max_input_class` already encodes (`docs/adr/
    ADR-003-gates.md`): never hand an agent C3/C4 data.
  - `AgentWorker` returns a typed, auditable `AgentDecision` — never a bare string — so its output
    can be logged the same way `app.gate_evaluation` logs a soft gate's, and a human can always see why
    an agent did what it did.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AgentTask:
    kind: str                  # e.g. "draft_requisition", "score_candidate"
    input: dict[str, Any]      # must already be bounded to max_input_class by the caller
    max_input_class: str       # "S" | "C0" | "C1" | "C2" -- never C3/C4, same rule as soft gates


@dataclass(frozen=True)
class AgentDecision:
    output: dict[str, Any]
    confidence: float | None = None
    rationale: str | None = None


class AgentWorker(Protocol):
    def run(self, task: AgentTask) -> AgentDecision: ...
