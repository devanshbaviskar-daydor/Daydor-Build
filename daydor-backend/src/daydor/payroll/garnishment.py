"""garnishment-processor: deductions from `garnishment_order`, applied in priority order, never
taking net below zero. `order_type` convention: 'fixed_amount' (amount_or_pct is a currency
amount) or 'percentage' (amount_or_pct is applied to `base`, e.g. disposable earnings) --
free text, like every other enum in this model until finding 5 is resolved.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Connection, text


@dataclass(frozen=True)
class GarnishmentLine:
    component_code: str
    amount: Decimal
    order_id: UUID


def compute_garnishments(conn: Connection, *, employee_id: UUID, base: Decimal,
                         as_of: date) -> list[GarnishmentLine]:
    orders = conn.execute(
        text("SELECT id, order_type, amount_or_pct FROM garnishment_order WHERE employee_id = :e "
             "AND effective_from <= :d AND (effective_to IS NULL OR effective_to >= :d) "
             "ORDER BY priority ASC"), {"e": employee_id, "d": as_of}).all()

    lines = []
    remaining = base
    for order in orders:
        if remaining <= 0:
            break
        requested = order.amount_or_pct if order.order_type == "fixed_amount" \
            else (base * order.amount_or_pct).quantize(Decimal("0.01"))
        amount = min(requested, remaining)
        lines.append(GarnishmentLine(f"garnishment_{order.id}", amount, order.id))
        remaining -= amount
    return lines
