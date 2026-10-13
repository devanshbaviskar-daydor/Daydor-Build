"""Calibration pipeline for soft gates (ADR-005): fit, measure on held-out data, record, export.

Laya checkpoints ship over-confident, so a gate may not enforce until a calibration has been fitted on our own
labelled data and approved. This module does the fitting and the measuring; approval is a person's sign-off on
`app.gate_calibration`, and the database refuses `approved` unless the promotion criteria hold.

  fit_temperature      one temperature per question, from labelled shadow decisions (p ** (1/T), renormalised)
  propose_calibration  fit on the earlier rows, measure on the latest, record a *candidate* row
  export_examples      the labelled inputs behind a gate, for fine-tuning: this tenant only
  export_pooled        ... across tenants, only those that opted in (ADR-006), and it says who was left out

Nothing here changes a gate's mode.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Sequence
from uuid import UUID

from sqlalchemy import Connection, Engine, text

from daydor.db.session import tenant_session
from daydor.gates.report import Outcome, build_report, expected_calibration_error, reliability_bins

EPS = 1e-9
T_GRID = [round(0.25 + 0.05 * i, 2) for i in range(0, 156)]       # 0.25 .. 8.0


@dataclass(frozen=True)
class Sample:
    """One labelled decision: the model's probabilities for a question and the option a person's decision implies."""
    probabilities: Mapping[str, float]
    correct: str


def scale(probabilities: Mapping[str, float], temperature: float) -> dict[str, float]:
    """Temperature scaling from probabilities: p_i ** (1/T), renormalised. T > 1 softens, T < 1 sharpens."""
    powered = {k: max(v, EPS) ** (1.0 / temperature) for k, v in probabilities.items()}
    total = sum(powered.values())
    return {k: v / total for k, v in powered.items()}


def negative_log_likelihood(samples: Sequence[Sample], temperature: float) -> float:
    return -sum(math.log(max(scale(s.probabilities, temperature).get(s.correct, EPS), EPS)) for s in samples) / len(samples)


def fit_temperature(samples: Sequence[Sample]) -> float:
    """The temperature on a fixed grid that minimises negative log-likelihood. Needs both outcomes present, or it
    would simply push the model toward whatever the single label was."""
    if not samples:
        raise ValueError("no labelled samples to fit")
    if len({s.correct for s in samples}) < 2:
        raise ValueError("every label is the same; a temperature cannot be fitted from one class")
    return min(T_GRID, key=lambda t: negative_log_likelihood(samples, t))


def samples_from_outcomes(rows: Sequence[Mapping[str, Any]], question: str, pass_option: str,
                          review_option: str) -> list[Sample]:
    """Labelled rows (as app.gate_shadow_outcome returns them, with `output` and `human_label`) to samples.
    A human 'pass' means the pass option was right; 'escalate' means the review option was."""
    out = []
    for r in rows:
        if r.get("human_label") is None or not r.get("output"):
            continue
        answer = (r["output"] or {}).get(question)
        if not answer or "probabilities" not in answer:
            continue
        out.append(Sample(answer["probabilities"], pass_option if r["human_label"] == "pass" else review_option))
    return out


def calibrated_outcomes(outcomes: Sequence[Outcome], probabilities: Sequence[Mapping[str, float] | None],
                        pass_option: str, temperature: float) -> list[Outcome]:
    """The same decisions with confidence recomputed under `temperature`, for measuring a candidate."""
    new = []
    for o, probs in zip(outcomes, probabilities):
        if probs is None or o.model_decision == "error":
            new.append(o)
            continue
        scaled = scale(probs, temperature)
        top = max(scaled, key=scaled.get)
        new.append(Outcome("pass" if top == pass_option else "escalate", scaled[top], o.threshold, o.human_label,
                           o.latency_ms, o.created_at, o.approval_request_id))
    return new


def with_threshold(outcomes: Sequence[Outcome], threshold: float) -> list[Outcome]:
    return [Outcome(o.model_decision, o.confidence, threshold, o.human_label, o.latency_ms, o.created_at,
                    o.approval_request_id) for o in outcomes]


def choose_threshold(outcomes: Sequence[Outcome], *, max_disagreement: float = 0.0099, min_support: int = 20,
                     floor: float = 0.5) -> float | None:
    """The lowest threshold at which the decisions the gate would auto-pass are ones a person agreed with often
    enough (under 1%), with at least `min_support` of them so the rate is not an accident. None when there is
    no such threshold: the gate does not earn enforcement on this evidence. ADR-003: the threshold comes from
    the shadow data, not from a guess."""
    for step in range(int(floor * 100), 100):
        threshold = step / 100
        rep = build_report("", with_threshold(outcomes, threshold))
        if (rep.auto_pass >= min_support and rep.auto_pass_disagreement_rate is not None
                and rep.auto_pass_disagreement_rate <= max_disagreement):
            return threshold
    return None


def apply_temperatures(result, temperatures: Mapping[str, float]):
    """A DeciderResult with each choice question's probabilities scaled by its fitted temperature, and the
    answer's confidence (max probability) recomputed. The runner calls this before it thresholds, so a recorded
    calibration is what actually decides. Questions without a temperature, and score answers (an expected
    value, not a choice), pass through unchanged."""
    from daydor.gates.decider import Answer, DeciderResult
    answers = {}
    for name, a in result.answers.items():
        t = temperatures.get(name)
        if not t or not isinstance(a.value, str):
            answers[name] = a
            continue
        scaled = scale(a.probabilities, float(t))
        top = max(scaled, key=scaled.get)
        answers[name] = Answer(top, scaled, scaled[top])
    return DeciderResult(answers, result.engine, result.engine_version, result.raw)


@dataclass(frozen=True)
class Candidate:
    version: str
    temperature: float
    threshold: float | None
    n_fit: int
    n_holdout: int
    n_labels: int
    n_rarer_label: int
    ece_before: float | None
    ece_after: float | None
    disagreement_rate: float | None


def propose_calibration(conn: Connection, *, gate_id: str, version: str, question: str, pass_option: str,
                        review_option: str, rows: Sequence[Mapping[str, Any]], checkpoint: str,
                        engine_version: str | None, rule_baseline_beaten: bool, shadow_clean_since: date | None,
                        holdout_fraction: float = 0.3) -> Candidate:
    """Fits on the earlier labelled rows and measures on the latest, so the numbers on the candidate are not
    the ones it was fitted to. Records a *candidate*: an owner approves it separately, and the database
    refuses the approval unless the criteria are met. `rows` come oldest first (fetch_rows below)."""
    labelled = [r for r in rows if r.get("human_label") is not None and r.get("output")]
    if len(labelled) < 4:
        raise ValueError("too few labelled rows to split into fit and holdout")
    cut = max(1, int(len(labelled) * (1 - holdout_fraction)))
    fit_rows, hold_rows = labelled[:cut], labelled[cut:]
    temperature = fit_temperature(samples_from_outcomes(fit_rows, question, pass_option, review_option))

    def outcomes(rs):
        return [Outcome(r["model_decision"], float(r["confidence"]) if r["confidence"] is not None else None,
                        float(r["threshold"]), r["human_label"]) for r in rs]
    probs = [((r["output"] or {}).get(question) or {}).get("probabilities") for r in hold_rows]
    before = outcomes(hold_rows)
    after = calibrated_outcomes(before, probs, pass_option, temperature)
    ece_before = expected_calibration_error(reliability_bins(before))
    # The threshold comes from the fit rows after calibration; the holdout is measured at it.
    fit_probs = [((r["output"] or {}).get(question) or {}).get("probabilities") for r in fit_rows]
    fit_after = calibrated_outcomes(outcomes(fit_rows), fit_probs, pass_option, temperature)
    threshold = choose_threshold(fit_after)
    after = with_threshold(after, threshold if threshold is not None else 1.0)
    report_after = build_report(gate_id, after)
    all_labels = build_report(gate_id, outcomes(labelled))
    conn.execute(text(
        "INSERT INTO app.gate_calibration (version, gate_id, checkpoint, engine_version, n_labels, n_rarer_label, ece, "
        "rule_baseline_beaten, disagreement_rate, auto_pass_threshold, shadow_clean_since, temperatures, note) "
        "VALUES (:v, :g, :c, :ev, :n, :r, :ece, :rb, :dis, :thr, :since, CAST(:t AS jsonb), :note)"),
        {"v": version, "g": gate_id, "c": checkpoint, "ev": engine_version, "n": all_labels.labelled,
         "r": all_labels.rarer_label,
         # No auto-passed decision on the holdout means nothing supports the claim: record the worst case.
         "ece": report_after.ece if report_after.ece is not None else 1.0,
         "rb": rule_baseline_beaten,
         "dis": report_after.auto_pass_disagreement_rate if report_after.auto_pass_disagreement_rate is not None else 1.0,
         "thr": threshold if threshold is not None else 1.0,
         "since": shadow_clean_since, "t": json.dumps({question: temperature}),
         "note": (f"fitted on {len(fit_rows)} rows, measured on the latest {len(hold_rows)}"
                  + ("" if threshold is not None else "; no threshold meets the disagreement limit, so none is proposed"))})
    return Candidate(version, temperature, threshold, len(fit_rows), len(hold_rows), all_labels.labelled, all_labels.rarer_label,
                     ece_before, report_after.ece, report_after.auto_pass_disagreement_rate)


def fetch_rows(conn: Connection, gate_id: str) -> list[dict]:
    """Labelled shadow rows for a gate, oldest first, as the caller's session may see them."""
    return [dict(r._mapping) for r in conn.execute(text(
        "SELECT model_decision, confidence, threshold, human_label, output, created_at FROM app.gate_shadow_outcome "
        "WHERE gate_id = :g AND mode = 'shadow' AND human_label IS NOT NULL AND output IS NOT NULL "
        "ORDER BY created_at"), {"g": gate_id})]


