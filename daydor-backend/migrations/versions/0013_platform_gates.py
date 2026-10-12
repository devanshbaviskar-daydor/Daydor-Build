"""Add g_requisition_budget, a platform hard gate not in the model (finding 11).

Revision ID: 0013
Revises: 0012
"""
from daydor.db.migrate import run_sql_file

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0013_platform_gates.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
