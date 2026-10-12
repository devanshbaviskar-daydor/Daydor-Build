"""Platform foundation: roles, app schema, session context, person scope.

Revision ID: 0001
Revises:
"""
from daydor.db.migrate import run_sql_file

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0001_platform.sql", as_owner=False)  # creates roles; switches role itself


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
