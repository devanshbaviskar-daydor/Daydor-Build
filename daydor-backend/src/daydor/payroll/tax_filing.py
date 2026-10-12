"""tax-filing-submitter: files `filing_record` rows for a payroll run's statutory schemes.

Illustrative scheme lists per jurisdiction, same scope note as daydor.payroll.tax_withholding:
real statutory filing calendars have many more schemes, cadences and amendments than one filing
per scheme per payroll period. What's real here is the shape -- one `filing_record` row per
scheme, carrying the vendor's acknowledgement number, idempotent per (legal_entity, scheme,
period) so re-running a filing job never double-files.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import Connection, text

from daydor.adapters.tax_filing import FakeTaxFilingAdapter, TaxFilingAdapter, TaxFilingRequest
from daydor.payroll.tax_withholding import UnsupportedJurisdiction

SCHEMES_BY_COUNTRY = {
    "IN": ("ecr", "24q"),
    "US": ("941", "w2", "state_ui"),
}


def file_payroll_run(conn: Connection, adapter: TaxFilingAdapter | None = None, *,
                     payroll_run_id: UUID, period: str, retention_class_id: UUID) -> list[UUID]:
    adapter = adapter or FakeTaxFilingAdapter()
    legal_entity_id, country_code = conn.execute(
        text("SELECT pr.legal_entity_id, le.country_code FROM payroll_run pr "
             "JOIN legal_entity le ON le.id = pr.legal_entity_id WHERE pr.id = :r"),
        {"r": payroll_run_id}).one()

    schemes = SCHEMES_BY_COUNTRY.get(country_code)
    if schemes is None:
        raise UnsupportedJurisdiction(f"no filing schemes registered for {country_code}")

    filing_ids = []
    for scheme in schemes:
        existing = conn.execute(
            text("SELECT id FROM filing_record WHERE legal_entity_id = :le AND scheme = :s "
                 "AND period = :p"), {"le": legal_entity_id, "s": scheme, "p": period},
        ).scalar_one_or_none()
        if existing is not None:
            filing_ids.append(existing)
            continue

        result = adapter.submit(TaxFilingRequest(scheme=scheme, period=period))
        filing_id = conn.execute(
            text("INSERT INTO filing_record (legal_entity_id, scheme, period, filed_on, "
                 "acknowledgement_no, retention_class) VALUES (:le, :s, :p, :f, :a, :rc) "
                 "RETURNING id"),
            {"le": legal_entity_id, "s": scheme, "p": period,
             "f": datetime.now(timezone.utc).date(),
             "a": result.acknowledgement_no, "rc": retention_class_id}).scalar_one()
        filing_ids.append(filing_id)

    return filing_ids
