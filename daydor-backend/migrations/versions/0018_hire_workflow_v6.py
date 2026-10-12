"""Hire workflow definition version 6: extends Sprint 4's steps 1-16 through app access grant
and payroll profile (steps 17-18). Step 19 (payslip) is permanently out of the hire flow's
scope -- see finding 15 / daydor.hire.workflow's module docstring.

Revision ID: 0018
Revises: 0017
"""
from daydor.db.migrate import run_sql_file

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0018_hire_workflow_v6.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
