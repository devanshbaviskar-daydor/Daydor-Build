"""How the API opens a database session.

human_session: as the signed-in person's own role. Row security, column grants and maker-checker
apply exactly as they would for that person.

worker_session: for actions a person starts but the backend runs as the worker that owns the step
(workflow instances can only be inserted by worker roles). The role comes from the backend's worker
registry, so its column grants are exactly that worker's scope, and a disabled worker fails closed. The
person's user id rides along in the session so the database still knows who asked. Never an owner,
`daydor_system` or any row-security-bypassing role."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Connection

from daydor.agents.session import worker_session as _backend_worker_session
from daydor.db.session import tenant_session

from .identity import Identity
from .state import get_engine


@contextmanager
def human_session(ident: Identity) -> Iterator[Connection]:
    with tenant_session(get_engine(), ident.role, ident.tenant_id, user_id=ident.user_id,
                        employee_id=ident.employee_id) as conn:
        yield conn


@contextmanager
def worker_session(ident: Identity, worker: str) -> Iterator[Connection]:
    """Run as a registry worker or platform actor (for example "gl-poster", or "hire-intake" for the
    actions that start or advance a hire on a person's behalf)."""
    with _backend_worker_session(get_engine(), worker, ident.tenant_id, user_id=ident.user_id) as conn:
        yield conn

