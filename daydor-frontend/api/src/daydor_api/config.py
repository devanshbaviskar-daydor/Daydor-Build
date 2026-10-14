from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_SECRET = "dev-only-secret-change-me"


@dataclass(frozen=True)
class Settings:
    env: str
    secret: str
    token_ttl_seconds: int
    cors_origins: tuple[str, ...]


def settings() -> Settings:
    return Settings(
        env=os.environ.get("DAYDOR_API_ENV", "dev"),
        secret=os.environ.get("DAYDOR_API_SECRET", DEFAULT_SECRET),
        token_ttl_seconds=int(os.environ.get("DAYDOR_API_TOKEN_TTL", "28800")),
        cors_origins=tuple(o for o in os.environ.get(
            "DAYDOR_API_CORS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o),
    )


def check_database_login(url: str, env: str) -> None:
    """Outside development the API must not connect as the owner (it would bypass what the roles enforce) or with the development
    password that migration 0001 gives `daydor_app` (see daydor.db.bootstrap)."""
    if env == "dev":
        return
    from sqlalchemy.engine import make_url
    u = make_url(url)
    if u.username in ("daydor_owner", "postgres") or (u.password or "") in ("", "dev"):
        raise RuntimeError("Set DAYDOR_DATABASE_URL to the daydor_app login with a real password (python -m daydor.db.bootstrap); "
                           "the API will not run outside development as the owner or with the development password.")
