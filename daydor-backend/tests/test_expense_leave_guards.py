"""ADR-006: the database refuses expense.reimbursed_at and leave_request.fmla_designation without an
approved g_expense / g_fmla request for the same row (finding 23 follow-up). No service writes either
column yet; these tests write them directly, as whatever eventually will."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from daydor.agents.session import worker_session
from daydor.db.session import tenant_session
from daydor.gates.hard import request_approval, resolve
from tests.factories import insert


@pytest.fixture
def expense_id(engine, org):
    with engine.begin() as conn:
        return insert(conn, "expense", tenant_id=org.tenant_a, employee_id=org.emp["report"])


@pytest.fixture
def leave_id(engine, org):
    with engine.begin() as conn:
        policy = insert(conn, "leave_policy", tenant_id=org.tenant_a, legal_entity_id=org.legal_entity_a,
                        leave_type="fmla")
        return insert(conn, "leave_request", tenant_id=org.tenant_a, employee_id=org.emp["report"],
                      leave_policy_id=policy)


def _approve(engine, org, gate, table, row, role, user):
    with tenant_session(engine, "agent_fin", org.tenant_a) as conn:
        approval = request_approval(conn, gate, table, row)
    with tenant_session(engine, role, org.tenant_a, user_id=org.user[user]) as conn:
        assert resolve(conn, approval, "approved") == "approved"
    return approval


def test_the_guards_are_registered(engine):
    with engine.connect() as conn:
        rows = {(r.table_name, r.guard_column): list(r.gate_ids)
                for r in conn.execute(text("SELECT * FROM app.gate_guard"))}
    assert rows[("expense", "reimbursed_at")] == ["g_expense"]
    assert rows[("leave_request", "fmla_designation")] == ["g_fmla"]


def test_reimbursement_is_refused_without_an_approved_g_expense(engine, org, expense_id):
    with pytest.raises(DBAPIError, match="needs an approved g_expense gate"):
        with tenant_session(engine, "agent_fin", org.tenant_a) as conn:
            conn.execute(text("UPDATE expense SET reimbursed_at = now() WHERE id = :e"), {"e": expense_id})
    with tenant_session(engine, "agent_fin", org.tenant_a) as conn:
        pending = request_approval(conn, "g_expense", "expense", expense_id)
    with pytest.raises(DBAPIError, match="needs an approved g_expense gate"):        # still pending
        with tenant_session(engine, "agent_fin", org.tenant_a) as conn:
            conn.execute(text("UPDATE expense SET approval_request_id = :a, reimbursed_at = now() WHERE id = :e"),
                         {"a": pending, "e": expense_id})


def test_reimbursement_succeeds_with_the_approved_gate_for_that_row_only(engine, org, expense_id):
    with engine.begin() as conn:
        other = insert(conn, "expense", tenant_id=org.tenant_a, employee_id=org.emp["peer"])
    wrong_row = _approve(engine, org, "g_expense", "expense", other, "tenant_manager", "manager")
    with pytest.raises(DBAPIError, match="needs an approved g_expense gate"):
        with tenant_session(engine, "agent_fin", org.tenant_a) as conn:
            conn.execute(text("UPDATE expense SET approval_request_id = :a, reimbursed_at = now() WHERE id = :e"),
                         {"a": wrong_row, "e": expense_id})
    approval = _approve(engine, org, "g_expense", "expense", expense_id, "tenant_manager", "manager")
    with tenant_session(engine, "agent_fin", org.tenant_a) as conn:
        conn.execute(text("UPDATE expense SET approval_request_id = :a, reimbursed_at = now() WHERE id = :e"),
                     {"a": approval, "e": expense_id})
    with pytest.raises(DBAPIError, match="final once set"):
        with tenant_session(engine, "agent_fin", org.tenant_a) as conn:
            conn.execute(text("UPDATE expense SET reimbursed_at = now() + interval '1 day' WHERE id = :e"),
                         {"e": expense_id})


def test_fmla_designation_is_refused_without_an_approved_g_fmla(engine, org, leave_id):
    """No application role can write this C4 column today (HR reads it, the employee's write is capped by
    finding 23), so the guard is exercised through the table owner: the trigger applies to every writer."""
    def update(approval=None):
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL ROLE daydor_schema_owner"))
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(org.tenant_a)})
            conn.execute(text("UPDATE leave_request SET approval_request_id = :a, fmla_designation = 'eligible' "
                              "WHERE id = :l"), {"a": approval, "l": leave_id})
    with pytest.raises(DBAPIError, match="needs an approved g_fmla gate"):
        update()
    with tenant_session(engine, "agent_time", org.tenant_a) as conn:
        pending = request_approval(conn, "g_fmla", "leave_request", leave_id)
    with pytest.raises(DBAPIError, match="needs an approved g_fmla gate"):            # still pending
        update(pending)
    with tenant_session(engine, "tenant_hr", org.tenant_a, user_id=org.user["hr_admin"]) as conn:
        resolve(conn, pending, "approved")
    update(pending)


def test_leave_status_is_not_guarded_so_requests_still_start_and_move(engine, org, leave_id):
    with tenant_session(engine, "agent_time", org.tenant_a) as conn:
        conn.execute(text("UPDATE leave_request SET status = 'approved' WHERE id = :l"), {"l": leave_id})


def test_no_worker_holds_either_guarded_column(engine, org, expense_id, leave_id):
    """Nobody reimburses yet, and the model gives agents no write on fmla_designation, so no worker role
    holds either column, even with an approved gate for the row."""
    approval = _approve(engine, org, "g_expense", "expense", expense_id, "tenant_manager", "manager")
    with pytest.raises(DBAPIError, match="permission denied"):
        with worker_session(engine, "expense-approval-router", org.tenant_a) as conn:
            conn.execute(text("UPDATE expense SET approval_request_id = :a, reimbursed_at = now() WHERE id = :e"),
                         {"a": approval, "e": expense_id})
    for worker in ("fmla-eligibility-checker", "leave-request-processor", "leave-return-coordinator"):
        with pytest.raises(DBAPIError, match="permission denied"):
            with worker_session(engine, worker, org.tenant_a) as conn:
                conn.execute(text("UPDATE leave_request SET fmla_designation = 'eligible' WHERE id = :l"),
                             {"l": leave_id})
