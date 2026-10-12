"""Access control: tenant isolation, person scope, column grants, masking, append-only.

test_column_grants_match_model is the generated matrix: it compares every column privilege in
the live database with what the artifact's access engine says, for all 82 tables x 10 roles.
"""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from daydor.db.session import tenant_session
from daydor.model import load_model
from daydor.model.ddl import SYSTEM_MANAGED
from daydor.model.loader import READ, ROLE_DB, WRITE


def visible_employees(engine, role, tenant, **ctx):
    with tenant_session(engine, role, tenant, **ctx) as conn:
        return set(conn.execute(text("SELECT id FROM employee")).scalars())


def test_tenant_isolation(engine, org):
    seen = visible_employees(engine, "tenant_hr", org.tenant_a)
    assert seen == set(org.emp.values())
    assert org.emp_b not in seen


def test_no_tenant_context_sees_nothing(engine, org):
    assert visible_employees(engine, "tenant_hr", None) == set()


def test_employee_sees_only_self(engine, org):
    seen = visible_employees(engine, "tenant_employee", org.tenant_a, employee_id=org.emp["report"])
    assert seen == {org.emp["report"]}


def test_manager_sees_subtree_not_peers(engine, org):
    seen = visible_employees(engine, "tenant_manager", org.tenant_a, employee_id=org.emp["manager"])
    assert seen == {org.emp["manager"], org.emp["report"], org.emp["deep_report"]}
    assert org.emp["peer"] not in seen and org.emp["founder"] not in seen


def test_reporting_closure_follows_reporting_changes(engine, org):
    # Move deep_report under peer; the manager loses sight of them, peer gains it.
    with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
        conn.execute(text("UPDATE reporting_line SET manager_employee_id = :p WHERE employee_id = :d"),
                     {"p": org.emp["peer"], "d": org.emp["deep_report"]})
    try:
        assert org.emp["deep_report"] not in visible_employees(
            engine, "tenant_manager", org.tenant_a, employee_id=org.emp["manager"])
    finally:
        with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
            conn.execute(text("UPDATE reporting_line SET manager_employee_id = :r WHERE employee_id = :d"),
                         {"r": org.emp["report"], "d": org.emp["deep_report"]})


def test_it_admin_cannot_read_restricted_pii(engine, org):
    with pytest.raises(ProgrammingError, match="permission denied"):
        with tenant_session(engine, "tenant_it", org.tenant_a) as conn:
            conn.execute(text("SELECT date_of_birth FROM employee"))


@pytest.mark.parametrize("role", ["tenant_hr", "tenant_payroll", "tenant_founder", "agent_pay"])
def test_encrypted_columns_never_granted(engine, org, role):
    with pytest.raises(ProgrammingError, match="permission denied"):
        with tenant_session(engine, role, org.tenant_a) as conn:
            conn.execute(text("SELECT pan_encrypted FROM employee"))


def test_founder_sees_restricted_pii_masked(engine, org):
    with tenant_session(engine, "tenant_founder", org.tenant_a) as conn:
        row = conn.execute(text("SELECT full_name, personal_address, date_of_birth, pan_encrypted_on_file "
                                "FROM employee_masked WHERE id = :e"), {"e": org.emp["report"]}).one()
    assert row.full_name == "Report"
    assert row.personal_address == "****luru"
    assert row.date_of_birth is None
    assert row.pan_encrypted_on_file is True


def test_hr_reads_restricted_pii_from_base_table(engine, org):
    # HR has full access to C3, so it reads the base table and needs no masked view.
    with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
        addr = conn.execute(text("SELECT personal_address FROM employee WHERE id = :e"),
                            {"e": org.emp["report"]}).scalar_one()
    assert addr == "12 MG Road, Bengaluru"


def test_masked_view_respects_tenant_isolation(engine, org):
    with tenant_session(engine, "tenant_founder", org.tenant_b) as conn:
        ids = set(conn.execute(text("SELECT id FROM employee_masked")).scalars())
    assert ids == {org.emp_b}


def test_no_role_can_delete(engine, org):
    with pytest.raises(ProgrammingError, match="permission denied"):
        with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
            conn.execute(text("DELETE FROM employee WHERE id = :e"), {"e": org.emp["peer"]})


