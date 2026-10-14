"""Phase D: approval escalation, notifications, inbox, tenant worker controls.

Revision ID: 0044
Revises: 0043
"""
from daydor.db.migrate import run_sql_file

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0044_human_surface.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
