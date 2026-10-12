"""Hire workflow definition version 4: extends Sprint 2's steps 1-8 through background check,
employee record creation, consent, and new-hire documents (steps 9-13). See daydor.hire.workflow.

Revision ID: 0016
Revises: 0015
"""
from daydor.db.migrate import run_sql_file

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0016_hire_workflow_v4.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
