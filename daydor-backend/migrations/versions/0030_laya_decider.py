"""Laya as the soft-gate engine: engine and checkpoint columns, calibration required to enforce (ADR-005).

Revision ID: 0030
Revises: 0029
"""
from daydor.db.migrate import run_sql_file

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0030_laya_decider.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
