"""Activate exit workflow version 3 now that the queue runner registers its handlers.

Revision ID: 0033
Revises: 0032
"""
from daydor.db.migrate import run_sql_file

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0033_activate_exit_v3.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
