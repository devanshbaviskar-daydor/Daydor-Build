"""Background-check vendor adapter: orders a check and reports whether its finding is adverse.

No real vendor is wired up yet (docs/sprint-plan.md: adapters are mocks until a sprint says
otherwise). `FakeBackgroundCheckAdapter` returns whatever outcome it was constructed with --
tests pick the outcome explicitly rather than this module guessing at what "adverse" should mean
for a given candidate.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal, Protocol

Outcome = Literal["clear", "adverse"]


@dataclass(frozen=True)
class BackgroundCheckRequest:
    full_name: str
    email: str


@dataclass(frozen=True)
class BackgroundCheckResult:
    vendor_ref: str
    outcome: Outcome


class BackgroundCheckAdapter(Protocol):
    def order(self, request: BackgroundCheckRequest) -> BackgroundCheckResult: ...


class FakeBackgroundCheckAdapter:
    """Always returns the outcome it was constructed with. No network, no external state."""

    def __init__(self, outcome: Outcome = "clear") -> None:
        self.outcome = outcome

    def order(self, request: BackgroundCheckRequest) -> BackgroundCheckResult:
        return BackgroundCheckResult(vendor_ref=f"fake-bgc-{uuid.uuid4().hex[:12]}", outcome=self.outcome)
