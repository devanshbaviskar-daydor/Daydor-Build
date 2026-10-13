"""Phase C: worker rollout, eval results, tenant AI budgets and a circuit breaker.

Revision ID: 0043
Revises: 0042
"""
from daydor.db.migrate import run_sql_file

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0043_agent_safety_ops.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
