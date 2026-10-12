"""Statutory tax filing adapter: submits one filing (ECR, 24Q, 941, W-2, state UI, ...) and
reports an acknowledgement number.

No real vendor is wired up yet (docs/sprint-plan.md: adapters are mocks until a sprint says
otherwise).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TaxFilingRequest:
    scheme: str
    period: str


@dataclass(frozen=True)
class TaxFilingResult:
    acknowledgement_no: str


class TaxFilingAdapter(Protocol):
    def submit(self, request: TaxFilingRequest) -> TaxFilingResult: ...


class FakeTaxFilingAdapter:
    """Always succeeds with a synthetic acknowledgement number. No network, no external state."""

    def submit(self, request: TaxFilingRequest) -> TaxFilingResult:
        return TaxFilingResult(acknowledgement_no=f"fake-ack-{uuid.uuid4().hex[:12]}")
