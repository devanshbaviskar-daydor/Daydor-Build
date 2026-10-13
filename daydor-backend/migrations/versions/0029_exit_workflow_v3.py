"""Exit workflow version 3 (one close-out step per worker), inserted inactive.

Revision ID: 0029
Revises: 0028
"""
from daydor.db.migrate import run_sql_file

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0029_exit_workflow_v3.sql", as_owner=True)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
