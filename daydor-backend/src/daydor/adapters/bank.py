"""Bank adapter: direct-deposit disbursal.

No real vendor is wired up yet (docs/sprint-plan.md: adapters are mocks until a sprint says
otherwise).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class TransferRequest:
    reference: str
    amount: Decimal


@dataclass(frozen=True)
class TransferResult:
    transfer_ref: str


class BankAdapter(Protocol):
    def transfer(self, request: TransferRequest) -> TransferResult: ...


class FakeBankAdapter:
    """Always succeeds with a synthetic reference. No network, no external state."""

    def transfer(self, request: TransferRequest) -> TransferResult:
        return TransferResult(transfer_ref=f"fake-transfer-{uuid.uuid4().hex[:12]}")
