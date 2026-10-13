"""The committed SQL and the live schema must match the model."""
from pathlib import Path

from sqlalchemy import text

from daydor.model import load_model
from daydor.model.ddl import (generate_grant_caps_sql, generate_security_sql, generate_tables_sql,
                              physical_type)

SQL = Path(__file__).resolve().parents[1] / "migrations" / "sql"


def test_committed_sql_matches_model():
    assert (SQL / "0002_model_tables.sql").read_text() == generate_tables_sql(), \
        "model changed: regenerate with `python -m daydor.model.ddl` and add a migration"
    assert (SQL / "0003_model_security.sql").read_text() == generate_security_sql()
    assert (SQL / "0024_model_grant_caps.sql").read_text() == generate_grant_caps_sql()


def test_live_schema_matches_model(engine):
    with engine.connect() as conn:
        live = {(r.table_name, r.column_name): r.udt_name for r in conn.execute(text(
            "SELECT table_name, column_name, udt_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name IN "
            "(SELECT tablename FROM pg_tables WHERE schemaname = 'public')"))}
    udt = {"uuid": "uuid", "text": "text", "jsonb": "jsonb", "numeric(14,2)": "numeric", "date": "date",
           "timestamptz": "timestamptz", "boolean": "bool", "integer": "int4", "bytea": "bytea",
           "citext": "citext"}
    expected = {(t.id, c.name): udt[physical_type(c)] for t in load_model().tables for c in t.columns}
    live = {k: v for k, v in live.items() if k[0] != "alembic_version"}
    assert set(expected) == set(live), (set(expected) ^ set(live))
    assert {k: v for k, v in live.items() if expected[k] != v} == {}


def test_model_has_82_tables():
    assert len(load_model().tables) == 82
