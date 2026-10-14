"""Phase E: the front door (feature switch, turn log, gate, record).

Revision ID: 0045
Revises: 0044
"""
from daydor.db.migrate import run_sql_file

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0045_front_door.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
