"""Statutory clocks beyond the I-9 timer: COBRA, work-authorization and certification expiry, 409A, thresholds.

Revision ID: 0039
Revises: 0038
"""
from daydor.db.migrate import run_sql_file

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0039_statutory_clocks.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
