"""Derived structures: reporting closure maintenance and employee directory.

Revision ID: 0004
Revises: 0003
"""
from daydor.db.migrate import run_sql_file

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0004_derived.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
