"""Gate service: registry, approval enforcement, write guards, soft-gate log.

Revision ID: 0006
Revises: 0005
"""
from daydor.db.migrate import run_sql_file

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0006_gates.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
