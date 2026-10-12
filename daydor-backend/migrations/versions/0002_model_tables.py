"""Business tables generated from the 82-table model (+ extensions).

Revision ID: 0002
Revises: 0001
"""
from daydor.db.migrate import run_sql_file

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0002_model_tables.sql")


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
