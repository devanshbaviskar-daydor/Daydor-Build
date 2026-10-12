from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from . import errors
from .config import DEFAULT_SECRET, settings
from .routers import approvals, auth, directory, exit as exit_router, hire, meta, payroll, requisitions, tables, timekeeping, trail, workflows
from .state import get_engine


def create_app() -> FastAPI:
    s = settings()
    if s.env != "dev" and s.secret == DEFAULT_SECRET:
        raise RuntimeError("Set DAYDOR_API_SECRET before running outside development.")
    app = FastAPI(title="Daydor API", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=list(s.cors_origins), allow_methods=["*"],
                       allow_headers=["*"])
    errors.install(app)
    api = APIRouter(prefix="/api")

    @api.get("/health")
    def health():
        with get_engine().begin() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "env": s.env}

    for r in (auth.router, meta.router, tables.router, approvals.router, workflows.router, trail.router, hire.router, requisitions.router,
              directory.router, payroll.router, timekeeping.router, exit_router.router):
        api.include_router(r)
    app.include_router(api)
    return app



def get_app() -> FastAPI:
    return create_app()
