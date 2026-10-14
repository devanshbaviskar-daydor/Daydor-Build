"""Request ids and one structured log line per request.

Every response carries `X-Request-ID` (the caller's, if it sent a sane one, else a new one). The log line has the method, the *route template*
(never the raw path: a webhook URL carries a secret), the status and the time taken as JSON, and nothing from the query string, headers or
body, which can hold personal data."""
from __future__ import annotations

import json
import logging
import re
import time
import uuid

from fastapi import FastAPI, Request

log = logging.getLogger("daydor_api.request")
SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_log(request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if SAFE_ID.match(incoming) else uuid.uuid4().hex
        started = time.monotonic()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            route = request.scope.get("route")
            log.info(json.dumps({"request_id": request_id, "method": request.method, "route": getattr(route, "path", "unmatched"),
                                 "status": status, "ms": int((time.monotonic() - started) * 1000)}))
