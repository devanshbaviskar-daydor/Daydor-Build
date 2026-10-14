"""Phase F: adapter breakers, webhook inbox, platform health.

Revision ID: 0046
Revises: 0045
"""
from daydor.db.migrate import run_sql_file

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0046_integrations_ops.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
