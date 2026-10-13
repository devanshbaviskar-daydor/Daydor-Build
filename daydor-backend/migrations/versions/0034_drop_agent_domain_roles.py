"""Drop the agent_<domain> roles; agent work runs as per-worker roles.

Revision ID: 0034
Revises: 0033
"""
from daydor.db.migrate import run_sql_file

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0034_drop_agent_domain_roles.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
