"""Exit flow support: relax final_settlement.approval_request_id to nullable, app.open_final_settlement
for its derived total_settlement, correct final_settlement.disbursed_at's gate to g_pay_disburse,
add cobra_event.notice_sent_at's g_cobra guard (finding 20).

Revision ID: 0022
Revises: 0021
"""
from daydor.db.migrate import run_sql_file

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0022_exit_gate_guards.sql", as_owner=True)


def downgrade() -> None:
    raise NotImplementedError("Forward-only: write a new migration instead.")
