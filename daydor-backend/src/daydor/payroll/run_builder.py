"""payroll-run-builder: ties Sprints 6-7 together into a real `payroll_run`, `payslip`,
`payslip_line` and `gratuity_accrual_balance` for every active employee under a legal entity.

Split across workers (Oct 13 2026; it used to be one transaction with a combined scope): the three
computation steps run as their own workers (`daydor.payroll.compute.compute_staged`: gross-pay-calculator,
tax-withholding-calculator, garnishment-processor, all pure reads), and only the persistence is
payroll-run-builder's. `build_payroll_run` is the orchestration, so it takes an engine and a tenant
instead of one connection: it cannot run as a single role any more. Persistence is still one
transaction, so a run is all or nothing.

Scope decision: unlike the hire flow, this is **not** driven through `WorkflowEngine`. A payroll
run's gates (`g_pay_anomaly`, `g_pay_disburse`) are checked via direct calls to
`run_soft_gate`/`request_approval` on the `payroll_run` row itself -- the same pattern Sprint 6
already uses for timecards (a single gated row, not a long-lived, many-real-world-events journey
the way one candidate's hire is). `payroll_run.status` carries the same bookkeeping a workflow
instance's `state` would, without the overhead of a state machine for a flow this short.

Finding 19 (docs/model-findings.md): `payroll_run.gross_total`/`net_total` and
`payslip.gross_pay`/`net_pay`/`tax_withheld` are all `derived` columns -- no role, not even
`agent_runtime`, has an INSERT/UPDATE grant on them (ddl.py's grants() excludes every `derived`
column). They're written through the SECURITY DEFINER functions in
`migrations/sql/0021_payroll_run_functions.sql` (`app.open_payroll_run`, `app.record_payslip`,
`app.finalize_payroll_run`), the same pattern `daydor.privacy.pii` uses for encrypted columns.

Gratuity accrual (India only, illustrative) uses a flat monthly rate; a real engine would account
for the 15-days-per-year-of-service / 26-working-days statutory formula precisely.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Connection, Engine, text

from daydor.agents.session import worker_session
from daydor.payroll.compute import GrossToNetResult, compute_staged

GRATUITY_MONTHLY_ACCRUAL_RATE = Decimal("0.0481")  # illustrative: ~15/26/12


def _current_employment_record_id(conn: Connection, employee_id: UUID, as_of: date) -> UUID:
    return conn.execute(
        text("SELECT id FROM employment_record WHERE employee_id = :e AND effective_from <= :d "
             "AND (effective_to IS NULL OR effective_to >= :d) ORDER BY effective_from DESC LIMIT 1"),
        {"e": employee_id, "d": as_of}).scalar_one()


def _existing_run(conn: Connection, legal_entity_id: UUID, period_start: date, period_end: date) -> dict | None:
    existing = conn.execute(
        text("SELECT id FROM payroll_run WHERE legal_entity_id = :le AND period_start = :s "
             "AND period_end = :f"), {"le": legal_entity_id, "s": period_start, "f": period_end},
    ).scalar_one_or_none()
    if existing is None:
        return None
    payslip_ids = conn.execute(text("SELECT id FROM payslip WHERE payroll_run_id = :r"),
                               {"r": existing}).scalars().all()
    return {"payroll_run_id": existing, "payslip_ids": payslip_ids}


def build_payroll_run(engine: Engine, tenant_id: UUID, *, legal_entity_id: UUID, period_start: date,
                      period_end: date, retention_class_id: UUID, user_id: UUID | None = None) -> dict:
    """Idempotent on (legal_entity_id, period_start, period_end).

    1. payroll-run-builder: is there already a run, and who is on it?
    2. the calculators, one worker each: gross, withholding, garnishments (reads only)
    3. payroll-run-builder: write the run, its payslips and lines, the gratuity accrual, in one transaction
    """
    with worker_session(engine, "payroll-run-builder", tenant_id, user_id=user_id) as conn:
        existing = _existing_run(conn, legal_entity_id, period_start, period_end)
        if existing is not None:
            return existing
        employee_ids = conn.execute(
            text("SELECT id FROM employee WHERE legal_entity_id = :le AND is_active = true"),
            {"le": legal_entity_id}).scalars().all()

    results = compute_staged(engine, tenant_id, employee_ids, period_end, user_id=user_id)

    with worker_session(engine, "payroll-run-builder", tenant_id, user_id=user_id) as conn:
        existing = _existing_run(conn, legal_entity_id, period_start, period_end)    # a concurrent call won
        if existing is not None:
            return existing
        return persist_payroll_run(conn, legal_entity_id=legal_entity_id, period_start=period_start,
                                   period_end=period_end, retention_class_id=retention_class_id, results=results)


def persist_payroll_run(conn: Connection, *, legal_entity_id: UUID, period_start: date, period_end: date,
                        retention_class_id: UUID, results: dict[UUID, GrossToNetResult]) -> dict:
    """payroll-run-builder's own work: write what the calculators computed."""
    payroll_run_id = conn.execute(
        text("SELECT app.open_payroll_run(:le, :s, :f, :r)"),
        {"le": legal_entity_id, "s": period_start, "f": period_end, "r": retention_class_id},
    ).scalar_one()

    payslip_ids = []
    for employee_id, result in results.items():
        employment_record_id = _current_employment_record_id(conn, employee_id, period_end)
        tax_withheld = sum((w.amount for w in result.withholding), Decimal("0"))
        payslip_id = conn.execute(
            text("SELECT app.record_payslip(:r, :e, :er, :g, :n, :t, :rc)"),
            {"r": payroll_run_id, "e": employee_id, "er": employment_record_id, "g": result.gross,
             "n": result.net, "t": tax_withheld, "rc": retention_class_id}).scalar_one()
        payslip_ids.append(payslip_id)

        for line in [*result.withholding, *result.garnishments]:
            conn.execute(
                text("INSERT INTO payslip_line (payslip_id, component_code, amount, rule_id) "
                     "VALUES (:p, :c, :a, :rule)"),
                {"p": payslip_id, "c": line.component_code, "a": line.amount,
                 "rule": getattr(line, "rule_id", None)})

        _accrue_gratuity(conn, employee_id=employee_id, as_of_period=period_end)

    conn.execute(text("SELECT app.finalize_payroll_run(:r)"), {"r": payroll_run_id})

    return {"payroll_run_id": payroll_run_id, "payslip_ids": payslip_ids}


