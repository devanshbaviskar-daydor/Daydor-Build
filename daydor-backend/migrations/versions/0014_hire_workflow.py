"""Hand-written hire workflow definition (version 2), replacing the generated skeleton for
steps 1-4 (position check through job posting). See daydor.hire.workflow.

Revision ID: 0014
Revises: 0013
"""
from daydor.db.migrate import run_sql_file

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0014_hire_workflow.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
