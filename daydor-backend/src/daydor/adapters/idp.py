"""Identity-provider adapter: provisions a directory account (Google/Okta/Entra in the model's
own words) for a new hire.

No real vendor is wired up yet (docs/sprint-plan.md: adapters are mocks until a sprint says
otherwise).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class IdentityProvisionRequest:
    work_email: str


@dataclass(frozen=True)
class IdentityProvisionResult:
    directory_provider: str
    external_id: str


class IdPAdapter(Protocol):
    def provision(self, request: IdentityProvisionRequest) -> IdentityProvisionResult: ...


class FakeIdPAdapter:
    """Always succeeds with a synthetic external id. No network, no external state."""

    def __init__(self, directory_provider: str = "fake-directory") -> None:
        self.directory_provider = directory_provider

    def provision(self, request: IdentityProvisionRequest) -> IdentityProvisionResult:
        return IdentityProvisionResult(directory_provider=self.directory_provider,
                                       external_id=f"fake-id-{uuid.uuid4().hex[:10]}")
