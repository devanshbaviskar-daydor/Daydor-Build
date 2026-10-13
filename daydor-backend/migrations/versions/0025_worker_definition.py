"""app.worker_definition: the worker registry in the database (ADR-004, Phase 1 step 1).

Generated from registry/ by `python -m daydor.agents.roles`. Creates the worker_platform group role,
so it runs as the superuser and switches to the schema owner inside the SQL.

Revision ID: 0025
Revises: 0024
"""
from daydor.db.migrate import run_sql_file

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0025_worker_definition.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
