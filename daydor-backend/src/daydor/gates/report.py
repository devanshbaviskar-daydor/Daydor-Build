"""Shadow-mode report: what a soft gate would have decided, against what a person did.

Every soft gate starts in shadow mode: it records its answer and the database forces `escalate`, so a person
decides on the hard gate it escalated to. `app.gate_shadow_outcome` (0036) pairs the two. This module turns
those pairs into the numbers the promotion criteria ask for (docs/backend-plan.md, "Promotion to enforce"):

  * how many decisions are labelled, and how many carry the rarer label
  * how often a person disagreed with a decision the gate would have auto-passed (the criterion is under 1%)
  * expected calibration error of the gate's confidence on the decisions it would have auto-passed
  * latency and error rate

It reads through the caller's own session, so row security applies: a tenant sees its own evaluations, and
ops sees the tenants it is assigned. Pooling rows across tenants is a separate, opt-in step (ADR-006).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Sequence

from sqlalchemy import Connection, text

# Starting points for the criteria, set per gate with its owner. The database enforces the same numbers on an
# approved calibration (app.gate_calibration), so these are for reading, not for deciding.
MIN_LABELS = 300
MIN_RARER_LABEL = 50
MAX_ECE = 0.10
MAX_AUTO_PASS_DISAGREEMENT = 0.01
BINS = 10


@dataclass(frozen=True)
class Outcome:
    """One evaluation, with the human decision when there is one."""
    model_decision: str                 # 'pass' | 'escalate' | 'error'
    confidence: float | None
    threshold: float
    human_label: str | None             # 'pass' | 'escalate' | None while unresolved
    latency_ms: int | None = None
    created_at: datetime | None = None
    approval_request_id: object | None = None

    @property
    def would_auto_pass(self) -> bool:
        """The gate would have skipped the extra review: it said pass, confidently enough."""
        return self.model_decision == "pass" and self.confidence is not None and self.confidence >= self.threshold


@dataclass(frozen=True)
class ReliabilityBin:
    low: float
    high: float
    n: int
    mean_confidence: float
    observed_pass_rate: float


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class ShadowReport:
    gate_id: str
    total: int
    labelled: int
    errors: int
    by_pair: dict[tuple[str, str], int]          # (model_decision, human_label) -> count, labelled rows only
    label_counts: dict[str, int]
    rarer_label: int
    agreement: float | None                      # labelled rows where model and human agree (errors count as 'escalate')
    auto_pass: int                               # labelled rows the gate would have auto-passed
    auto_pass_disagreements: int                 # ... of which a person said it needed review
    auto_pass_disagreement_rate: float | None
    ece: float | None
    reliability: list[ReliabilityBin] = field(default_factory=list)
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None

    @property
    def error_rate(self) -> float | None:
        return self.errors / self.total if self.total else None

    def promotion_checks(self) -> list[Check]:
        """The evidence-based criteria this report can speak to. The rest (a rule baseline beaten, two clean
        weeks, a named owner) are recorded on the calibration itself."""
        d = self.auto_pass_disagreement_rate
        return [
            Check("labels", self.labelled >= MIN_LABELS, f"{self.labelled} labelled, need {MIN_LABELS}"),
            Check("rarer label", self.rarer_label >= MIN_RARER_LABEL, f"{self.rarer_label} of the rarer label, need {MIN_RARER_LABEL}"),
            Check("calibration error", self.ece is not None and self.ece <= MAX_ECE,
                  "no auto-passed decisions yet" if self.ece is None else f"ECE {self.ece:.3f}, need at most {MAX_ECE}"),
            Check("auto-pass disagreement", d is not None and d < MAX_AUTO_PASS_DISAGREEMENT,
                  "no auto-passed decisions yet" if d is None else f"{d:.1%} of auto-passes disagreed, need under {MAX_AUTO_PASS_DISAGREEMENT:.0%}"),
        ]

    @property
    def ready(self) -> bool:
        return all(c.ok for c in self.promotion_checks())


def _percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return ordered[lo] if lo == hi else ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def reliability_bins(outcomes: Iterable[Outcome], bins: int = BINS) -> list[ReliabilityBin]:
    """Confidence against how often a person agreed the row could pass, over the decisions the gate would
    have auto-passed and that a person has resolved. Empty bins are omitted."""
    rows = [o for o in outcomes if o.would_auto_pass and o.human_label is not None]
    out = []
    for i in range(bins):
        low, high = i / bins, (i + 1) / bins
        in_bin = [o for o in rows if low <= o.confidence < high or (i == bins - 1 and o.confidence == 1.0)]
        if in_bin:
            out.append(ReliabilityBin(low, high, len(in_bin),
                                      sum(o.confidence for o in in_bin) / len(in_bin),
                                      sum(o.human_label == "pass" for o in in_bin) / len(in_bin)))
    return out


def expected_calibration_error(bins: Sequence[ReliabilityBin]) -> float | None:
    n = sum(b.n for b in bins)
    if not n:
        return None
    return sum(abs(b.observed_pass_rate - b.mean_confidence) * b.n for b in bins) / n


def build_report(gate_id: str, outcomes: Sequence[Outcome]) -> ShadowReport:
    labelled = [o for o in outcomes if o.human_label is not None]
    pairs: dict[tuple[str, str], int] = {}
    for o in labelled:
        pairs[(o.model_decision, o.human_label)] = pairs.get((o.model_decision, o.human_label), 0) + 1
    labels = {k: sum(1 for o in labelled if o.human_label == k) for k in ("pass", "escalate")}
    # An error escalates, so it agrees with a person who also wanted review.
    agree = sum(1 for o in labelled if (o.model_decision == "pass") == (o.human_label == "pass"))
    auto = [o for o in labelled if o.would_auto_pass]
    bad = sum(1 for o in auto if o.human_label == "escalate")
    bins = reliability_bins(outcomes)
    latencies = [o.latency_ms for o in outcomes if o.latency_ms is not None]
    return ShadowReport(
        gate_id=gate_id, total=len(outcomes), labelled=len(labelled),
        errors=sum(1 for o in outcomes if o.model_decision == "error"),
        by_pair=pairs, label_counts=labels, rarer_label=min(labels.values()) if labelled else 0,
        agreement=agree / len(labelled) if labelled else None,
        auto_pass=len(auto), auto_pass_disagreements=bad,
        auto_pass_disagreement_rate=bad / len(auto) if auto else None,
        ece=expected_calibration_error(bins), reliability=bins,
        latency_p50_ms=_percentile(latencies, 0.5), latency_p95_ms=_percentile(latencies, 0.95))


def fetch_outcomes(conn: Connection, gate_id: str, *, since: datetime | None = None,
                   shadow_only: bool = True) -> list[Outcome]:
    """Outcomes visible to the caller's session. `shadow_only` keeps the report to evaluations made while the
    gate escalated everything: after a gate enforces, its own decisions shape what a person sees, so the human
    label is no longer an independent check."""
    rows = conn.execute(text(
        "SELECT model_decision, confidence, threshold, human_label, latency_ms, created_at, approval_request_id "
        "FROM app.gate_shadow_outcome WHERE gate_id = :g AND (CAST(:since AS timestamptz) IS NULL OR created_at >= :since) "
        "AND (NOT :shadow OR mode = 'shadow') ORDER BY created_at"),
        {"g": gate_id, "since": since, "shadow": shadow_only}).all()
    return [Outcome(r.model_decision, float(r.confidence) if r.confidence is not None else None, float(r.threshold),
                    r.human_label, r.latency_ms, r.created_at, r.approval_request_id) for r in rows]


def shadow_report(conn: Connection, gate_id: str, *, since: datetime | None = None) -> ShadowReport:
    return build_report(gate_id, fetch_outcomes(conn, gate_id, since=since))


def render(report: ShadowReport) -> str:
    """A plain-text summary for a person reading it in a terminal or a ticket."""
    def pct(x): return "n/a" if x is None else f"{x:.1%}"
    lines = [f"Shadow report: {report.gate_id}",
             f"  evaluations {report.total}, labelled {report.labelled}, errors {report.errors} ({pct(report.error_rate)})",
             f"  labels: pass {report.label_counts.get('pass', 0)}, escalate {report.label_counts.get('escalate', 0)}",
             f"  agreement with the human decision: {pct(report.agreement)}",
             f"  would have auto-passed {report.auto_pass}; a person disagreed with {report.auto_pass_disagreements} "
             f"({pct(report.auto_pass_disagreement_rate)})",
             f"  calibration error (auto-passed decisions): {'n/a' if report.ece is None else f'{report.ece:.3f}'}"]
    if report.latency_p50_ms is not None:
        lines.append(f"  latency p50 {report.latency_p50_ms:.0f} ms, p95 {report.latency_p95_ms:.0f} ms")
    lines.append("  promotion evidence:")
    lines += [f"    [{'x' if c.ok else ' '}] {c.name}: {c.detail}" for c in report.promotion_checks()]
    lines.append("  also needed (recorded on the calibration): a rule baseline beaten, two clean shadow weeks, a named owner.")
    return "\n".join(lines)
