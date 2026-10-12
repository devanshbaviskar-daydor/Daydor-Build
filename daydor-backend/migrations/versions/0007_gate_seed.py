"""Gate seed: 20 hard gates from the model, soft gates, write guards.

Revision ID: 0007
Revises: 0006
"""
from daydor.db.migrate import run_sql_file

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0007_gate_seed.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
