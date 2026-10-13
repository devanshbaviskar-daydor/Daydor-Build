"""Finding 6: Daydor ops sees only the tenants it is assigned to, enforced in app.tenant_id()."""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from daydor.db.session import tenant_session
from tests.factories import insert


def employees(engine, tenant, user, role="daydor_ops"):
    with tenant_session(engine, role, tenant, user_id=user) as conn:
        return conn.execute(text("SELECT count(*) FROM employee")).scalar_one()


@pytest.fixture
def second_ops(engine, org):
    with engine.begin() as conn:
        return insert(conn, "app_user", role="ops")


def test_an_assigned_ops_user_sees_the_tenant_and_only_that_tenant(engine, org):
    ops = org.user["ops"]
    assert employees(engine, org.tenant_a, ops) == len(org.emp)
    assert employees(engine, org.tenant_b, ops) == 0             # not assigned: the database shows nothing


def test_an_unassigned_ops_user_sees_nothing_anywhere(engine, org, second_ops):
    assert employees(engine, org.tenant_a, second_ops) == 0
    assert employees(engine, org.tenant_b, second_ops) == 0


def test_ops_with_a_tenant_but_no_user_sees_nothing(engine, org):
    assert employees(engine, org.tenant_a, None) == 0


def test_ops_without_a_tenant_is_a_platform_session_and_unaffected(engine, org):
    with tenant_session(engine, "daydor_ops") as conn:
        assert conn.execute(text("SELECT count(*) FROM app.gate_definition")).scalar_one() > 0


def test_ops_cannot_write_into_an_unassigned_tenant(engine, org, second_ops):
    with pytest.raises(DBAPIError):
        with tenant_session(engine, "daydor_ops", org.tenant_a, user_id=second_ops) as conn:
            conn.execute(text("INSERT INTO department (name) VALUES ('sneaky')"))


def test_other_roles_are_unaffected(engine, org):
    assert employees(engine, org.tenant_a, None, role="tenant_hr") == len(org.emp)
    with tenant_session(engine, "daydor_admin", org.tenant_b) as conn:
        conn.execute(text("SELECT 1"))                              # admin keeps platform-wide reach


def test_an_assignment_can_be_revoked_and_the_access_goes_with_it(engine, org, second_ops):
    with tenant_session(engine, "daydor_admin") as conn:
        conn.execute(text("INSERT INTO app.ops_tenant_assignment (user_id, tenant_id) VALUES (:u, :t)"),
                     {"u": second_ops, "t": org.tenant_a})
    assert employees(engine, org.tenant_a, second_ops) == len(org.emp)
    with tenant_session(engine, "daydor_admin") as conn:
        conn.execute(text("UPDATE app.ops_tenant_assignment SET revoked_at = now() WHERE user_id = :u"), {"u": second_ops})
    assert employees(engine, org.tenant_a, second_ops) == 0


def test_only_admin_assigns_and_nothing_is_deleted(engine, org, second_ops):
    for role in ("daydor_ops", "tenant_founder", "tenant_hr"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            with tenant_session(engine, role, None, user_id=org.user["ops"]) as conn:
                conn.execute(text("INSERT INTO app.ops_tenant_assignment (user_id, tenant_id) VALUES (:u, :t)"),
                             {"u": second_ops, "t": org.tenant_a})
    with pytest.raises(ProgrammingError, match="permission denied"):
        with tenant_session(engine, "daydor_admin") as conn:
            conn.execute(text("DELETE FROM app.ops_tenant_assignment"))
    with pytest.raises(ProgrammingError, match="permission denied"):
        with tenant_session(engine, "daydor_admin") as conn:
            conn.execute(text("UPDATE app.ops_tenant_assignment SET tenant_id = :t"), {"t": org.tenant_b})


def test_the_check_lives_in_tenant_id_so_every_policy_gets_it(engine, org, second_ops):
    with tenant_session(engine, "daydor_ops", org.tenant_a, user_id=second_ops) as conn:
        assert conn.execute(text("SELECT app.tenant_id()")).scalar_one() is None
    with tenant_session(engine, "daydor_ops", org.tenant_a, user_id=org.user["ops"]) as conn:
        assert conn.execute(text("SELECT app.tenant_id()")).scalar_one() == org.tenant_a
