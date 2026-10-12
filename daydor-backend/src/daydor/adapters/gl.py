"""General ledger adapter: posts a journal entry to the external accounting system.

No real vendor is wired up yet (docs/sprint-plan.md: adapters are mocks until a sprint says
otherwise).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class JournalEntryRequest:
    debit_account: str
    credit_account: str
    amount: Decimal


@dataclass(frozen=True)
class JournalEntryResult:
    external_ref: str


class GLAdapter(Protocol):
    def post(self, request: JournalEntryRequest) -> JournalEntryResult: ...


class FakeGLAdapter:
    """Always succeeds with a synthetic reference. No network, no external state."""

    def post(self, request: JournalEntryRequest) -> JournalEntryResult:
        return JournalEntryResult(external_ref=f"fake-je-{uuid.uuid4().hex[:12]}")
