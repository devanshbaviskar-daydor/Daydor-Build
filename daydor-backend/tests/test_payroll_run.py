"""Sprint 8: payroll-run-builder, the sg_payroll_anomaly_precheck soft gate, and the
g_pay_disburse hard gate that makes disbursal provably impossible without an approved request.

Uses its own tenant (not `org`/`hire_org`) for the same reason test_payroll_compute.py does:
jurisdiction packs (statutory_rate_rule, pt_slab_rule) are global reference tables keyed by
synthetic, per-test-unique codes.
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from daydor.agents.session import worker_session
from daydor.db.session import tenant_session
from daydor.gates.hard import resolve
from daydor.payroll.anomaly import check_payroll_run
from daydor.payroll.disbursement import disburse_payroll_run, request_disbursal_approval
from daydor.payroll.payslip_issuer import PayrollRunNotDisbursed, issue_payslips
from daydor.payroll.run_builder import build_payroll_run
from tests.factories import insert
from tests.hire_helpers import retention_policy  # noqa: F401


@pytest.fixture
def payroll_run_tenant(engine):
    with engine.begin() as conn:
        tenant = insert(conn, "tenant", legal_name="Run Co", status="active")
        dept = insert(conn, "department", tenant_id=tenant, name="Eng")
        jp = insert(conn, "job_profile", tenant_id=tenant, title="Engineer", job_family="Eng",
                   level="L3", flsa_default="exempt", description="x")
        founder_user = insert(conn, "app_user", tenant_id=tenant, role="founder")
    return {"tenant": tenant, "department": dept, "job_profile": jp, "founder_user": founder_user}


def _make_employee(engine, t, *, legal_entity_id, state_code, ctc_annual):
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
              ctc_annual=str(ctc_annual), basic_da_monthly=str(ctc_annual / 24),
              tax_regime_election="new", flsa_status="exempt")
    return employee_id


@pytest.fixture
def seeded_run(engine, payroll_run_tenant, retention_policy):
    """One legal entity, two active employees, India jurisdiction rules seeded, ready to build."""
    state_code = f"KA{uuid.uuid4().hex[:6]}"
    with engine.begin() as conn:
        le = insert(conn, "legal_entity", tenant_id=payroll_run_tenant["tenant"],
                   name=f"LE-{uuid.uuid4().hex[:6]}", country_code="IN")
    emp1 = _make_employee(engine, payroll_run_tenant, legal_entity_id=le, state_code=state_code,
                          ctc_annual=Decimal("1200000"))
    emp2 = _make_employee(engine, payroll_run_tenant, legal_entity_id=le, state_code=state_code,
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
    return {**payroll_run_tenant, "legal_entity": le, "employees": (emp1, emp2),
           "retention_policy": retention_policy}


def test_build_payroll_run_aggregates_employees_and_accrues_gratuity(engine, seeded_run):
    tenant = seeded_run["tenant"]
    with worker_session(engine, "payroll-run-builder", tenant) as conn:
        result = build_payroll_run(conn, legal_entity_id=seeded_run["legal_entity"],
                                   period_start=date(2026, 3, 1), period_end=date(2026, 3, 31),
                                   retention_class_id=seeded_run["retention_policy"])
    run_id = result["payroll_run_id"]
    assert len(result["payslip_ids"]) == 2

    with engine.begin() as conn:
        run = conn.execute(
            text(
                "SELECT status, gross_total, net_total FROM payroll_run WHERE id = :r"),
            {"r": run_id}).one()
        assert run.status == "built"
        assert run.gross_total == Decimal("200000.00")
        assert run.net_total == Decimal("176000.00")

        payslips = conn.execute(
            text(
                "SELECT employee_id, gross_pay, net_pay FROM payslip WHERE payroll_run_id = :r"),
            {"r": run_id}).all()
        assert {p.gross_pay for p in payslips} == {Decimal("100000.00")}
        assert {p.net_pay for p in payslips} == {Decimal("88000.00")}

        lines = conn.execute(
            text(
                "SELECT component_code FROM payslip_line pl JOIN payslip p ON p.id = pl.payslip_id "
                "WHERE p.payroll_run_id = :r"), {"r": run_id}).scalars().all()
        assert sorted(lines).count("pt") == 2
        assert sorted(lines).count("pf_employee") == 2
        assert sorted(lines).count("tds") == 2

        gratuity = conn.execute(
            text(
                "SELECT employee_id, accrued_amount FROM gratuity_accrual_balance "
                "WHERE employee_id = ANY(:emps)"),
            {"emps": list(seeded_run["employees"])}).all()
        assert len(gratuity) == 2
        for g in gratuity:
            assert g.accrued_amount == (Decimal("50000") * Decimal("0.0481")).quantize(Decimal("0.01"))


def test_build_payroll_run_is_idempotent_on_period(engine, seeded_run):
    tenant = seeded_run["tenant"]
    with worker_session(engine, "payroll-run-builder", tenant) as conn:
        first = build_payroll_run(conn, legal_entity_id=seeded_run["legal_entity"],
                                  period_start=date(2026, 4, 1), period_end=date(2026, 4, 30),
                                  retention_class_id=seeded_run["retention_policy"])
        second = build_payroll_run(conn, legal_entity_id=seeded_run["legal_entity"],
                                   period_start=date(2026, 4, 1), period_end=date(2026, 4, 30),
                                   retention_class_id=seeded_run["retention_policy"])
    assert first["payroll_run_id"] == second["payroll_run_id"]
    assert sorted(first["payslip_ids"]) == sorted(second["payslip_ids"])


def test_anomaly_soft_gate_always_escalates_in_shadow_mode(engine, seeded_run):
    tenant = seeded_run["tenant"]
    with worker_session(engine, "payroll-run-builder", tenant) as conn:
        built = build_payroll_run(conn, legal_entity_id=seeded_run["legal_entity"],
                                  period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
                                  retention_class_id=seeded_run["retention_policy"])
        run_id = built["payroll_run_id"]
    with worker_session(engine, "payroll-anomaly-detector", tenant) as conn:
        outcome = check_payroll_run(conn, payroll_run_id=run_id)

    assert outcome.effective_decision == "escalate"
    assert outcome.approval_request_id is not None
    with engine.begin() as conn:
        gate_type = conn.execute(
            text(
                "SELECT gate_type FROM approval_request WHERE id = :a"),
            {"a": outcome.approval_request_id}).scalar_one()
    assert gate_type == "g_pay_anomaly"


def test_disbursal_is_impossible_without_an_approved_g_pay_disburse_request(engine, seeded_run):
    """The sprint's own exit criterion: build the row, ask for approval, try to disburse against
    the still-pending request (must fail), approve it, then disbursal succeeds -- and only then
    can payslips be issued."""
    tenant = seeded_run["tenant"]
    founder_user = seeded_run["founder_user"]

    with worker_session(engine, "payroll-run-builder", tenant) as conn:
        built = build_payroll_run(conn, legal_entity_id=seeded_run["legal_entity"],
                                  period_start=date(2026, 6, 1), period_end=date(2026, 6, 30),
                                  retention_class_id=seeded_run["retention_policy"])
        run_id = built["payroll_run_id"]

    with pytest.raises(PayrollRunNotDisbursed):
        with worker_session(engine, "payslip-issuer", tenant) as conn:
            issue_payslips(conn, payroll_run_id=run_id)

    with worker_session(engine, "direct-deposit-disburser", tenant) as conn:
        approval_id = request_disbursal_approval(conn, payroll_run_id=run_id)

    with pytest.raises(DBAPIError):
        with worker_session(engine, "direct-deposit-disburser", tenant) as conn:
            disburse_payroll_run(conn, payroll_run_id=run_id, approval_request_id=approval_id)

    with tenant_session(engine, "tenant_founder", tenant, user_id=founder_user) as conn:
        assert resolve(conn, approval_id, "approved") == "approved"

    with worker_session(engine, "direct-deposit-disburser", tenant) as conn:
        disburse_payroll_run(conn, payroll_run_id=run_id, approval_request_id=approval_id)

    with engine.begin() as conn:
        disbursed_at = conn.execute(
            text("SELECT disbursed_at FROM payroll_run WHERE id = :r"),
            {"r": run_id}).scalar_one()
    assert disbursed_at is not None

    with worker_session(engine, "payslip-issuer", tenant) as conn:
        issued = issue_payslips(conn, payroll_run_id=run_id)
    assert len(issued) == 2

    with worker_session(engine, "payslip-issuer", tenant) as conn:
        assert issue_payslips(conn, payroll_run_id=run_id) == []


def test_disbursal_rejects_an_approval_for_a_different_gate_or_row(engine, seeded_run):
    tenant = seeded_run["tenant"]
    with worker_session(engine, "payroll-run-builder", tenant) as conn:
        built = build_payroll_run(conn, legal_entity_id=seeded_run["legal_entity"],
                                  period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
                                  retention_class_id=seeded_run["retention_policy"])
        run_id = built["payroll_run_id"]
    with worker_session(engine, "direct-deposit-disburser", tenant) as conn:
        bogus_approval_id = uuid.uuid4()
        with pytest.raises(DBAPIError):
            disburse_payroll_run(conn, payroll_run_id=run_id, approval_request_id=bogus_approval_id)
