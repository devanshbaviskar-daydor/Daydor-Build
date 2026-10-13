"""Gross-to-net computation (docs/sprint-plan.md Sprint 7). Pure computation, not persistence --
see daydor.payroll.compute's module docstring (finding 17) for why payslip_line rows aren't
written yet.

Uses its own tenant (not the shared `org`/`hire_org` fixtures) because jurisdiction packs
(statutory_rate_rule, pt_slab_rule) are *global* reference tables keyed by scheme/jurisdiction
code: every test here picks unique, synthetic codes so they can't collide with each other or with
real-looking codes another test file might one day seed."""
import uuid
from datetime import date
from decimal import Decimal

import pytest

from daydor.agents.session import worker_session
from daydor.db.session import tenant_session
from daydor.payroll.compute import compute_gross_to_net
from daydor.payroll.garnishment import compute_garnishments
from daydor.payroll.tax_withholding import UnsupportedJurisdiction, compute_withholding
from tests.factories import insert


@pytest.fixture
def payroll_tenant(engine):
    with engine.begin() as conn:
        tenant = insert(conn, "tenant", legal_name="Payroll Co", status="active")
        dept = insert(conn, "department", tenant_id=tenant, name="Eng")
        jp = insert(conn, "job_profile", tenant_id=tenant, title="Engineer", job_family="Eng",
                   level="L3", flsa_default="exempt", description="x")
    return {"tenant": tenant, "department": dept, "job_profile": jp}


def _make_employee(engine, payroll_tenant, *, country_code, state_code, ctc_annual):
    tenant = payroll_tenant["tenant"]
    with engine.begin() as conn:
        le = insert(conn, "legal_entity", tenant_id=tenant, name=f"LE-{uuid.uuid4().hex[:6]}",
                   country_code=country_code)
        loc = insert(conn, "location", tenant_id=tenant, name="Office", country_code=country_code,
                    state_code=state_code, legal_entity_id=le)
        employee_id = insert(conn, "employee", tenant_id=tenant, full_name="Test Employee",
                            legal_entity_id=le, department_id=payroll_tenant["department"],
                            location_id=loc, hire_event_id=f"hire-{uuid.uuid4().hex[:10]}",
                            state_code=state_code, date_of_joining="2026-01-01")
        insert(conn, "employment_record", tenant_id=tenant, employee_id=employee_id,
              effective_from="2026-01-01", job_profile_id=payroll_tenant["job_profile"],
              fte="1.0", ctc_annual=str(ctc_annual), basic_da_monthly=str(ctc_annual / 24),
              tax_regime_election="new", flsa_status="exempt")
    return employee_id


def test_india_gross_to_net_uses_real_slab_and_rate_rows(engine, payroll_tenant):
    """1,200,000 ctc_annual -> 100,000 gross. PT slab (>15000 -> 200), PF (12% of min(gross,
    15000) = 1800), TDS (flat 10% illustrative = 10000). Net = 100000 - 200 - 1800 - 10000 = 88000."""
    tenant = payroll_tenant["tenant"]
    state_code = f"KA{uuid.uuid4().hex[:6]}"
    employee_id = _make_employee(engine, payroll_tenant, country_code="IN", state_code=state_code,
                                 ctc_annual=Decimal("1200000"))
    with engine.begin() as conn:
        insert(conn, "pt_slab_rule", state_code=state_code, effective_from="2026-01-01",
              slab_min="0", slab_max="15000", monthly_amount="0")
        insert(conn, "pt_slab_rule", state_code=state_code, effective_from="2026-01-01",
              slab_min="15000", monthly_amount="200")
        insert(conn, "statutory_rate_rule", scheme="pf", jurisdiction_code="IN",
              effective_from="2026-01-01", wage_ceiling="15000", employee_rate="0.12",
              employer_rate="0.12")
        insert(conn, "statutory_rate_rule", scheme="tds", jurisdiction_code="IN",
              effective_from="2026-01-01", employee_rate="0.10", employer_rate="0")

    with worker_session(engine, "payroll-run-builder", tenant) as conn:
        result = compute_gross_to_net(conn, employee_id=employee_id, as_of=date(2026, 3, 1))

    assert result.gross == Decimal("100000.00")
    by_code = {w.component_code: w.amount for w in result.withholding}
    assert by_code == {"pt": Decimal("200"), "pf_employee": Decimal("1800.00"), "tds": Decimal("10000.00")}
    assert result.net == Decimal("88000.00")


