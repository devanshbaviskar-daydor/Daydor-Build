"""app.worker_tenant_policy and the fail-closed worker check (ADR-004, Phase 1 step 2).

Revision ID: 0026
Revises: 0025
"""
from daydor.db.migrate import run_sql_file

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0026_worker_tenant_policy.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
