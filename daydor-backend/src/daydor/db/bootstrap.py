"""Production bootstrap for the database logins (run once after the migrations, as the owner).

Migration 0001 creates the application login `daydor_app` with the development password 'dev'. That is fine on a laptop and wrong anywhere
else, so a deployment sets a real one:

    DAYDOR_OWNER_URL=postgresql+psycopg://daydor_owner:...@db/daydor DAYDOR_APP_PASSWORD=... python -m daydor.db.bootstrap

It refuses a short password or 'dev' unless DAYDOR_ENV=dev. The API itself refuses to start outside dev while it connects as the owner or
with the development password (`daydor_api.config.check_database_login`).
"""
from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, text

MIN_LENGTH = 20


def set_app_password(owner_url: str, password: str, *, dev: bool = False) -> None:
    if not dev and (password == "dev" or len(password) < MIN_LENGTH):
        raise ValueError(f"the application password must be at least {MIN_LENGTH} characters and not 'dev'")
    engine = create_engine(owner_url)
    with engine.begin() as conn:
        # ALTER ROLE takes a literal, not a bind parameter; SQL string escaping is doubling the quote (standard_conforming_strings is on).
        conn.exec_driver_sql("ALTER ROLE daydor_app PASSWORD '" + password.replace("'", "''") + "'")
    engine.dispose()


if __name__ == "__main__":  # pragma: no cover
    try:
        set_app_password(os.environ["DAYDOR_OWNER_URL"], os.environ["DAYDOR_APP_PASSWORD"], dev=os.environ.get("DAYDOR_ENV") == "dev")
    except (KeyError, ValueError) as exc:
        sys.exit(f"bootstrap: {exc}")
    print("application password set")
