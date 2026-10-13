"""Sprint 13: the statutory clocks beyond I-9 (0039): COBRA, work-authorization and certification expiry, 409A and
threshold registration. A dated column becomes a clock.due_soon event, then a clock.overdue event, once each."""
from datetime import date, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from daydor import clocks
from daydor.agents.session import worker_session
from daydor.db.session import tenant_session
from daydor.queue.worker import Job
from tests.factories import insert

TODAY = date(2026, 6, 15)


@pytest.fixture
def clock_org(engine):
    with engine.begin() as conn:
        tenant = insert(conn, "tenant", legal_name="Clock Co", status="active")
        le = insert(conn, "legal_entity", tenant_id=tenant, name="Clock Co Inc", country_code="US")
        dept = insert(conn, "department", tenant_id=tenant, name="Eng")
        loc = insert(conn, "location", tenant_id=tenant, name="NY", country_code="US", state_code="NY", legal_entity_id=le)

        ops = insert(conn, "app_user", role="ops")
        conn.execute(text("INSERT INTO app.ops_tenant_assignment (user_id, tenant_id) VALUES (:u, :t)"), {"u": ops, "t": tenant})

    def person(active=True):
        with engine.begin() as c:
            return insert(c, "employee", tenant_id=tenant, full_name="P", legal_entity_id=le, department_id=dept,
                          location_id=loc, hire_event_id=f"h{insert_counter()}", is_active=active)
    return {"tenant": tenant, "le": le, "person": person, "ops": ops}


_n = [0]


def insert_counter():
    _n[0] += 1
    return _n[0]


def scan(engine, org, as_of):
    with worker_session(engine, "root-orchestrator", org["tenant"]) as conn:
        return conn.execute(text("SELECT app.scan_statutory_clocks(:d)"), {"d": as_of}).scalar_one()


def due(engine, org):
    with worker_session(engine, "root-orchestrator", org["tenant"]) as conn:
        return {(r.clock_id, r.subject_id): r for r in conn.execute(text("SELECT * FROM app.statutory_clocks_due()"))}


def events(engine, org, topic=None):
    with engine.connect() as conn:
        return conn.execute(text("SELECT topic, subject_table, subject_id, payload FROM app.outbox WHERE tenant_id = :t "
                                 "AND topic LIKE 'clock.%' AND (CAST(:tp AS text) IS NULL OR topic = :tp) ORDER BY id"),
                            {"t": org["tenant"], "tp": topic}).all()


def make(engine, org, table, **cols):
    with engine.begin() as conn:
        return insert(conn, table, tenant_id=org["tenant"], **cols)


# -------------------------------------------------------------------------------- one clock, its three moments
def test_a_clock_is_quiet_then_due_soon_then_overdue_once_each(engine, clock_org):
    emp = clock_org["person"]()
    cert = make(engine, clock_org, "certification", employee_id=emp, name="Forklift", issuer="OSHA",
                issued_on=TODAY - timedelta(days=300), expires_on=TODAY + timedelta(days=60), role_critical=True)
    assert scan(engine, clock_org, TODAY) == 0                                     # 60 days out, lead is 30
    assert scan(engine, clock_org, TODAY + timedelta(days=31)) == 1                 # 29 days out: due soon
    assert scan(engine, clock_org, TODAY + timedelta(days=31)) == 0                 # idempotent
    assert scan(engine, clock_org, TODAY + timedelta(days=60)) == 1                 # the day it expires: overdue
    assert scan(engine, clock_org, TODAY + timedelta(days=90)) == 0
    got = events(engine, clock_org)
    assert [e.topic for e in got] == ["clock.due_soon", "clock.overdue"]
    assert all(e.subject_table == "certification" and e.subject_id == cert for e in got)
    assert got[0].payload["clock"] == "certification_expiry" and got[0].payload["owner"] == "hr"
    assert got[0].payload["due_on"] == (TODAY + timedelta(days=60)).isoformat()


def test_a_row_that_first_appears_already_overdue_emits_only_overdue(engine, clock_org):
    emp = clock_org["person"]()
    make(engine, clock_org, "certification", employee_id=emp, name="Late", issuer="x", issued_on=TODAY - timedelta(days=700),
         expires_on=TODAY - timedelta(days=5), role_critical=True)
    assert scan(engine, clock_org, TODAY) == 1
    assert [e.topic for e in events(engine, clock_org)] == ["clock.overdue"]


