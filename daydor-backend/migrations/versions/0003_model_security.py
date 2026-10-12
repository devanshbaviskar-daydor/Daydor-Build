"""Row-level security, column grants and masked views generated from the model.

Revision ID: 0003
Revises: 0002
"""
from daydor.db.migrate import run_sql_file

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0003_model_security.sql")


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