def test_us_gross_to_net_uses_real_rate_rows(engine, payroll_tenant):
    """120,000 ctc_annual -> 10,000 gross. FICA 7.65% = 765, federal 12% = 1200, CA state 5% =
    500. Net = 10000 - 765 - 1200 - 500 = 7535."""
    tenant = payroll_tenant["tenant"]
    state_code = f"Z{uuid.uuid4().hex[:6]}"
    employee_id = _make_employee(engine, payroll_tenant, country_code="US", state_code=state_code,
                                 ctc_annual=Decimal("120000"))
    with engine.begin() as conn:
        insert(conn, "statutory_rate_rule", scheme="fica", jurisdiction_code="US",
              effective_from="2026-01-01", employee_rate="0.0765", employer_rate="0.0765")
        insert(conn, "statutory_rate_rule", scheme="fed_wh", jurisdiction_code="US",
              effective_from="2026-01-01", employee_rate="0.12", employer_rate="0")
        insert(conn, "statutory_rate_rule", scheme="state_wh", jurisdiction_code=f"US-{state_code}",
              effective_from="2026-01-01", employee_rate="0.05", employer_rate="0")

    with worker_session(engine, "payroll-run-builder", tenant) as conn:
        result = compute_gross_to_net(conn, employee_id=employee_id, as_of=date(2026, 3, 1))

    assert result.gross == Decimal("10000.00")
    by_code = {w.component_code: w.amount for w in result.withholding}
    assert by_code == {"fica": Decimal("765.00"), "federal_wh": Decimal("1200.00"),
                       "state_wh": Decimal("500.00")}
    assert result.net == Decimal("7535.00")


def test_withholding_is_effective_dated(engine, payroll_tenant):
    """A rate change only applies from its own effective_from; an older pay date still sees the
    old rate, not a hardcoded single rule."""
    tenant = payroll_tenant["tenant"]
    jurisdiction = f"US-{uuid.uuid4().hex[:8]}"
    employee_id = _make_employee(engine, payroll_tenant, country_code="US", state_code=jurisdiction[3:],
                                 ctc_annual=Decimal("120000"))
    with engine.begin() as conn:
        insert(conn, "statutory_rate_rule", scheme="fed_wh", jurisdiction_code="US",
              effective_from="2020-01-01", effective_to="2025-12-31", employee_rate="0.10",
              employer_rate="0")
        insert(conn, "statutory_rate_rule", scheme="fed_wh", jurisdiction_code="US",
              effective_from="2026-01-01", employee_rate="0.12", employer_rate="0")

    with worker_session(engine, "payroll-run-builder", tenant) as conn:
        old = compute_withholding(conn, employee_id=employee_id, gross=Decimal("10000"),
                                  as_of=date(2024, 6, 1))
        new = compute_withholding(conn, employee_id=employee_id, gross=Decimal("10000"),
                                  as_of=date(2026, 6, 1))
    assert {w.component_code: w.amount for w in old}["federal_wh"] == Decimal("1000.00")
    assert {w.component_code: w.amount for w in new}["federal_wh"] == Decimal("1200.00")


def test_unsupported_jurisdiction_raises_rather_than_silently_skipping(engine, payroll_tenant):
    employee_id = _make_employee(engine, payroll_tenant, country_code="FR", state_code="IDF",
                                 ctc_annual=Decimal("60000"))
    with worker_session(engine, "payroll-run-builder", payroll_tenant["tenant"]) as conn:
        with pytest.raises(UnsupportedJurisdiction):
            compute_withholding(conn, employee_id=employee_id, gross=Decimal("5000"), as_of=date(2026, 3, 1))


def test_garnishments_apply_in_priority_order_and_never_exceed_base(engine, payroll_tenant):
    tenant = payroll_tenant["tenant"]
    employee_id = _make_employee(engine, payroll_tenant, country_code="IN", state_code="XX",
                                 ctc_annual=Decimal("120000"))
    with engine.begin() as conn:
        first = insert(conn, "garnishment_order", tenant_id=tenant, employee_id=employee_id,
                      issuing_authority="Court A", order_type="fixed_amount", amount_or_pct="3000",
                      priority=1, effective_from="2026-01-01")
        second = insert(conn, "garnishment_order", tenant_id=tenant, employee_id=employee_id,
                       issuing_authority="Court B", order_type="percentage", amount_or_pct="0.50",
                       priority=2, effective_from="2026-01-01")

    with worker_session(engine, "payroll-run-builder", tenant) as conn:
        lines = compute_garnishments(conn, employee_id=employee_id, base=Decimal("4000"),
                                     as_of=date(2026, 3, 1))

    assert len(lines) == 2
    assert lines[0].order_id == first and lines[0].amount == Decimal("3000")
    # Second order wants 50% of the 4000 base (2000) but only 1000 remains after the first.
    assert lines[1].order_id == second and lines[1].amount == Decimal("1000")