def test_tenant_id_cannot_be_set_explicitly(engine, org):
    # tenant_id is never writable: it always comes from the session, so a caller cannot
    # write into another tenant even if it knows the tenant's id.
    with pytest.raises(ProgrammingError, match="permission denied"):
        with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
            conn.execute(text("INSERT INTO department (tenant_id, name, cost_center_code) "
                              "VALUES (:t, 'Sneaky', 'CC1')"), {"t": org.tenant_b})


def test_cannot_update_another_tenants_rows(engine, org):
    with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
        n = conn.execute(text("UPDATE employee SET full_name = 'Hijacked' WHERE id = :e"),
                         {"e": org.emp_b}).rowcount
    assert n == 0


def test_tenant_id_defaults_from_session(engine, org):
    with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
        t = conn.execute(text("INSERT INTO department (name, cost_center_code) VALUES ('Design', 'CC2') RETURNING tenant_id")).scalar_one()
    assert t == org.tenant_a


def test_audit_log_is_append_only(engine, org):
    with tenant_session(engine, "agent_hr", org.tenant_a) as conn:
        aid = conn.execute(text("INSERT INTO audit_log (actor_kind, event_type, subject_table, subject_id, "
                                "occurred_at) VALUES ('agent', 'test', 'employee', :e, now()) RETURNING id"),
                           {"e": org.emp["report"]}).scalar_one()
    with pytest.raises(ProgrammingError, match="permission denied"):
        with tenant_session(engine, "agent_hr", org.tenant_a) as conn:
            conn.execute(text("UPDATE audit_log SET event_type = 'tampered' WHERE id = :a"), {"a": aid})


def test_directory_shows_colleagues_to_employees(engine, org):
    with tenant_session(engine, "tenant_employee", org.tenant_a, employee_id=org.emp["report"]) as conn:
        names = set(conn.execute(text("SELECT full_name FROM employee_directory")).scalars())
    assert {"Founder", "Peer", "Report"} <= names and "Other Co Person" not in names


def _actual_column_privileges(engine) -> set[tuple[str, str, str, str]]:
    sql = text("""
        SELECT c.relname, a.attname, r.rolname, x.privilege_type
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
        CROSS JOIN LATERAL aclexplode(a.attacl) x
        JOIN pg_roles r ON r.oid = x.grantee
        WHERE c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
    """)
    with engine.connect() as conn:
        return {tuple(r) for r in conn.execute(sql)}


def test_column_grants_match_model(engine, org):
    model = load_model()
    expected = set()
    for t in model.tables:
        for c in t.columns:
            if c.encrypted:
                continue
            for letter, db in ROLE_DB.items():
                lvl = c.level(letter)
                if lvl >= READ:
                    expected.add((t.id, c.name, db, "SELECT"))
                if lvl >= WRITE and c.name not in SYSTEM_MANAGED and not c.derived:
                    expected.add((t.id, c.name, db, "INSERT"))
                    if not t.append_only:
                        expected.add((t.id, c.name, db, "UPDATE"))
    model_roles = set(ROLE_DB.values())
    actual = {p for p in _actual_column_privileges(engine) if p[2] in model_roles}
    missing, extra = expected - actual, actual - expected
    assert not missing, f"{len(missing)} grants missing, e.g. {sorted(missing)[:5]}"
    assert not extra, f"{len(extra)} unexpected grants, e.g. {sorted(extra)[:5]}"
    assert len(expected) > 3000


def test_no_app_function_is_executable_by_public(engine, org):
    with engine.connect() as conn:
        public = conn.execute(text("""
            SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'app'
              AND (p.proacl IS NULL OR EXISTS (SELECT 1 FROM aclexplode(p.proacl) a WHERE a.grantee = 0))
        """)).scalars().all()
    assert public == []


def test_tenant_roles_cannot_drive_the_queue(engine, org):
    with pytest.raises(ProgrammingError, match="permission denied for function claim_jobs"):
        with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
            conn.execute(text("SELECT * FROM app.claim_jobs('any', 'me')"))