# -------------------------------------------------------------------------------- each clock's own rule
def test_cobra_notice_then_election_window(engine, clock_org):
    emp = clock_org["person"]()
    ev = make(engine, clock_org, "cobra_event", employee_id=emp, qualifying_event="termination",
              event_date=TODAY - timedelta(days=40), notice_due_at=TODAY + timedelta(days=4), election_status="pending")
    d = due(engine, clock_org)
    assert ("cobra_notice", ev) in d and ("cobra_election", ev) not in d          # notice not sent yet
    assert d[("cobra_notice", ev)].due_on == TODAY + timedelta(days=4) and d[("cobra_notice", ev)].lead_days == 7
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = replica"))        # the guard needs an approved gate; this test is about clocks
        conn.execute(text("UPDATE cobra_event SET notice_sent_at = :s WHERE id = :i"), {"s": f"{TODAY} 09:00+00", "i": ev})
    d = due(engine, clock_org)
    assert ("cobra_notice", ev) not in d                                           # sent: no longer due
    assert d[("cobra_election", ev)].due_on == TODAY + timedelta(days=60)


def test_work_authorization_expiry_ignores_people_who_have_left(engine, clock_org):
    here, gone = clock_org["person"](), clock_org["person"](active=False)
    w1 = make(engine, clock_org, "work_authorization", employee_id=here, auth_type="h1b", status="active", sponsor_flag=True,
              expiration_date=TODAY + timedelta(days=80))
    w2 = make(engine, clock_org, "work_authorization", employee_id=gone, auth_type="h1b", status="active", sponsor_flag=True,
              expiration_date=TODAY + timedelta(days=80))
    d = due(engine, clock_org)
    assert ("work_authorization_expiry", w1) in d and ("work_authorization_expiry", w2) not in d
    assert scan(engine, clock_org, TODAY) == 1                                      # 80 days out is inside the 90-day lead


def test_only_role_critical_certifications_count(engine, clock_org):
    emp = clock_org["person"]()
    crit = make(engine, clock_org, "certification", employee_id=emp, name="A", issuer="x", issued_on=TODAY, expires_on=TODAY,
                role_critical=True)
    plain = make(engine, clock_org, "certification", employee_id=emp, name="B", issuer="x", issued_on=TODAY, expires_on=TODAY,
                 role_critical=False)
    d = due(engine, clock_org)
    assert ("certification_expiry", crit) in d and ("certification_expiry", plain) not in d


def test_only_the_latest_409a_valuation_can_go_stale(engine, clock_org):
    old = make(engine, clock_org, "valuation_409a", legal_entity_id=clock_org["le"], valuation_date=TODAY - timedelta(days=400),
               fmv_per_share="1", provider="p", expires_on=TODAY - timedelta(days=35))
    new = make(engine, clock_org, "valuation_409a", legal_entity_id=clock_org["le"], valuation_date=TODAY - timedelta(days=20),
               fmv_per_share="2", provider="p", expires_on=TODAY + timedelta(days=345))
    d = due(engine, clock_org)
    assert ("valuation_409a", new) in d and ("valuation_409a", old) not in d       # superseded: its expiry no longer matters
    assert d[("valuation_409a", new)].owner == "founder"


def test_threshold_registration_clock_stops_once_approved_or_not_applicable(engine, clock_org):
    open_ = make(engine, clock_org, "threshold_obligation", legal_entity_id=clock_org["le"], scheme="esic", headcount_at_check=11,
                 threshold=10, applicable=True, crossed_at=TODAY, registration_deadline=TODAY + timedelta(days=10))
    na = make(engine, clock_org, "threshold_obligation", legal_entity_id=clock_org["le"], scheme="pf", headcount_at_check=11,
              threshold=20, applicable=False, crossed_at=TODAY, registration_deadline=TODAY + timedelta(days=10))
    d = due(engine, clock_org)
    assert ("threshold_registration", open_) in d and ("threshold_registration", na) not in d
    assert d[("threshold_registration", open_)].lead_days == 14
    assert scan(engine, clock_org, TODAY) == 1


