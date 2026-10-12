"""Widen statutory_rate_rule.employee_rate/employer_rate from numeric(14,2) to numeric(8,6):
the generated 2dp precision silently rounds real statutory rate fractions (finding 18).

Revision ID: 0020
Revises: 0019
"""
from daydor.db.migrate import run_sql_file

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0020_statutory_rate_precision.sql", as_owner=True)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
