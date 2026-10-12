"""Helpers for migrations: each migration executes a committed SQL file."""
from pathlib import Path

from alembic import op

SQL_DIR = Path(__file__).resolve().parents[3] / "migrations" / "sql"


def run_sql_file(name: str, as_owner: bool = True) -> None:
    sql = (SQL_DIR / name).read_text()
    # Use the raw driver cursor with no parameters, so '%' in SQL (format strings,
    # LIKE patterns) is not treated as a placeholder. Same transaction as Alembic.
    cur = op.get_bind().connection.cursor()
    if as_owner:
        cur.execute("SET ROLE daydor_schema_owner")
    cur.execute(sql)
    if as_owner:
        cur.execute("RESET ROLE")
