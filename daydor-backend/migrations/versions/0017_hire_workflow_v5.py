"""Hire workflow definition version 5: extends Sprint 3's steps 1-13 through work
authorization, onboarding checklist and identity provisioning (steps 14-16). See
daydor.hire.workflow.

Revision ID: 0017
Revises: 0016
"""
from daydor.db.migrate import run_sql_file

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0017_hire_workflow_v5.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
