"""Agent runs: the trace spine, and autonomy that holds or flags a job (Phase A of the agentic infrastructure).

Revision ID: 0040
Revises: 0039
"""
from daydor.db.migrate import run_sql_file

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0040_agent_runs.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
