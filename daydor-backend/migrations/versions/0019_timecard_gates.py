"""Add g_timecard, g_expense (finding 9) and the 'timekeeping' queue's own gate.resolved
subscription.

Revision ID: 0019
Revises: 0018
"""
from daydor.db.migrate import run_sql_file

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0019_timecard_gates.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
