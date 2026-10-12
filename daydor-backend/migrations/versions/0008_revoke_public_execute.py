"""Fix: revoke PUBLIC execute on app functions (per-schema default revoke was a no-op).

Revision ID: 0008
Revises: 0007
"""
from daydor.db.migrate import run_sql_file

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0008_revoke_public_execute.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
