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
