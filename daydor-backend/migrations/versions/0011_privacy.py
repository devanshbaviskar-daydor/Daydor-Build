"""Privacy services: app.encrypt_pii / app.decrypt_pii, the PII and purpose registries.

Revision ID: 0011
Revises: 0010
"""
from daydor.db.migrate import run_sql_file

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0011_privacy.sql", as_owner=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
