"""Hire flow: relax employee's PII columns to nullable (creation precedes consent and
encryption), add an idempotency key for employment_record.

Revision ID: 0012
Revises: 0011
"""
from daydor.db.migrate import run_sql_file

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0012_hire.sql", as_owner=True)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
