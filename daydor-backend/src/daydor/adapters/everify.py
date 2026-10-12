"""E-Verify adapter: submits an I-9 case and reports a case number + status.

US only (see daydor.hire.work_authorization). No real vendor is wired up yet
(docs/sprint-plan.md: adapters are mocks until a sprint says otherwise).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EVerifyRequest:
    employee_id: str


@dataclass(frozen=True)
class EVerifyResult:
    case_number: str
    status: str


class EVerifyAdapter(Protocol):
    def submit(self, request: EVerifyRequest) -> EVerifyResult: ...


class FakeEVerifyAdapter:
    """Always returns a fresh, pending case. No network, no external state."""

    def submit(self, request: EVerifyRequest) -> EVerifyResult:
        return EVerifyResult(case_number=f"fake-case-{uuid.uuid4().hex[:10]}", status="pending")