def compare_to_baseline(model_correct: Sequence[bool], baseline_correct: Sequence[bool]) -> bool:
    """The model has to beat the rule on the same held-out rows, or the rule wins and the model is not needed."""
    if len(model_correct) != len(baseline_correct) or not model_correct:
        raise ValueError("compare on the same, non-empty set of rows")
    return sum(model_correct) > sum(baseline_correct)


def zscore_flags(values: Sequence[float], history: Sequence[float], k: float = 3.0) -> list[bool]:
    """The simple baseline a payroll gate must beat: flag a value more than k standard deviations from the mean of
    its own history."""
    if len(history) < 2:
        raise ValueError("need at least two historical values")
    mean = sum(history) / len(history)
    sd = math.sqrt(sum((x - mean) ** 2 for x in history) / (len(history) - 1)) or EPS
    return [abs(v - mean) / sd > k for v in values]


# ----------------------------------------------------------------------------- the example store
def export_examples(conn: Connection, gate_id: str) -> list[dict]:
    """Labelled inputs for this session's tenant only (ops or admin). Fine-tuning data for a gate's model."""
    return [dict(r._mapping) for r in conn.execute(text(
        "SELECT evaluation_id, input, label, labelled_at FROM app.gate_example "
        "WHERE gate_id = :g AND label IS NOT NULL ORDER BY labelled_at"), {"g": gate_id})]


@dataclass(frozen=True)
class PooledExport:
    examples: list[dict]
    included: list[UUID]
    excluded: list[UUID]


def export_pooled(engine: Engine, gate_id: str, tenant_ids: Sequence[UUID]) -> PooledExport:
    """Examples across tenants, from only those that opted in to pooling (ADR-006). A tenant with no policy row,
    or one that says no, is left out and reported, never silently included."""
    examples, included, excluded = [], [], []
    for tid in tenant_ids:
        with tenant_session(engine, "daydor_ops", tid) as conn:
            allowed = conn.execute(text("SELECT allow_pooling FROM app.tenant_training_policy WHERE tenant_id = :t"),
                                   {"t": tid}).scalar_one_or_none()
            if not allowed:
                excluded.append(tid)
                continue
            included.append(tid)
            examples += [{**e, "tenant_id": tid} for e in export_examples(conn, gate_id)]
    return PooledExport(examples, included, excluded)
