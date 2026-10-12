"""Common conventions for external-vendor adapters (IdP, bank, carriers, E-Verify, tax filing,
background checks, GL, job boards -- component 10 in docs/backend-plan.md).

Every adapter is a narrow `typing.Protocol` plus at least one implementation. Until a sprint
wires up a real vendor, it ships a `Fake*Adapter` that returns deterministic, canned results, so
domain services are written and tested against the real interface shape now, and a real
HTTP-backed implementation can be swapped in later behind the same Protocol without the caller
changing.

Adapters are called synchronously, in-process, from inside a queue handler (see
src/daydor/hire/posting.py for the first one). Nothing here talks to an inbound webhook path yet;
that's `docs/sprint-plan.md`'s backlog item, for whenever a real vendor's response is
asynchronous rather than an immediate call/response.
"""
from __future__ import annotations


class AdapterError(RuntimeError):
    """A vendor call failed in a way the caller should treat as a normal operational failure.

    Workers let this propagate — the queue's retry/backoff (src/daydor/queue/worker.py) is the
    retry policy, not the adapter. Adapters should raise this (or a subclass) rather than letting
    a vendor-specific exception type leak into domain-service code.
    """
