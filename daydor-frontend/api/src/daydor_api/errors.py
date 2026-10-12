"""One error shape for every endpoint: {"error": {"code", "message"}}.

Codes are machine-readable so the UI can show the right explanation. Database messages are never
echoed; the few useful cases (maker-checker, wrong approver role) get fixed wording instead."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from daydor.hire.requisition import NoVacantPosition


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def map_db_error(exc: DBAPIError) -> tuple[int, str, str]:
    orig = exc.orig
    state = getattr(orig, "sqlstate", None)
    msg = str(getattr(getattr(orig, "diag", None), "message_primary", "") or orig)
    if "maker-checker" in msg:
        return 403, "maker_checker", "The person who raised this request cannot approve it."
    if "cannot approve gate" in msg:
        return 403, "wrong_approver_role", "Your role cannot approve this kind of request."
    if "already" in msg and "approval request" in msg:
        return 409, "already_resolved", "This request has already been resolved."
    if state == "42501":
        return 403, "forbidden", "Your role does not have access to this."
    if state == "P0002":
        return 404, "not_found", "That record was not found."
    if state == "23505":
        return 409, "duplicate", "That record already exists."
    if state == "23503":
        return 422, "invalid_reference", "A referenced record does not exist."
    if state in ("23514", "23502"):
        return 422, "check_violation", "A value is missing or not allowed."
    if state in ("22P02", "22007", "22008", "22003"):
        return 422, "invalid_value", "A value has the wrong format."
    return 500, "database_error", "The database could not complete this request."


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api(_: Request, exc: ApiError):
        return JSONResponse(_body(exc.code, exc.message), status_code=exc.status)

    @app.exception_handler(DBAPIError)
    async def _db(_: Request, exc: DBAPIError):
        status, code, message = map_db_error(exc)
        return JSONResponse(_body(code, message), status_code=status)

    @app.exception_handler(NoVacantPosition)
    async def _seat(_: Request, exc: NoVacantPosition):
        return JSONResponse(_body("no_open_seat", "That position is not an open, vacant, budgeted seat."),
                            status_code=409)

    @app.exception_handler(RequestValidationError)
    async def _val(_: Request, exc: RequestValidationError):
        fields = sorted({".".join(str(p) for p in e["loc"][1:]) or "body" for e in exc.errors()})
        return JSONResponse(_body("invalid_request", "Check these fields: " + ", ".join(fields)),
                            status_code=422)
