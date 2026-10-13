"""Typed soft decisions: the engine-agnostic interface behind soft gates, and the Laya client.

Laya (convaiinnovations/laya, Apache-2.0) is a bidirectional encoder that reads a state plus typed
questions and returns typed answers with probabilities in one forward pass. It runs locally and
never generates text. Facts this module relies on (checked against laya 0.4.6 source):

* `choice`  -> {"choice", "probabilities", "confidence", "answer_confidence", "action"}
* `score`   -> {"score" (expected level), "legend", "probabilities", "confidence", "answer_confidence"}
* `noul`    -> {"noul" (P(true)), "confidence", "answer_confidence"}
* `answer_confidence` is max(p), the calibrated number to threshold on, comparable across question
  types. `confidence` is normalized entropy for choice/score, a different scale. We never use it.
* `action.act_probability` carries no usable signal (the model card reports AUROC 0.30). We ignore it.
* Anything past the token budget is silently cut off, so we fail closed on truncation.
* Checkpoints ship over-confident; calibration on our own data is required before a gate enforces
  (the database refuses mode='enforce' without a calibration_version).
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol

MAX_OPTIONS = 20            # accuracy falls off sharply above ~20 options at default head budgets
MAX_SCORE_LEVELS = 10
DEFAULT_MAX_STATE_CHARS = 1000   # ~320 state tokens on the English checkpoint; tune per gate
PROB_TOLERANCE = 0.02


class DeciderError(RuntimeError):
    """Any failure to get a trustworthy answer. Soft gates treat every subclass as 'escalate'."""


class DeciderUnavailable(DeciderError):
    pass


class DeciderTruncated(DeciderError):
    pass


class DeciderMalformed(DeciderError):
    pass


# ----------------------------------------------------------------------------- questions
def _nonblank(value: str, what: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{what} must be a non-empty string")


@dataclass(frozen=True)
class Choice:
    """Pick one option. Descriptions matter: the model reads them to tell options apart."""
    name: str
    instructions: str
    options: Mapping[str, str]

    def __post_init__(self) -> None:
        _nonblank(self.name, "name")
        _nonblank(self.instructions, f"{self.name}: instructions")
        if not 2 <= len(self.options) <= MAX_OPTIONS:
            raise ValueError(f"{self.name}: needs 2..{MAX_OPTIONS} options, got {len(self.options)}")
        for k, v in self.options.items():
            _nonblank(k, f"{self.name}: option key")
            _nonblank(v, f"{self.name}: description of {k!r}")


@dataclass(frozen=True)
class Score:
    """Rate on an ordered scale, lowest level first. The answer is the expected level."""
    name: str
    instructions: str
    levels: tuple[str, ...]

    def __post_init__(self) -> None:
        _nonblank(self.name, "name")
        _nonblank(self.instructions, f"{self.name}: instructions")
        if not 2 <= len(self.levels) <= MAX_SCORE_LEVELS or len(set(self.levels)) != len(self.levels):
            raise ValueError(f"{self.name}: needs 2..{MAX_SCORE_LEVELS} distinct levels")
        for level in self.levels:
            _nonblank(level, f"{self.name}: level")


@dataclass(frozen=True)
class Truth:
    """Yes/no with P(true). Sent to Laya as a two-option choice with neutral keys by default,
    because its `noul` primitive can follow its own 'false:'/'true:' labels instead of the state
    (laya issue #156). Describe both sides: `yes` and `no` are what the model reads."""
    name: str
    instructions: str
    yes: str = "yes"
    no: str = "no"

    def __post_init__(self) -> None:
        for v, w in ((self.name, "name"), (self.instructions, "instructions"), (self.yes, "yes"), (self.no, "no")):
            _nonblank(v, f"{self.name or 'truth'}: {w}")


Question = Choice | Score | Truth


@dataclass(frozen=True)
class DecisionSchema:
    name: str
    version: str
    questions: tuple[Question, ...]

    def __post_init__(self) -> None:
        names = [q.name for q in self.questions]
        if not names or len(set(names)) != len(names):
            raise ValueError(f"{self.name}: needs one or more questions with distinct names")


@dataclass(frozen=True)
class Answer:
    value: str | float          # choice key | expected score | "true"/"false" for Truth
    probabilities: dict[str, float]
    confidence: float           # answer_confidence = max(p): the number a gate thresholds on


@dataclass(frozen=True)
class DeciderResult:
    answers: dict[str, Answer]
    engine: str = "laya"
    engine_version: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class DeciderClient(Protocol):
    engine: str

    def decide(self, schema: DecisionSchema, state: Any, timeout_s: float) -> DeciderResult: ...


# ----------------------------------------------------------------------------- Laya
def render_question(q: Question, truth_render: str = "choice") -> dict[str, Any]:
    if isinstance(q, Choice):
        return {"type": "choice", "instructions": q.instructions, "criteria": dict(q.options)}
    if isinstance(q, Score):
        return {"type": "score", "instructions": q.instructions, "criteria": list(q.levels)}
    if truth_render == "noul":
        return {"type": "noul", "instructions": q.instructions}
    return {"type": "choice", "instructions": q.instructions, "criteria": {"A": q.yes, "B": q.no}}


def _confidence(a: Mapping[str, Any], probs: Mapping[str, float], name: str) -> float:
    c = a.get("answer_confidence")
    c = max(probs.values()) if c is None else c
    try:
        c = float(c)
    except (TypeError, ValueError) as exc:
        raise DeciderMalformed(f"{name}: unusable confidence {c!r}") from exc
    if math.isnan(c) or not 0.0 <= c <= 1.0:
        raise DeciderMalformed(f"{name}: confidence {c} outside [0, 1]")
    return c


def _probs(a: Mapping[str, Any], expected_keys: set[str], name: str) -> dict[str, float]:
    raw = a.get("probabilities")
    if not isinstance(raw, Mapping) or {str(k) for k in raw} != expected_keys:
        raise DeciderMalformed(f"{name}: probabilities keys {sorted(map(str, raw or {}))} != {sorted(expected_keys)}")
    probs = {str(k): float(v) for k, v in raw.items()}
    if any(math.isnan(v) or v < 0 for v in probs.values()) or abs(sum(probs.values()) - 1) > PROB_TOLERANCE:
        raise DeciderMalformed(f"{name}: probabilities do not form a distribution: {probs}")
    return probs


class LayaClient:
    """In-process Laya. `predictor` is `Router.predict`-shaped; tests inject a fake.

    The default loader refuses to run unless LAYA_REVISION is set (a commit SHA, or `reviewed` to use
    the library's reviewed pins), so a gate never silently runs different weights after an upstream
    change. Pair it with LAYA_SHA256_DIGESTS and HF_HUB_OFFLINE=1 in production images.
    """
    engine = "laya"

    def __init__(self, predictor: Callable[..., dict] | None = None, *, truth_render: str = "choice",
                 max_state_chars: int = DEFAULT_MAX_STATE_CHARS, model: str | None = None,
                 require_pinned_revision: bool = True) -> None:
        if truth_render not in ("choice", "noul"):
            raise ValueError("truth_render must be 'choice' or 'noul'")
        self._predictor = predictor
        self.truth_render, self.max_state_chars, self.model = truth_render, max_state_chars, model
        self.require_pinned_revision = require_pinned_revision

    def _predict(self) -> Callable[..., dict]:
        if self._predictor is not None:
            return self._predictor
        if self.require_pinned_revision and not os.environ.get("LAYA_REVISION"):
            raise DeciderUnavailable("LAYA_REVISION is not set: refusing to load unpinned checkpoints "
                                     "(set it to a commit SHA, or 'reviewed')")
        try:
            from laya import Router  # optional dependency: pip install 'daydor-backend[laya]'
        except ImportError as exc:
            raise DeciderUnavailable("laya is not installed (pip install 'daydor-backend[laya]')") from exc
        self._predictor = Router(preload=True).predict
        return self._predictor

    def decide(self, schema: DecisionSchema, state: Any, timeout_s: float) -> DeciderResult:
        # In-process inference cannot be pre-empted; the soft-gate runner enforces timeout_s afterwards.
        if len(json.dumps(state, default=str)) > self.max_state_chars:
            raise DeciderTruncated(f"state is over {self.max_state_chars} characters; the model would cut it off")
        predict = self._predict()
        questions = {q.name: render_question(q, self.truth_render) for q in schema.questions}
        raw = predict(state, questions, **({"model": self.model} if self.model else {}))
        return self._parse(schema, raw)

    def _parse(self, schema: DecisionSchema, raw: Mapping[str, Any]) -> DeciderResult:
        usage = raw.get("usage")
        if isinstance(usage, Mapping):
            for k, v in usage.items():
                if "trunc" in str(k).lower() and v:
                    raise DeciderTruncated(f"model reported truncation ({k}={v})")
        got = raw.get("answers")
        if not isinstance(got, Mapping):
            raise DeciderMalformed("response has no answers")
        answers: dict[str, Answer] = {}
        for q in schema.questions:
            a = got.get(q.name)
            if not isinstance(a, Mapping):
                raise DeciderMalformed(f"no answer for question {q.name!r}")
            if isinstance(q, Choice):
                probs = _probs(a, set(q.options), q.name)
                if a.get("choice") not in q.options:
                    raise DeciderMalformed(f"{q.name}: choice {a.get('choice')!r} is not an option")
                answers[q.name] = Answer(a["choice"], probs, _confidence(a, probs, q.name))
            elif isinstance(q, Score):
                probs = _probs(a, {str(i) for i in range(len(q.levels))}, q.name)
                score = float(a.get("score", math.nan))
                if math.isnan(score) or not 0 <= score <= len(q.levels) - 1:
                    raise DeciderMalformed(f"{q.name}: score {a.get('score')!r} outside the scale")
                answers[q.name] = Answer(score, probs, _confidence(a, probs, q.name))
            elif self.truth_render == "noul":
                p = float(a.get("noul", math.nan))
                if math.isnan(p) or not 0 <= p <= 1:
                    raise DeciderMalformed(f"{q.name}: noul {a.get('noul')!r} is not a probability")
                probs = {"true": p, "false": 1 - p}
                answers[q.name] = Answer("true" if p >= 0.5 else "false", probs, _confidence(a, probs, q.name))
            else:
                raw_p = _probs(a, {"A", "B"}, q.name)
                probs = {"true": raw_p["A"], "false": raw_p["B"]}
                answers[q.name] = Answer("true" if raw_p["A"] >= raw_p["B"] else "false", probs,
                                         _confidence(a, probs, q.name))
        routing = raw.get("routing") if isinstance(raw.get("routing"), Mapping) else {}
        revision = os.environ.get("LAYA_REVISION") or "unpinned"
        return DeciderResult(answers, "laya", f"{routing.get('repo', 'laya')}@{revision}", dict(raw))
