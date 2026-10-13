"""Shadow outcome view, labelled-example store, training policy, calibrations and the enforce guard (Sprint 13).

Revision ID: 0036
Revises: 0035
"""
from daydor.db.migrate import run_sql_file

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0036_laya_calibration.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