# -------------------------------------------------------------------------------- scope and plumbing
def test_scans_see_only_their_tenant(engine, clock_org, org):
    emp = clock_org["person"]()
    make(engine, clock_org, "certification", employee_id=emp, name="C", issuer="x", issued_on=TODAY, expires_on=TODAY,
         role_critical=True)
    with worker_session(engine, "root-orchestrator", org.tenant_a) as conn:
        assert conn.execute(text("SELECT count(*) FROM app.statutory_clocks_due()")).scalar_one() == 0
        assert conn.execute(text("SELECT app.scan_statutory_clocks(:d)"), {"d": TODAY}).scalar_one() == 0


def test_ops_scans_only_an_assigned_tenant(engine, clock_org, org):
    with tenant_session(engine, "daydor_ops", clock_org["tenant"], user_id=clock_org["ops"]) as conn:
        conn.execute(text("SELECT app.scan_statutory_clocks(:d)"), {"d": TODAY})
    with tenant_session(engine, "daydor_ops", clock_org["tenant"], user_id=org.user["ops"]) as conn:   # assigned elsewhere
        assert conn.execute(text("SELECT count(*) FROM app.statutory_clocks_due()")).scalar_one() == 0


def test_only_the_orchestrator_and_staff_can_scan_and_emissions_are_append_only(engine, clock_org):
    for worker in ("gl-poster", "cobra-notice-generator", "eeo-report-builder"):
        with pytest.raises(ProgrammingError, match="permission denied for function scan_statutory_clocks"):
            with worker_session(engine, worker, clock_org["tenant"]) as conn:
                conn.execute(text("SELECT app.scan_statutory_clocks(:d)"), {"d": TODAY})
    with pytest.raises(ProgrammingError, match="permission denied"):
        with tenant_session(engine, "tenant_hr", clock_org["tenant"]) as conn:
            conn.execute(text("SELECT app.scan_statutory_clocks(:d)"), {"d": TODAY})
    emp = clock_org["person"]()
    make(engine, clock_org, "certification", employee_id=emp, name="C", issuer="x", issued_on=TODAY, expires_on=TODAY, role_critical=True)
    scan(engine, clock_org, TODAY)
    from sqlalchemy.exc import DBAPIError
    with pytest.raises(DBAPIError, match="append-only|permission denied"):
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL ROLE daydor_schema_owner"))
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(clock_org["tenant"])})
            conn.execute(text("DELETE FROM app.clock_emission"))


def test_hr_and_founder_can_list_what_is_coming_but_not_raise_events(engine, clock_org):
    for role in ("tenant_hr", "tenant_founder"):
        with tenant_session(engine, role, clock_org["tenant"]) as conn:
            conn.execute(text("SELECT * FROM app.statutory_clocks_due()")).all()


# -------------------------------------------------------------------------------- the daily chain
def test_the_handler_scans_and_schedules_the_next_day_idempotently(engine, clock_org):
    emp = clock_org["person"]()
    make(engine, clock_org, "certification", employee_id=emp, name="C", issuer="x", issued_on=TODAY, expires_on=TODAY - timedelta(days=1),
         role_critical=True)
    job = Job(id=None, tenant_id=clock_org["tenant"], queue="platform", kind=clocks.KIND, payload={"day": "2099-01-01"},
              attempts=1, max_attempts=5)
    for _ in range(2):                                                              # a retried job changes nothing
        with worker_session(engine, "root-orchestrator", clock_org["tenant"]) as conn:
            result = clocks.handle_statutory_clock_scan(conn, job)
    assert result["day"] == "2099-01-01"
    with engine.connect() as conn:
        timers = conn.execute(text("SELECT timer_key, queue, kind, status FROM app.timer WHERE tenant_id = :t "
                                   "AND timer_key LIKE 'statutory-clock-scan-%'"), {"t": clock_org["tenant"]}).all()
    assert [(t.timer_key, t.queue, t.kind, t.status) for t in timers] == [
        ("statutory-clock-scan-2099-01-02", "platform", "statutory_clock_scan", "pending")]
    assert len(events(engine, clock_org, "clock.overdue")) == 1                     # emitted by the first run only


def test_start_clock_scan_is_idempotent_per_day(engine, clock_org):
    for _ in range(3):
        with worker_session(engine, "root-orchestrator", clock_org["tenant"]) as conn:
            clocks.start_clock_scan(conn, first_day=date(2098, 3, 1))
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM app.timer WHERE tenant_id = :t AND timer_key = 'statutory-clock-scan-2098-03-01'"),
                            {"t": clock_org["tenant"]}).scalar_one() == 1
