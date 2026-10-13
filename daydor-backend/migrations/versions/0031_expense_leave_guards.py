"""Gate guards on expense.reimbursed_at and leave_request.fmla_designation (ADR-006).

Revision ID: 0031
Revises: 0030
"""
from daydor.db.migrate import run_sql_file

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0031_expense_leave_guards.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
