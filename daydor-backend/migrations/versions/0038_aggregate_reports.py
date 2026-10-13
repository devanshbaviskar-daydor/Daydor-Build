"""Aggregate-only reports with small-cell suppression: the EEO-1 workforce report (finding 7).

Revision ID: 0038
Revises: 0037
"""
from daydor.db.migrate import run_sql_file

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0038_aggregate_reports.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
