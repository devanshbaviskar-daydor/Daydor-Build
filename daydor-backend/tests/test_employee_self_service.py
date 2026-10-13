"""Finding 2: an employee may edit only self-service fields on their own `employee` row.

The model gave the employee role W on every `employee` column, so a signed-in employee could set
their own `is_active`, `date_of_exit`, `legal_entity_id` (payroll picks the tax jurisdiction from it),
`department_id`, `position_id` or `date_of_joining`. HR-owned fields must go through
`employee-record-writer` / HR instead. Enforced by column grants (see `grant_caps` in
model/extensions.json and migration 0024), so these tests hit the database directly.
"""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from daydor.agents.session import worker_session
from daydor.db.session import tenant_session
from daydor.model import load_model
from daydor.model.loader import ROLE_DB, WRITE

SELF_SERVICE = {"personal_address"}
HR_OWNED = ["hire_event_id", "full_name", "work_email", "employment_type", "legal_entity_id",
            "department_id", "location_id", "position_id", "state_code", "date_of_joining",
            "date_of_exit", "is_active", "date_of_birth", "aadhaar_last4"]


def as_employee(engine, org, key="report"):
    return tenant_session(engine, "tenant_employee", org.tenant_a, employee_id=org.emp[key])


@pytest.mark.parametrize("column", HR_OWNED)
def test_employee_cannot_edit_hr_owned_columns_on_their_own_row(engine, org, column):
    # A self-assignment is enough: Postgres checks the UPDATE privilege on every column in SET.
    with pytest.raises(ProgrammingError, match="permission denied"):
        with as_employee(engine, org) as conn:
            conn.execute(text(f"UPDATE employee SET {column} = {column} WHERE id = :e"),
                         {"e": org.emp["report"]})


def test_employee_cannot_deactivate_themselves_or_change_their_legal_entity(engine, org):
    with pytest.raises(ProgrammingError, match="permission denied"):
        with as_employee(engine, org) as conn:
            conn.execute(text("UPDATE employee SET is_active = false, date_of_exit = '2026-01-01', "
                              "legal_entity_id = :le WHERE id = :e"),
                         {"le": org.legal_entity_a, "e": org.emp["report"]})


def test_employee_can_still_edit_their_own_address(engine, org):
    with as_employee(engine, org) as conn:
        n = conn.execute(text("UPDATE employee SET personal_address = '7 Church Street, Bengaluru' "
                              "WHERE id = :e"), {"e": org.emp["report"]}).rowcount
        assert n == 1
        conn.execute(text("UPDATE employee SET personal_address = '12 MG Road, Bengaluru' WHERE id = :e"),
                     {"e": org.emp["report"]})


def test_employee_cannot_edit_someone_elses_address(engine, org):
    with as_employee(engine, org) as conn:
        n = conn.execute(text("UPDATE employee SET personal_address = 'Hijacked' WHERE id = :e"),
                         {"e": org.emp["peer"]}).rowcount
    assert n == 0


def test_employee_cannot_create_an_employee_row(engine, org):
    with pytest.raises(ProgrammingError, match="permission denied|null value|row-level security"):
        with as_employee(engine, org) as conn:
            conn.execute(text("INSERT INTO employee (personal_address) VALUES ('x')"))


def test_hr_and_agents_can_still_edit_hr_owned_columns(engine, org):
    with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
        assert conn.execute(text("UPDATE employee SET employment_type = employment_type WHERE id = :e"),
                            {"e": org.emp["peer"]}).rowcount == 1
    with worker_session(engine, "employee-record-writer", org.tenant_a) as conn:
        assert conn.execute(text("UPDATE employee SET is_active = is_active WHERE id = :e"),
                            {"e": org.emp["peer"]}).rowcount == 1


def test_the_model_says_the_same_thing_as_the_database():
    employee = load_model().table("employee")
    writable = {c.name for c in employee.columns if c.level("E") >= WRITE and not c.encrypted and not c.derived}
    assert writable & SELF_SERVICE == SELF_SERVICE
    assert not (writable - SELF_SERVICE - {"id", "tenant_id", "created_at", "updated_at"}), writable
    # Other roles keep their access: the cap is scoped to the employee role.
    assert {c.name for c in employee.columns if c.level("H") >= WRITE and not c.encrypted}.issuperset(HR_OWNED)
    assert ROLE_DB["E"] == "tenant_employee"


# Finding 23: workflow-owned columns on other tables. (table, column) pairs the employee role must
# not write, and the ones it authors itself and must keep.
EMPLOYEE_MUST_NOT_WRITE = [
    ("timecard", "status"), ("timecard", "approved_by_user_id"), ("timecard", "employee_id"),
    ("expense", "reimbursed_at"), ("expense", "gl_journal_entry_id"), ("expense", "approval_request_id"),
    ("expense", "policy_flags"),
    ("leave_request", "status"), ("leave_request", "fmla_designation"), ("leave_request", "approval_request_id"),
    ("benefit_election", "carrier_sent_at"),
    ("checklist", "status"), ("checklist", "employee_id"),
    ("life_event", "status"), ("life_event", "window_closes_at"),
    ("training_assignment", "completed_at"), ("training_assignment", "due_at"),
]
EMPLOYEE_AUTHORS = [
    ("expense", "category"), ("expense", "receipt_document_id"),
    ("leave_request", "leave_policy_id"), ("leave_request", "start_date"), ("leave_request", "end_date"),
    ("leave_request", "reason_detail"),
    ("benefit_election", "benefit_plan_id"), ("benefit_election", "effective_from"),
    ("life_event", "event_type"), ("life_event", "event_date"), ("life_event", "evidence_document_id"),
    ("time_punch", "punched_at"), ("consent_record", "status"),
]


def _can(engine, table, column, privilege):
    with engine.connect() as conn:
        return conn.execute(text("SELECT has_column_privilege('tenant_employee', :t, :c, :p)"),
                            {"t": f"public.{table}", "c": column, "p": privilege}).scalar_one()


@pytest.mark.parametrize("table,column", EMPLOYEE_MUST_NOT_WRITE)
def test_employee_cannot_write_workflow_owned_columns(engine, org, table, column):
    assert not _can(engine, table, column, "UPDATE"), f"{table}.{column} is employee-updatable"
    assert not _can(engine, table, column, "INSERT"), f"{table}.{column} is employee-insertable"
    # ...and the planner agrees, with no rows involved (the privilege is checked at parse time).
    with pytest.raises(ProgrammingError, match="permission denied"):
        with as_employee(engine, org) as conn:
            conn.execute(text(f"UPDATE {table} SET {column} = {column} WHERE false"))


@pytest.mark.parametrize("table,column", EMPLOYEE_AUTHORS)
def test_employee_keeps_the_columns_they_author(engine, table, column):
    assert _can(engine, table, column, "UPDATE") and _can(engine, table, column, "INSERT")


def test_agents_and_managers_keep_the_access_the_flows_need(engine):
    with engine.connect() as conn:
        def can(role, table, column):
            return conn.execute(text("SELECT has_column_privilege(:r, :t, :c, 'UPDATE')"),
                                {"r": role, "t": f"public.{table}", "c": column}).scalar_one()
        assert can("agent_runtime", "timecard", "status")
        assert can("agent_runtime", "leave_request", "status")
        assert can("tenant_hr", "checklist", "status")
