"""worker_platform grants, worker-aware role functions, and the PII role-check fix (Phase 1).

Revision ID: 0027
Revises: 0026
"""
from daydor.db.migrate import run_sql_file

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0027_worker_platform.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
