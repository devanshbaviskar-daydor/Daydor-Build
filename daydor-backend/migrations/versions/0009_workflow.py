"""State machines: definitions, instances, append-only transition log.

Revision ID: 0009
Revises: 0008
"""
from daydor.db.migrate import run_sql_file

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0009_workflow.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
