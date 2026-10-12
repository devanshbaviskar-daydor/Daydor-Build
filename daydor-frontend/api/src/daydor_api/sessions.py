"""How the API opens a database session.

human_session: as the signed-in person's own role. Row security, column grants and maker-checker
apply exactly as they would for that person.

agent_session: for actions a person starts but the backend runs as a domain agent (workflow
instances can only be inserted by agent roles). The person's user id rides along in the session so
the database still knows who asked. Never an owner, `daydor_system` or any row-security-bypassing role."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Connection

from daydor.db.session import tenant_session

from .identity import Identity
from .state import get_engine

ALLOWED_AGENT_ROLES = frozenset({"agent_ta", "agent_hr", "agent_ro", "agent_pay", "agent_time", "agent_ben", "agent_it"})


@contextmanager
def human_session(ident: Identity) -> Iterator[Connection]:
    with tenant_session(get_engine(), ident.role, ident.tenant_id, user_id=ident.user_id,
                        employee_id=ident.employee_id) as conn:
        yield conn


@contextmanager
def agent_session(ident: Identity, agent_role: str) -> Iterator[Connection]:
    if agent_role not in ALLOWED_AGENT_ROLES:
        raise ValueError(f"agent role {agent_role!r} is not allowed for API-started actions")
    with tenant_session(get_engine(), agent_role, ident.tenant_id, user_id=ident.user_id) as conn:
        yield conn
