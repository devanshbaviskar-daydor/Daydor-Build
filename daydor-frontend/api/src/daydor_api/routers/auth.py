from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from .. import identity as idn
from .. import tokens
from ..config import settings
from ..deps import get_identity
from ..errors import ApiError
from ..sessions import human_session

router = APIRouter(prefix="/auth", tags=["auth"])


class DevLogin(BaseModel):
    email: str


def confirm_backend_user(ident: idn.Identity) -> None:
    """Inside a tenant session as the person's own role, confirm their app_user row is still active.
    Payroll and managers cannot read app_user, and platform staff have no row; those are confirmed
    when the identity is provisioned instead."""
    if ident.user_id is None or ident.role not in idn.CAN_READ_APP_USER:
        return
    with human_session(ident) as conn:
        row = conn.execute(text("SELECT is_active FROM app_user WHERE id = :u"), {"u": ident.user_id}).first()
    if row is None or not row[0]:
        raise ApiError(401, "identity_mismatch", "This account is not active in the platform.")


def issue(ident: idn.Identity) -> dict:
    confirm_backend_user(ident)
    s = settings()
    return {"token": tokens.sign({"sub": str(ident.id)}, s.secret, s.token_ttl_seconds),
            "session": ident.public()}


@router.post("/dev-login")
def dev_login(body: DevLogin):
    if settings().env != "dev":
        raise ApiError(404, "not_found", "Not found.")
    ident = idn.find_by_email(body.email)
    if ident is None:
        raise ApiError(401, "unknown_account", "No active account uses that email.")
    return issue(ident)


@router.get("/dev-users")
def dev_users():
    if settings().env != "dev":
        raise ApiError(404, "not_found", "Not found.")
    return {"users": [i.public() for i in idn.list_active()]}


@router.get("/me")
def me(ident: idn.Identity = Depends(get_identity)):
    return ident.public()
