"""Postgres job queue, outbox, timers and business-day calendars (ADR-001).

Revision ID: 0005
Revises: 0004
"""
from daydor.db.migrate import run_sql_file

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0005_queue.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
