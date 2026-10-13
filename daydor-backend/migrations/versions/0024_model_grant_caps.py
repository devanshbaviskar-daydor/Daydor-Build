"""Finding 2: narrow the employee role's write access on `employee` to self-service fields.

Generated REVOKEs from `grant_caps` in model/extensions.json (`python -m daydor.model.ddl`).

Revision ID: 0024
Revises: 0023
"""
from daydor.db.migrate import run_sql_file

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0024_model_grant_caps.sql", as_owner=True)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
