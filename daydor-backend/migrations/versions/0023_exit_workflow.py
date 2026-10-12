"""Exit flow workflow definition v2 (Sprints 10-11, steps 1-14): see
daydor.exit.workflow.EXIT_DEFINITION's module docstring for its departures from the hire flow's
gate-placement conventions.

Revision ID: 0023
Revises: 0022
"""
from daydor.db.migrate import run_sql_file

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0023_exit_workflow.sql", as_owner=True)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
