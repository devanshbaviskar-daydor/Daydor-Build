"""payroll-anomaly-detector: the `sg_payroll_anomaly_precheck` soft gate
(`daydor.gates.registry.SOFT_GATES`), escalating to the hard gate `g_pay_anomaly`.

Shadow mode (this gate's seeded mode) always escalates regardless of Jev's answer -- that's
enforced in the database (`app.record_gate_evaluation`'s `CHECK (mode <> 'shadow' OR
effective_decision = 'escalate')`), not just here. With no real Jev API wired yet
(`daydor.gates.jev.HttpJevClient` raises), every call also fails closed to "escalate" on its own.
Put together: every payroll run currently requires a human to review it before disbursal, which
is the correct conservative behavior for an unproven model, not a bug to work around.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, text

from daydor.gates.jev import Choice, DecisionSchema, HttpJevClient, JevClient, JevResult
from daydor.gates.soft import SoftGate, SoftGateOutcome, run_soft_gate

SCHEMA = DecisionSchema("payroll_anomaly", "1",
                        (Choice("run_looks", ("normal", "unusual"),
                                "Does this payroll run's gross/net relative to its own "
                                "anomaly_score look normal for this tenant?"),))


def _payroll_run_state(conn: Connection, run_id: UUID) -> dict:
    row = conn.execute(text("SELECT gross_total, net_total, anomaly_score FROM payroll_run WHERE id = :r"),
                       {"r": run_id}).one()
    return {"gross_total": float(row.gross_total), "net_total": float(row.net_total),
            "anomaly_score": float(row.anomaly_score) if row.anomaly_score is not None else 0.0}


def _pass_if_normal(result: JevResult) -> tuple[bool, float]:
    answer = result.answers["run_looks"]
    return answer.value == "normal", answer.confidence


PAYROLL_ANOMALY_GATE = SoftGate(
    "sg_payroll_anomaly_precheck", SCHEMA,
    ("payroll_run.gross_total", "payroll_run.net_total", "payroll_run.anomaly_score"),
    _payroll_run_state, _pass_if_normal)


def check_payroll_run(conn: Connection, *, payroll_run_id: UUID, jev: JevClient | None = None) -> SoftGateOutcome:
    return run_soft_gate(conn, PAYROLL_ANOMALY_GATE, "payroll_run", payroll_run_id, jev or HttpJevClient())
