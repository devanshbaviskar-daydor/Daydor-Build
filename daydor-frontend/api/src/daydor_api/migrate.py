"""Applies this package's SQL files in order. Safe to run repeatedly."""
from __future__ import annotations

from importlib import resources

from sqlalchemy import text

from .state import get_engine


def run() -> list[str]:
    applied: list[str] = []
    files = sorted(p for p in resources.files("daydor_api").joinpath("sql").iterdir() if p.name.endswith(".sql"))
    with get_engine().begin() as conn:
        conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS citext")
        conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS api")
        conn.exec_driver_sql("CREATE TABLE IF NOT EXISTS api.schema_version (name text PRIMARY KEY, "
                             "applied_at timestamptz NOT NULL DEFAULT now())")
        for f in files:
            if conn.execute(text("SELECT 1 FROM api.schema_version WHERE name = :n"), {"n": f.name}).first():
                continue
            conn.exec_driver_sql(f.read_text())
            conn.execute(text("INSERT INTO api.schema_version (name) VALUES (:n)"), {"n": f.name})
            applied.append(f.name)
    return applied


if __name__ == "__main__":
    print("applied:", run() or "nothing new")
