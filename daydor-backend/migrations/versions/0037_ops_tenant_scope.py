"""Daydor ops sees assigned tenants only (finding 6), enforced inside app.tenant_id().

Revision ID: 0037
Revises: 0036
"""
from daydor.db.migrate import run_sql_file

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0037_ops_tenant_scope.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
