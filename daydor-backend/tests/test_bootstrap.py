"""The production bootstrap for the application login (daydor.db.bootstrap)."""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from daydor.db.bootstrap import set_app_password


def test_a_weak_password_is_refused_unless_this_is_development():
    for bad in ("dev", "short", "x" * 19):
        with pytest.raises(ValueError, match="at least 20"):
            set_app_password("postgresql+psycopg://nobody@nowhere/none", bad)


def test_the_password_is_set_and_works_then_put_back(engine):
    owner = os.environ.get("DAYDOR_TEST_DATABASE_URL")
    if not owner:
        pytest.skip("needs the test database url")
    secret = "it's-a-long-random-secret-1234"                         # a quote, to prove the escaping
    set_app_password(owner, secret)
    try:
        url = make_url(owner).set(username="daydor_app", password=secret)
        e = create_engine(url)
        with e.connect() as conn:
            assert conn.execute(text("SELECT current_user")).scalar_one() == "daydor_app"
        e.dispose()
        # (a wrong password is not refused on a development server that trusts local connections, so only success is asserted)
    finally:
        set_app_password(owner, "dev", dev=True)
