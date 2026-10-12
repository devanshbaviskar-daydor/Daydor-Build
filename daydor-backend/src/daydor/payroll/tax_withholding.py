"""tax-withholding-calculator: statutory deductions from `statutory_rate_rule` (PF, FICA,
federal/state withholding) and `pt_slab_rule` (India professional tax).

These are **illustrative**, not certified statutory compliance (see docs/sprint-plan.md Sprint 7
and ADR scope notes): real PF/ESI/TDS and FICA/federal/state withholding rules are far more
involved (slabs, exemptions, filing status, YTD caps) than one flat rate per scheme. What's real
here is the *shape*: rates and slabs come from `statutory_rate_rule`/`pt_slab_rule`, looked up by
jurisdiction and effective-dated as of the pay date, not hardcoded numbers -- that's what this
sprint's exit criteria asks for.

Jurisdiction is the employee's legal_entity.country_code, exactly like
daydor.hire.work_authorization's I-9 applicability check reads it, rather than a context flag.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Connection, text


@dataclass(frozen=True)
class WithholdingLine:
    component_code: str
    amount: Decimal
    rule_id: UUID | None = None


class UnsupportedJurisdiction(RuntimeError):
    pass


def _statutory_rate(conn: Connection, *, scheme: str, jurisdiction_code: str, as_of: date):
    return conn.execute(
        text("SELECT id, wage_ceiling, employee_rate FROM statutory_rate_rule "
             "WHERE scheme = :s AND jurisdiction_code = :j AND effective_from <= :d "
             "AND (effective_to IS NULL OR effective_to >= :d) ORDER BY effective_from DESC LIMIT 1"),
        {"s": scheme, "j": jurisdiction_code, "d": as_of}).one_or_none()


def _pt_slab(conn: Connection, *, state_code: str, gross: Decimal, as_of: date):
    return conn.execute(
        text("SELECT monthly_amount FROM pt_slab_rule WHERE state_code = :st "
             "AND effective_from <= :d AND (effective_to IS NULL OR effective_to >= :d) "
             "AND slab_min <= :g AND (slab_max IS NULL OR slab_max >= :g) "
             "ORDER BY effective_from DESC LIMIT 1"),
        {"st": state_code, "d": as_of, "g": gross}).scalar_one_or_none()


def compute_withholding(conn: Connection, *, employee_id: UUID, gross: Decimal, as_of: date) -> list[WithholdingLine]:
    country_code, state_code = conn.execute(
        text("SELECT le.country_code, e.state_code FROM employee e "
             "JOIN legal_entity le ON le.id = e.legal_entity_id WHERE e.id = :e"),
        {"e": employee_id}).one()

    if country_code == "IN":
        return _compute_india(conn, gross=gross, state_code=state_code, as_of=as_of)
    if country_code == "US":
        return _compute_us(conn, gross=gross, state_code=state_code, as_of=as_of)
    raise UnsupportedJurisdiction(f"no withholding rules for country {country_code!r}")


def _compute_india(conn: Connection, *, gross: Decimal, state_code: str, as_of: date) -> list[WithholdingLine]:
    lines = []

    pt = _pt_slab(conn, state_code=state_code, gross=gross, as_of=as_of)
    if pt is not None:
        lines.append(WithholdingLine("pt", pt))

    pf = _statutory_rate(conn, scheme="pf", jurisdiction_code="IN", as_of=as_of)
    if pf is not None:
        base = min(gross, pf.wage_ceiling) if pf.wage_ceiling is not None else gross
        lines.append(WithholdingLine("pf_employee", (base * pf.employee_rate).quantize(Decimal("0.01")), pf.id))

    tds = _statutory_rate(conn, scheme="tds", jurisdiction_code="IN", as_of=as_of)
    if tds is not None:
        lines.append(WithholdingLine("tds", (gross * tds.employee_rate).quantize(Decimal("0.01")), tds.id))

    return lines


def _compute_us(conn: Connection, *, gross: Decimal, state_code: str, as_of: date) -> list[WithholdingLine]:
    lines = []

    fica = _statutory_rate(conn, scheme="fica", jurisdiction_code="US", as_of=as_of)
    if fica is not None:
        base = min(gross, fica.wage_ceiling) if fica.wage_ceiling is not None else gross
        lines.append(WithholdingLine("fica", (base * fica.employee_rate).quantize(Decimal("0.01")), fica.id))

    federal = _statutory_rate(conn, scheme="fed_wh", jurisdiction_code="US", as_of=as_of)
    if federal is not None:
        lines.append(WithholdingLine("federal_wh", (gross * federal.employee_rate).quantize(Decimal("0.01")),
                                     federal.id))

    state = _statutory_rate(conn, scheme="state_wh", jurisdiction_code=f"US-{state_code}", as_of=as_of)
    if state is not None:
        lines.append(WithholdingLine("state_wh", (gross * state.employee_rate).quantize(Decimal("0.01")),
                                     state.id))

    return lines
