"""gl-poster: posts a payroll run's summary journal entry to the general ledger, gated by
`g_close` -- the same "create the row, then gate the guarded column" shape
`daydor.payroll.disbursement` uses for `g_pay_disburse`, because `app.enforce_gate_guard`
(migrations/sql/0006_gates.sql) checks the approval's `subject_id` against the row's own,
already-allocated id.

Illustrative single-line posting (debit payroll expense, credit cash, net amount): a real chart of
accounts would post separate lines for gross expense, statutory withholding liabilities and net
cash settlement, each potentially needing its own approval under this same guard. One line is
enough to prove the gate, not a complete general ledger integration.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, text

from daydor.adapters.gl import FakeGLAdapter, GLAdapter, JournalEntryRequest
from daydor.gates.hard import request_approval

DEFAULT_COST_CENTER = "CC-DEFAULT"


def open_journal_entry(conn: Connection, *, payroll_run_id: UUID) -> UUID:
    """Idempotent on (source_table, source_id). Leaves posted_at NULL."""
    existing = conn.execute(
        text("SELECT id FROM gl_journal_entry WHERE source_table = 'payroll_run' "
             "AND source_id = :r"), {"r": payroll_run_id}).scalar_one_or_none()
    if existing is not None:
        return existing

    run = conn.execute(
        text("SELECT legal_entity_id, period_end, net_total FROM payroll_run WHERE id = :r"),
        {"r": payroll_run_id}).one()
    period = run.period_end.strftime("%Y-%m")

    return conn.execute(
        text("INSERT INTO gl_journal_entry (legal_entity_id, source_table, source_id, period, "
             "cost_center_code, debit_account, credit_account, amount) VALUES "
             "(:le, 'payroll_run', :r, :p, :cc, 'payroll_expense', 'cash', :a) RETURNING id"),
        {"le": run.legal_entity_id, "r": payroll_run_id, "p": period, "cc": DEFAULT_COST_CENTER,
         "a": run.net_total}).scalar_one()


def request_gl_close_approval(conn: Connection, *, gl_journal_entry_id: UUID) -> UUID:
    """Idempotent via request_approval's own idempotency key."""
    return request_approval(conn, "g_close", "gl_journal_entry", gl_journal_entry_id)


def post_journal_entry(conn: Connection, adapter: GLAdapter | None = None, *,
                       gl_journal_entry_id: UUID, approval_request_id: UUID) -> None:
    """Raises (via app.enforce_gate_guard, not a Python-side check) if approval_request_id isn't
    an approved g_close request for this exact row."""
    adapter = adapter or FakeGLAdapter()
    row = conn.execute(
        text("SELECT debit_account, credit_account, amount FROM gl_journal_entry WHERE id = :r"),
        {"r": gl_journal_entry_id}).one()
    adapter.post(JournalEntryRequest(debit_account=row.debit_account,
                                     credit_account=row.credit_account, amount=row.amount))
    conn.execute(
        text("UPDATE gl_journal_entry SET approval_request_id = :a, posted_at = now() "
             "WHERE id = :r"), {"a": approval_request_id, "r": gl_journal_entry_id})
