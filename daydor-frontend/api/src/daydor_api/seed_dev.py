"""Seeds a demo tenant ("Acme Technologies", Bengaluru) and one sign-in per people-facing role.

Platform records (tenant, legal entity, departments, locations, users) are created the way Daydor
ops provisions a tenant. Reference data (job profiles, comp bands, positions) is entered as
`tenant_hr` through a real tenant session, the way the backend's plan says demos should seed it.

Run:  python -m daydor_api.seed_dev
"""
from __future__ import annotations

import json
from datetime import date

from sqlalchemy import text

from daydor.agents.session import worker_session
from daydor.db.session import tenant_session
from daydor.hire.employee_record import hire_employee, open_employment_record

from . import identity as idn
from . import migrate
from .provision import insert
from .state import get_engine

FOUNDER_EMAIL = "rohan.mehta@acme.test"


def run() -> dict:
    migrate.run()
    engine = get_engine()
    if idn.find_by_email(FOUNDER_EMAIL):
        return {"seeded": False, "reason": "already seeded"}
    with engine.begin() as conn:
        tenant = insert(conn, "tenant", legal_name="Acme Technologies", status="active")
        legal_entity = insert(conn, "legal_entity", tenant_id=tenant, name="Acme Technologies Pvt Ltd",
                              country_code="IN")
        eng = insert(conn, "department", tenant_id=tenant, name="Engineering")
        people = insert(conn, "department", tenant_id=tenant, name="People Operations")
        sales = insert(conn, "department", tenant_id=tenant, name="Sales")
        loc = insert(conn, "location", tenant_id=tenant, name="Bengaluru", country_code="IN",
                     legal_entity_id=legal_entity, state_code="KA")
        # A second, US legal entity/location: Phase 3's live tests run both an India-first and a
        # US-first hire (work authorization only applies to the latter -- daydor.hire.work_
        # authorization reads the employee's own legal_entity.country_code, not a context flag).
        us_legal_entity = insert(conn, "legal_entity", tenant_id=tenant, name="Acme Technologies Inc",
                                 country_code="US")
        us_loc = insert(conn, "location", tenant_id=tenant, name="Austin", country_code="US",
                        legal_entity_id=us_legal_entity, state_code="TX")

    with worker_session(engine, "employee-record-writer", tenant) as conn:
        def hire(event, name, email):
            return hire_employee(conn, hire_event_id=event, full_name=name, work_email=email,
                                 employment_type="full_time", legal_entity_id=legal_entity, department_id=eng,
                                 location_id=loc, state_code="KA", date_of_joining=date(2025, 4, 1),
                                 date_of_birth=date(1990, 1, 1), personal_address="Bengaluru",
                                 aadhaar_last4="0000")
        manager_emp = hire("seed-meera", "Meera Iyer", "meera.iyer@acme.test")
        employee_emp = hire("seed-arjun", "Arjun Rao", "arjun.rao@acme.test")

    with tenant_session(engine, "tenant_hr", tenant) as conn:
        profile = conn.execute(text(
            "INSERT INTO job_profile (title, job_family, level, flsa_default, description) "
            "VALUES ('Backend Engineer', 'Engineering', 'L3', 'exempt', 'Builds and runs backend services') "
            "RETURNING id")).scalar_one()
        for dept, n in ((eng, 2), (sales, 1)):
            for _ in range(n):
                conn.execute(text(
                    "INSERT INTO position (department_id, job_profile_id, status, budgeted_fte, budgeted_cost, "
                    "opened_at) VALUES (:d, :j, 'open', 1.0, 2400000, :o)"),
                    {"d": dept, "j": profile, "o": date(2026, 9, 1)})
        conn.execute(text(
            "INSERT INTO position (department_id, job_profile_id, status, budgeted_fte, budgeted_cost, opened_at, "
            "current_employee_id) VALUES (:d, :j, 'filled', 1.0, 2400000, :o, :e)"),
            {"d": eng, "j": profile, "o": date(2025, 3, 1), "e": manager_emp})
        conn.execute(text(
            "INSERT INTO comp_band (job_profile_id, currency, band_min, band_mid, band_max, effective_from) "
            "VALUES (:j, 'INR', 1800000, 2400000, 3000000, :f)"), {"j": profile, "f": date(2026, 1, 1)})

    # Payroll's own run-builder (not a hire-flow step) processes every active employee under a
    # legal entity, not just new hires -- Meera and Arjun need an employment_record (ctc_annual)
    # too, or compute_gross_to_net raises on them the first time a real payroll run is built.
    with worker_session(engine, "employee-record-writer", tenant) as conn:
        for employee_id, ctc in ((manager_emp, 2400000), (employee_emp, 1800000)):
            open_employment_record(conn, employee_id=employee_id, effective_from=date(2025, 4, 1),
                                   job_profile_id=profile, fte="1.0", ctc_annual=str(ctc),
                                   basic_da_monthly=str(ctc / 24), tax_regime_election="new", flsa_status="exempt")

    # Global, admin-entered reference data (retention_policy's table_acl: only daydor_admin writes
    # it). The hire flow's new-hire-doc-collector (step 13) needs one to exist -- see
    # daydor.hire.documents's module docstring -- so the Start-hiring dialog has something to pick.
    # statutory_rate_rule/pt_slab_rule are the same kind of global reference data (daydor_ops
    # maintains them, not the tenant) -- Payroll's gross-to-net computation needs real rows to read,
    # not hardcoded numbers (docs/sprint-plan.md Sprint 7); values match the backend's own test
    # fixtures (tests/test_payroll_compute.py) so a demo payslip's numbers are hand-checkable.
    with engine.begin() as conn:
        retention_policy = insert(conn, "retention_policy", retention_class="new_hire_docs", record_type="document",
                                  duration_months=84, anchor_field="created_at", legal_basis="contract",
                                  jurisdiction="IN")
        insert(conn, "pt_slab_rule", state_code="KA", effective_from=date(2026, 1, 1),
              slab_min="0", slab_max="15000", monthly_amount="0")
        insert(conn, "pt_slab_rule", state_code="KA", effective_from=date(2026, 1, 1),
              slab_min="15000", monthly_amount="200")
        insert(conn, "statutory_rate_rule", scheme="pf", jurisdiction_code="IN", effective_from=date(2026, 1, 1),
              wage_ceiling="15000", employee_rate="0.12", employer_rate="0.12")
        insert(conn, "statutory_rate_rule", scheme="tds", jurisdiction_code="IN", effective_from=date(2026, 1, 1),
              employee_rate="0.10", employer_rate="0")
        insert(conn, "statutory_rate_rule", scheme="fica", jurisdiction_code="US", effective_from=date(2026, 1, 1),
              employee_rate="0.0765", employer_rate="0.0765")
        insert(conn, "statutory_rate_rule", scheme="fed_wh", jurisdiction_code="US", effective_from=date(2026, 1, 1),
              employee_rate="0.12", employer_rate="0")
        insert(conn, "statutory_rate_rule", scheme="state_wh", jurisdiction_code="US-TX", effective_from=date(2026, 1, 1),
              employee_rate="0.00", employer_rate="0")

    # Admin-entered reference data (tenant_hr writes it directly, same pattern as job_profile/
    # comp_band) that FE-7's leave and benefits screens need something real to pick from.
    with tenant_session(engine, "tenant_hr", tenant) as conn:
        leave_policy = conn.execute(text(
            "INSERT INTO leave_policy (legal_entity_id, leave_type, accrual_rule, carry_forward_cap) "
            "VALUES (:le, 'annual', :r, 15) RETURNING id"),
            {"le": legal_entity, "r": json.dumps({"days_per_month": 1.5})}).scalar_one()
        benefit_plan = conn.execute(text(
            "INSERT INTO benefit_plan (legal_entity_id, plan_type, carrier, plan_year, employer_contribution) "
            "VALUES (:le, 'health', 'Star Health', 2026, 12000) RETURNING id"),
            {"le": legal_entity}).scalar_one()

    with engine.begin() as conn:
        def app_user(email, role, employee=None):
            return insert(conn, "app_user", tenant_id=tenant, email=email, role=role, employee_id=employee,
                          is_active=True, mfa_enrolled=False)
        founder = app_user(FOUNDER_EMAIL, "founder")
        hr = app_user("kavya.menon@acme.test", "hr")
        payroll = app_user("dev.patel@acme.test", "payroll")
        it = app_user("sana.qureshi@acme.test", "it")
        manager = app_user("meera.iyer@acme.test", "manager", manager_emp)
        employee = app_user("arjun.rao@acme.test", "employee", employee_emp)
        # daydor_ops is also a resolver for g_pay_anomaly (model: ap=['P', 'O']) -- without an
        # app_user row, resolving as them fails ("resolving an approval needs a signed-in user").
        ops = app_user("ops@daydor.test", "ops")
        # Daydor ops sees assigned tenants only (backend finding 6, migration 0037): without this row the
        # database shows ops nothing in this tenant, and signing in fails.
        conn.execute(text("INSERT INTO app.ops_tenant_assignment (user_id, tenant_id) VALUES (:u, :t) "
                          "ON CONFLICT DO NOTHING"), {"u": ops, "t": tenant})

    t = "Acme Technologies"
    for email, name, role, user, emp in (
        (FOUNDER_EMAIL, "Rohan Mehta", "tenant_founder", founder, None),
        ("kavya.menon@acme.test", "Kavya Menon", "tenant_hr", hr, None),
        ("dev.patel@acme.test", "Dev Patel", "tenant_payroll", payroll, None),
        ("sana.qureshi@acme.test", "Sana Qureshi", "tenant_it", it, None),
        ("meera.iyer@acme.test", "Meera Iyer", "tenant_manager", manager, manager_emp),
        ("arjun.rao@acme.test", "Arjun Rao", "tenant_employee", employee, employee_emp),
    ):
        idn.create(email=email, display_name=name, role=role, tenant_id=tenant, tenant_name=t, user_id=user,
                   employee_id=emp)
    idn.create(email="ops@daydor.test", display_name="Daydor Ops", role="daydor_ops", tenant_id=tenant,
               tenant_name=t, user_id=ops)
    idn.create(email="admin@daydor.test", display_name="Daydor Admin", role="daydor_admin", tenant_id=None)
    idn.create(email="imran.khan@audit.test", display_name="Imran Khan", role="external_auditor", tenant_id=tenant,
               tenant_name=t)
    return {"seeded": True, "tenant_id": str(tenant), "hiring_manager_id": str(manager_emp)}


if __name__ == "__main__":
    print(run())
