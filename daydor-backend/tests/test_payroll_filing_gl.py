"""Sprint 9: tax-filing-submitter (`filing_record`) and gl-poster (`gl_journal_entry`, gated by
`g_close`) -- the last two steps of "Payroll is demoable end to end."

Own tenant for the same reason the other payroll test files use one: these tests seed/compute
against reference tables and legal entities that should never collide with another test's data.
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from daydor.db.session import tenant_session
from daydor.gates.hard import resolve
from daydor.payroll.gl_posting import open_journal_entry, post_journal_entry, request_gl_close_approval
from daydor.payroll.run_builder import build_payroll_run
from daydor.payroll.tax_filing import file_payroll_run
from daydor.payroll.tax_withholding import UnsupportedJurisdiction
from tests.factories import insert
from tests.hire_helpers import retention_policy  # noqa: F401


@pytest.fixture
def filing_tenant(engine):
    with engine.begin() as conn:
        tenant = insert(conn, "tenant", legal_name="Filing Co", status="active")
        dept = insert(conn, "department", tenant_id=tenant, name="Eng")
        jp = insert(conn, "job_profile", tenant_id=tenant, title="Engineer", job_family="Eng",
                   level="L3", flsa_default="exempt", description="x")
        founder_user = insert(conn, "app_user", tenant_id=tenant, role="founder")
    return {"tenant": tenant, "department": dept, "job_profile": jp, "founder_user": founder_user}


def _legal_entity(engine, tenant, country_code):
    with engine.begin() as conn:
        return insert(conn, "legal_entity", tenant_id=tenant, name=f"LE-{uuid.uuid4().hex[:6]}",
                      country_code=country_code)


def _build_run_with_one_employee(engine, t, *, legal_entity_id, state_code, retention_class_id):
    tenant = t["tenant"]
    with engine.begin() as conn:
        loc = insert(conn, "location", tenant_id=tenant, name="Office", country_code="IN",
                    state_code=state_code, legal_entity_id=legal_entity_id)
        employee_id = insert(conn, "employee", tenant_id=tenant, full_name="Test Employee",
                            legal_entity_id=legal_entity_id, department_id=t["department"],
                            location_id=loc, hire_event_id=f"hire-{uuid.uuid4().hex[:10]}",
                            state_code=state_code, date_of_joining="2026-01-01")
        insert(conn, "employment_record", tenant_id=tenant, employee_id=employee_id,
              effective_from="2026-01-01", job_profile_id=t["job_profile"], fte="1.0",
              ctc_annual="1200000", basic_da_monthly=str(Decimal("1200000") / 24),
              tax_regime_election="new", flsa_status="exempt")
        insert(conn, "pt_slab_rule", state_code=state_code, effective_from="2026-01-01",
              slab_min="0", monthly_amount="0")
        insert(conn, "statutory_rate_rule", scheme="pf", jurisdiction_code="IN",
              effective_from="2026-01-01", wage_ceiling="15000", employee_rate="0.12",
              employer_rate="0.12")
        insert(conn, "statutory_rate_rule", scheme="tds", jurisdiction_code="IN",
              effective_from="2026-01-01", employee_rate="0.10", employer_rate="0")

    with tenant_session(engine, "agent_pay", tenant) as conn:
        return build_payroll_run(conn, legal_entity_id=legal_entity_id, period_start=date(2026, 8, 1),
                                 period_end=date(2026, 8, 31), retention_class_id=retention_class_id)


def test_filing_submitter_files_every_scheme_for_india_and_is_idempotent(engine, filing_tenant,
                                                                         retention_policy):
    tenant = filing_tenant["tenant"]
    le = _legal_entity(engine, tenant, "IN")
    state_code = f"KA{uuid.uuid4().hex[:6]}"
    built = _build_run_with_one_employee(engine, filing_tenant, legal_entity_id=le,
                                         state_code=state_code, retention_class_id=retention_policy)

    with tenant_session(engine, "agent_pay", tenant) as conn:
        first = file_payroll_run(conn, payroll_run_id=built["payroll_run_id"], period="2026-08",
                                 retention_class_id=retention_policy)
        second = file_payroll_run(conn, payroll_run_id=built["payroll_run_id"], period="2026-08",
                                  retention_class_id=retention_policy)

    assert len(first) == 2  # ecr, 24q
    assert sorted(first) == sorted(second)
    with engine.begin() as conn:
        schemes = conn.execute(text("SELECT scheme, acknowledgement_no FROM filing_record "
                                    "WHERE legal_entity_id = :le"), {"le": le}).all()
    assert {s.scheme for s in schemes} == {"ecr", "24q"}
    assert all(s.acknowledgement_no is not None for s in schemes)


def test_filing_submitter_raises_for_an_unregistered_jurisdiction(engine, filing_tenant,
                                                                   retention_policy):
    tenant = filing_tenant["tenant"]
    le = _legal_entity(engine, tenant, "FR")
    with tenant_session(engine, "agent_pay", tenant) as conn:
        built = build_payroll_run(conn, legal_entity_id=le, period_start=date(2026, 8, 1),
                                  period_end=date(2026, 8, 31), retention_class_id=retention_policy)
        with pytest.raises(UnsupportedJurisdiction):
            file_payroll_run(conn, payroll_run_id=built["payroll_run_id"], period="2026-08",
                             retention_class_id=retention_policy)


def test_gl_posting_is_impossible_without_an_approved_g_close_request(engine, filing_tenant,
                                                                       retention_policy):
    tenant = filing_tenant["tenant"]
    founder_user = filing_tenant["founder_user"]
    le = _legal_entity(engine, tenant, "IN")
    state_code = f"KA{uuid.uuid4().hex[:6]}"
    built = _build_run_with_one_employee(engine, filing_tenant, legal_entity_id=le,
                                         state_code=state_code, retention_class_id=retention_policy)
    run_id = built["payroll_run_id"]

    with tenant_session(engine, "agent_pay", tenant) as conn:
        je_id = open_journal_entry(conn, payroll_run_id=run_id)
        je_id_again = open_journal_entry(conn, payroll_run_id=run_id)
    assert je_id == je_id_again

    with tenant_session(engine, "agent_pay", tenant) as conn:
        approval_id = request_gl_close_approval(conn, gl_journal_entry_id=je_id)

    with pytest.raises(DBAPIError):
        with tenant_session(engine, "agent_pay", tenant) as conn:
            post_journal_entry(conn, gl_journal_entry_id=je_id, approval_request_id=approval_id)

    with tenant_session(engine, "tenant_founder", tenant, user_id=founder_user) as conn:
        assert resolve(conn, approval_id, "approved") == "approved"

    with tenant_session(engine, "agent_pay", tenant) as conn:
        post_journal_entry(conn, gl_journal_entry_id=je_id, approval_request_id=approval_id)

    with engine.begin() as conn:
        row = conn.execute(text("SELECT posted_at, debit_account, credit_account, amount "
                                "FROM gl_journal_entry WHERE id = :i"), {"i": je_id}).one()
    assert row.posted_at is not None
    assert row.debit_account == "payroll_expense" and row.credit_account == "cash"
    assert row.amount == Decimal("88200.00")

    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(text("UPDATE gl_journal_entry SET posted_at = now() WHERE id = :i"),
                        {"i": je_id})
