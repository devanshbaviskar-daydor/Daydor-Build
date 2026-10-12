"""Skeleton workflow definitions generated from the model's six flows.

Revision ID: 0010
Revises: 0009
"""
from daydor.db.migrate import run_sql_file

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0010_workflow_seed.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
