"""payroll-run-builder support: SECURITY DEFINER functions for payroll_run/payslip's `derived`
total columns, which carry no role grant at all (finding 19).

Revision ID: 0021
Revises: 0020
"""
from daydor.db.migrate import run_sql_file

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0021_payroll_run_functions.sql", as_owner=True)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
