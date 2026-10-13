"""One NOLOGIN role per worker with derived column grants (ADR-004, Phase 1 steps 3 and 4).

Generated from registry/ and the model by `python -m daydor.agents.roles`. Also seeds the worker
roles into the PII registries. Creates roles, so it runs as the superuser and switches to the schema
owner inside the SQL.

Revision ID: 0028
Revises: 0027
"""
from daydor.db.migrate import run_sql_file

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0028_worker_roles.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
