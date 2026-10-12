"""Hire workflow definition version 3: extends Sprint 1's steps 1-4 through screening,
interview and offer (steps 5-8). See daydor.hire.workflow.

Revision ID: 0015
Revises: 0014
"""
from daydor.db.migrate import run_sql_file

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0015_hire_workflow_v3.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
