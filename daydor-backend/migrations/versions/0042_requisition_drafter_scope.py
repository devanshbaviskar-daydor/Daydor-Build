"""requisition-drafter reads job_profile and department (incremental on 0025 and 0028).

Revision ID: 0042
Revises: 0041
"""
from daydor.db.migrate import run_sql_file

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0042_requisition_drafter_scope.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
