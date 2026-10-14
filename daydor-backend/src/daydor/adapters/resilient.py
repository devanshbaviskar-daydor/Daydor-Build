"""A circuit breaker around any vendor adapter (migration 0046 registers one per adapter; 0043 made the breaker).

    adapter = guard(FakeBankAdapter(), "bank", conn)         # or the real one, later
    adapter.transfer(request)

Each call first asks the breaker. When it is open the call is not made: `IntegrationUnavailable` is raised, and the queue worker defers the
job without spending an attempt. The outcome of each call is recorded in its own short transaction (as the dispatcher role), so it survives
the handler's rollback. An adapter signals "the vendor answered and said no" with `AdapterRejected`: that is not an outage and does not
count against the breaker. Anything else it raises does.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, Engine

from daydor import circuit
from daydor.db.session import tenant_session
from daydor.queue.worker import Deferred


class IntegrationUnavailable(Deferred):
    def __init__(self, integration: str, retry_after_s: int) -> None:
        super().__init__(max(retry_after_s, 1), f"the {integration} integration's circuit is open")
        self.integration = integration


class AdapterRejected(Exception):
    """The vendor answered and refused (bad input, not allowed). The vendor is up."""


class Guarded:
    def __init__(self, adapter: Any, integration: str, engine: Engine) -> None:
        self._adapter, self._integration, self._engine = adapter, integration, engine

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._adapter, name)
        if not callable(attr):
            return attr

        def call(*args: Any, **kwargs: Any) -> Any:
            with tenant_session(self._engine, "daydor_worker") as c:
                gate = circuit.allow(c, self._integration)
            if not gate.allowed:
                raise IntegrationUnavailable(self._integration, gate.retry_after_s)
            try:
                result = attr(*args, **kwargs)
            except AdapterRejected:
                self._record(True, None)
                raise
            except Exception as exc:  # noqa: BLE001 - any other failure is the vendor's, whatever it is
                self._record(False, f"{type(exc).__name__}: {exc}")
                raise
            self._record(True, None)
            return result
        return call

    def _record(self, ok: bool, error: str | None) -> None:
        with tenant_session(self._engine, "daydor_worker") as c:
            circuit.record(c, self._integration, ok, error)


def guard(adapter: Any, integration: str, conn_or_engine: Connection | Engine) -> Guarded:
    return Guarded(adapter, integration, conn_or_engine.engine if isinstance(conn_or_engine, Connection) else conn_or_engine)
