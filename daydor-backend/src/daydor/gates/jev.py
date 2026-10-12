"""Jev client interface.

Jev (TypeSafe's "System One" model) takes unstructured state plus a typed schema defined up
front and returns typed values with calibrated probabilities. It does not generate text, so a
soft gate asks small typed questions and code branches on the probabilities.

HttpJevClient is a stub until we have TypeSafe's API reference (early access). Everything else
depends only on the JevClient protocol, so wiring the real API touches this file only.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol

MAX_CHOICES = 255   # Jev's per-decision cardinality limit


@dataclass(frozen=True)
class Choice:
    """One typed question: pick one of `options`."""
    name: str
    options: tuple[str, ...]
    description: str = ""

    def __post_init__(self) -> None:
        if not 2 <= len(self.options) <= MAX_CHOICES:
            raise ValueError(f"{self.name}: needs 2..{MAX_CHOICES} options, got {len(self.options)}")
        if len(set(self.options)) != len(self.options):
            raise ValueError(f"{self.name}: duplicate options")


@dataclass(frozen=True)
class DecisionSchema:
    name: str
    version: str
    questions: tuple[Choice, ...]


@dataclass(frozen=True)
class Answer:
    value: str
    probabilities: dict[str, float]

    @property
    def confidence(self) -> float:
        return self.probabilities.get(self.value, 0.0)


@dataclass(frozen=True)
class JevResult:
    answers: dict[str, Answer]
    engine_version: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class JevClient(Protocol):
    def decide(self, schema: DecisionSchema, state: dict[str, Any], timeout_s: float) -> JevResult: ...


class HttpJevClient:
    """Placeholder for the TypeSafe API. Configure with JEV_API_URL / JEV_API_KEY."""

    def __init__(self, url: str | None = None, api_key: str | None = None) -> None:
        self.url = url or os.environ.get("JEV_API_URL")
        self.api_key = api_key or os.environ.get("JEV_API_KEY")

    def decide(self, schema: DecisionSchema, state: dict[str, Any], timeout_s: float) -> JevResult:
        raise NotImplementedError(
            "Jev HTTP API not wired yet: implement once TypeSafe early-access docs are available. "
            "Soft gates fail closed (escalate) while this raises."
        )
