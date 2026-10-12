"""Job board adapter: publishes a `job_posting` to an external channel.

No real vendor is wired up yet (docs/sprint-plan.md: adapters are mocks until a sprint says
otherwise). `FakeJobBoardAdapter` is deterministic, keeps no external state, and is what
`src/daydor/hire/posting.py` uses today; swap in a real HTTP-backed implementation later behind
the same `JobBoardAdapter` protocol.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from .base import AdapterError


@dataclass(frozen=True)
class JobPostingRequest:
    channel: str
    pay_range_min: float
    pay_range_max: float


@dataclass(frozen=True)
class JobPostingResult:
    external_ref: str


class JobBoardAdapter(Protocol):
    def publish(self, request: JobPostingRequest) -> JobPostingResult: ...


class FakeJobBoardAdapter:
    """Always succeeds with a synthetic reference. No network, no external state."""

    def publish(self, request: JobPostingRequest) -> JobPostingResult:
        if request.pay_range_min > request.pay_range_max:
            raise AdapterError(
                f"invalid pay range: {request.pay_range_min} > {request.pay_range_max}")
        return JobPostingResult(external_ref=f"fake-posting-{uuid.uuid4().hex[:12]}")