def _accrue_gratuity(conn: Connection, *, employee_id: UUID, as_of_period: date) -> None:
    country_code = conn.execute(
        text("SELECT le.country_code FROM employee e JOIN legal_entity le ON le.id = e.legal_entity_id "
             "WHERE e.id = :e"), {"e": employee_id}).scalar_one()
    if country_code != "IN":
        return

    employment_record_id = _current_employment_record_id(conn, employee_id, as_of_period)
    wage_base = conn.execute(text("SELECT basic_da_monthly FROM employment_record WHERE id = :er"),
                             {"er": employment_record_id}).scalar_one()
    monthly_accrual = (wage_base * GRATUITY_MONTHLY_ACCRUAL_RATE).quantize(Decimal("0.01"))

    existing = conn.execute(text("SELECT id, accrued_amount FROM gratuity_accrual_balance "
                                 "WHERE employee_id = :e"), {"e": employee_id}).one_or_none()
    if existing is not None:
        conn.execute(text("UPDATE gratuity_accrual_balance SET accrued_amount = :a, "
                          "gratuity_wage_base = :w, as_of_period = :p WHERE id = :i"),
                    {"a": existing.accrued_amount + monthly_accrual, "w": wage_base,
                     "p": as_of_period, "i": existing.id})
    else:
        conn.execute(text("INSERT INTO gratuity_accrual_balance (employee_id, as_of_period, "
                          "accrued_amount, gratuity_wage_base) VALUES (:e, :p, :a, :w)"),
                    {"e": employee_id, "p": as_of_period, "a": monthly_accrual, "w": wage_base})
