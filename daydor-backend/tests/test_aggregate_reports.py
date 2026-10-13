"""Finding 7: aggregate-only access. Counts of fewer than five people are withheld, raw rows are never readable."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from daydor.agents.session import worker_session
from daydor.db.session import tenant_session
from tests.factories import insert


@pytest.fixture
def eeo_org(engine):
    """A tenant of its own: engineers 6 + 5 + 2 + 1 by (race, gender) and 3 analysts, plus one inactive engineer."""
    with engine.begin() as conn:
        tenant = insert(conn, "tenant", legal_name="Counting Co", status="active")
        le = insert(conn, "legal_entity", tenant_id=tenant, name="Counting Co", country_code="US")
        dept = insert(conn, "department", tenant_id=tenant, name="Eng")
        loc = insert(conn, "location", tenant_id=tenant, name="NY", country_code="US", state_code="NY", legal_entity_id=le)
        eng = insert(conn, "job_profile", tenant_id=tenant, title="Engineer", job_family="Professionals", level="L3",
                     flsa_default="exempt", description="x")
        ana = insert(conn, "job_profile", tenant_id=tenant, title="Analyst", job_family="Technicians", level="L2",
                     flsa_default="exempt", description="x")
        n = 0

        def person(profile, race, gender, active=True):
            nonlocal n
            n += 1
            e = insert(conn, "employee", tenant_id=tenant, full_name=f"P{n}", legal_entity_id=le, department_id=dept,
                       location_id=loc, hire_event_id=f"h{n}", is_active=active)
            insert(conn, "employment_record", tenant_id=tenant, employee_id=e, effective_from="2025-01-01",
                   job_profile_id=profile, fte="1.0", ctc_annual="100", basic_da_monthly="1", tax_regime_election="new",
                   flsa_status="exempt")
            insert(conn, "self_identification", tenant_id=tenant, employee_id=e, race_ethnicity=race, gender=gender,
                   veteran_status="no", disability_status="no", collection_context="voluntary",
                   collected_at="2026-01-01")
        for _ in range(6): person(eng, "asian", "female")
        for _ in range(5): person(eng, "white", "male")
        for _ in range(2): person(eng, "black", "female")
        person(eng, "hispanic", "male")
        person(eng, "asian", "female", active=False)               # left the company: not counted
        for _ in range(3): person(ana, "white", "female")
        ops = insert(conn, "app_user", role="ops")
        conn.execute(text("INSERT INTO app.ops_tenant_assignment (user_id, tenant_id) VALUES (:u, :t)"), {"u": ops, "t": tenant})
    return {"tenant": tenant, "ops": ops}


def report(engine, eeo_org, role, **kw):
    with tenant_session(engine, role, eeo_org["tenant"], user_id=eeo_org["ops"] if role == "daydor_ops" else None) as conn:
        rows = conn.execute(text("SELECT * FROM app.eeo1_report(" + (":m" if "p_min" in kw else "") + ")"),
                            {"m": kw["p_min"]} if "p_min" in kw else {}).all()
    return {(r.job_family, r.race_ethnicity, r.gender): (r.employees, r.suppressed) for r in rows}


def test_cells_of_five_or_more_are_counted_and_smaller_ones_are_withheld(engine, eeo_org):
    got = report(engine, eeo_org, "tenant_hr")
    assert got[("Professionals", "asian", "female")] == (6, False)          # the inactive person is not counted
    assert got[("Professionals", "white", "male")] == (5, False)            # exactly the minimum
    assert got[("Professionals", "black", "female")] == (None, True)        # 2 people
    assert got[("Professionals", "hispanic", "male")] == (None, True)       # 1 person
    assert got[("Technicians", "white", "female")] == (None, True)          # 3 people
    assert all(count is None for count, hidden in got.values() if hidden) and all(hidden or count >= 5 for count, hidden in got.values())


def test_the_minimum_cannot_be_lowered(engine, eeo_org):
    assert report(engine, eeo_org, "tenant_hr", p_min=1) == report(engine, eeo_org, "tenant_hr")
    assert report(engine, eeo_org, "tenant_hr", p_min=0)[("Professionals", "black", "female")] == (None, True)
    # ... but it can be raised
    assert report(engine, eeo_org, "tenant_hr", p_min=6)[("Professionals", "white", "male")] == (None, True)


def test_the_report_returns_no_totals_so_a_withheld_cell_cannot_be_recovered(engine, eeo_org):
    with tenant_session(engine, "tenant_hr", eeo_org["tenant"]) as conn:
        cols = [c for c in conn.execute(text("SELECT * FROM app.eeo1_report()")).keys()]
    assert cols == ["job_family", "race_ethnicity", "gender", "employees", "suppressed"]


@pytest.mark.parametrize("role", ["tenant_founder", "tenant_hr", "daydor_ops", "external_auditor"])
def test_the_aggregate_only_roles_can_run_it(engine, eeo_org, role):
    assert report(engine, eeo_org, role)[("Professionals", "asian", "female")] == (6, False)


@pytest.mark.parametrize("role", ["tenant_payroll", "tenant_it", "tenant_manager", "tenant_employee"])
def test_other_roles_cannot(engine, eeo_org, role):
    with pytest.raises(ProgrammingError, match="permission denied for function eeo1_report"):
        with tenant_session(engine, role, eeo_org["tenant"]) as conn:
            conn.execute(text("SELECT * FROM app.eeo1_report()"))


@pytest.mark.parametrize("role", ["tenant_founder", "tenant_hr", "daydor_ops", "external_auditor", "tenant_payroll"])
def test_nobody_but_the_employee_can_read_the_rows_or_the_columns(engine, eeo_org, role):
    with pytest.raises(ProgrammingError, match="permission denied"):
        with tenant_session(engine, role, eeo_org["tenant"], user_id=eeo_org["ops"]) as conn:
            conn.execute(text("SELECT race_ethnicity FROM self_identification"))


def test_the_report_sees_only_the_sessions_tenant(engine, eeo_org, org):
    with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
        assert conn.execute(text("SELECT count(*) FROM app.eeo1_report()")).scalar_one() == 0
    assert report(engine, eeo_org, "tenant_hr")                          # and the populated tenant does show


def test_ops_sees_the_report_only_for_an_assigned_tenant(engine, eeo_org, org):
    with tenant_session(engine, "daydor_ops", eeo_org["tenant"], user_id=org.user["ops"]) as conn:     # assigned to tenant A only
        assert conn.execute(text("SELECT count(*) FROM app.eeo1_report()")).scalar_one() == 0


def test_the_eeo_report_builder_worker_can_run_it_but_has_no_column_grant(engine, eeo_org):
    with worker_session(engine, "eeo-report-builder", eeo_org["tenant"]) as conn:
        assert conn.execute(text("SELECT count(*) FROM app.eeo1_report()")).scalar_one() > 0
    with pytest.raises(ProgrammingError, match="permission denied"):
        with worker_session(engine, "eeo-report-builder", eeo_org["tenant"]) as conn:
            conn.execute(text("SELECT gender FROM self_identification"))
    with pytest.raises(ProgrammingError, match="permission denied for function eeo1_report"):
        with worker_session(engine, "gl-poster", eeo_org["tenant"]) as conn:
            conn.execute(text("SELECT * FROM app.eeo1_report()"))
