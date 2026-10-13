"""payroll-run-builder's scope narrows after the run_builder split (incremental on 0025 and 0028).

Revision ID: 0035
Revises: 0034
"""
from daydor.db.migrate import run_sql_file

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0035_payroll_run_builder_narrowed.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
