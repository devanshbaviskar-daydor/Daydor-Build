"""LLM runtime support: review that blocks the next step, proposals and model-call records (Phase B).

Revision ID: 0041
Revises: 0040
"""
from daydor.db.migrate import run_sql_file

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0041_agent_harness.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
