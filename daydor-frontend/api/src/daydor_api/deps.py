from __future__ import annotations

from fastapi import Header

from . import identity as idn
from . import tokens
from .config import settings
from .errors import ApiError


def get_identity(authorization: str | None = Header(default=None)) -> idn.Identity:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(401, "not_signed_in", "Sign in to continue.")
    payload = tokens.verify(authorization[7:].strip(), settings().secret)
    if not payload:
        raise ApiError(401, "session_expired", "Your session has expired. Sign in again.")
    ident = idn.find_by_id(payload["sub"])
    if ident is None:
        raise ApiError(401, "not_signed_in", "This account is no longer active.")
    return ident


def idempotency_key(idempotency_key: str | None = Header(default=None)) -> str | None:
    return idempotency_key
