"""Decider interface and the Laya client, using answer shapes taken from laya 0.4.6's source
(agent.py _decode_answers). No model is loaded: a fake predictor stands in for Router.predict."""
import pytest

from daydor.gates.decider import (MAX_OPTIONS, Choice, DecisionSchema, DeciderMalformed, DeciderTruncated,
                                  DeciderUnavailable, LayaClient, Score, Truth, render_question)


def choice_answer(choice, probs, *, answer_confidence=None, entropy_confidence=0.31, act=1.0):
    return {"type": "choice", "choice": choice, "probabilities": probs, "confidence": entropy_confidence,
            "answer_confidence": max(probs.values()) if answer_confidence is None else answer_confidence,
            "action": {"act_probability": act}}


def raw(answers, usage=None, repo="convaiinnovations/laya"):
    return {"answers": answers, "routing": {"model": "english", "repo": repo, "reason": "latin script"},
            "usage": usage or {"input_tokens": 140}}


SCHEMA = DecisionSchema("grant_fit", "1", (
    Choice("grant_fits_role", "Is this grant consistent with the person's role?",
           {"consistent": "access normally given to this role", "inconsistent": "access not normally given"}),
    Score("risk", "How risky is this access?", ("low", "medium", "high")),
    Truth("privileged", "Does this grant give admin rights?", yes="yes, it grants admin rights",
          no="no admin rights"),
))


def client(answers, **kw):
    seen = {}

    def predictor(state, questions, **k):
        seen.update(state=state, questions=questions, kwargs=k)
        return raw(answers) if isinstance(answers, dict) and "answers" not in answers else answers

    return LayaClient(predictor, **kw), seen


GOOD = {
    "grant_fits_role": choice_answer("consistent", {"consistent": 0.9, "inconsistent": 0.1}),
    "risk": {"type": "score", "score": 0.4, "legend": {"0": "low", "1": "medium", "2": "high"},
             "probabilities": {"0": 0.6, "1": 0.35, "2": 0.05}, "confidence": 0.5, "answer_confidence": 0.6,
             "action": {"act_probability": 1.0}},
    "privileged": choice_answer("B", {"A": 0.15, "B": 0.85}),
}


def test_schema_validation():
    with pytest.raises(ValueError):
        Choice("c", "pick", {"only": "one option"})
    with pytest.raises(ValueError):
        Choice("c", "pick", {str(i): "x" for i in range(MAX_OPTIONS + 1)})
    with pytest.raises(ValueError):
        Choice("c", "pick", {"a": "", "b": "x"})
    with pytest.raises(ValueError):
        Score("s", "rate", ("same", "same"))
    with pytest.raises(ValueError):
        DecisionSchema("dup", "1", (Truth("t", "q"), Truth("t", "q2")))
    with pytest.raises(ValueError):
        DecisionSchema("empty", "1", ())


def test_truth_is_sent_as_a_two_option_choice_with_neutral_keys():
    q = render_question(Truth("p", "Is it admin?", yes="yes admin", no="no admin"))
    assert q == {"type": "choice", "instructions": "Is it admin?", "criteria": {"A": "yes admin", "B": "no admin"}}
    assert render_question(Truth("p", "Is it admin?"), "noul") == {"type": "noul", "instructions": "Is it admin?"}


def test_choice_score_and_truth_parse_with_calibrated_confidence():
    c, seen = client(GOOD)
    res = c.decide(SCHEMA, {"role": "analyst"}, 2.0)
    assert seen["questions"]["risk"] == {"type": "score", "instructions": "How risky is this access?",
                                         "criteria": ["low", "medium", "high"]}
    a = res.answers
    assert (a["grant_fits_role"].value, a["grant_fits_role"].confidence) == ("consistent", 0.9)
    assert a["risk"].value == 0.4 and a["risk"].confidence == 0.6
    assert a["privileged"].value == "false" and a["privileged"].probabilities == {"true": 0.15, "false": 0.85}
    assert res.engine == "laya" and res.engine_version.startswith("convaiinnovations/laya@")


def test_noul_rendering_maps_back_to_a_probability():
    schema = DecisionSchema("t", "1", (Truth("flag", "Is it urgent?"),))
    c, _ = client({"flag": {"type": "noul", "noul": 0.82, "confidence": 0.82, "answer_confidence": 0.82,
                            "action": {"act_probability": 1.0}}}, truth_render="noul")
    ans = c.decide(schema, "state", 2.0).answers["flag"]
    assert ans.value == "true" and ans.probabilities["true"] == 0.82


def test_gates_threshold_on_answer_confidence_not_entropy_or_act_probability():
    low = dict(GOOD, grant_fits_role=choice_answer(
        "consistent", {"consistent": 0.55, "inconsistent": 0.45}, entropy_confidence=0.99, act=1.0))
    c, _ = client(low)
    assert c.decide(SCHEMA, {"x": 1}, 2.0).answers["grant_fits_role"].confidence == 0.55


@pytest.mark.parametrize("mutate,message", [
    (lambda a: a.pop("risk"), "no answer for question 'risk'"),
    (lambda a: a["grant_fits_role"].update(choice="made_up"), "is not an option"),
    (lambda a: a["grant_fits_role"].update(probabilities={"consistent": 0.9, "inconsistent": 0.5}),
     "do not form a distribution"),
    (lambda a: a["grant_fits_role"].update(probabilities={"consistent": 1.0}), "probabilities keys"),
    (lambda a: a["risk"].update(score=7.0), "outside the scale"),
    (lambda a: a["grant_fits_role"].update(answer_confidence=1.4), "outside"),
])
def test_malformed_answers_are_rejected(mutate, message):
    answers = {k: dict(v) for k, v in GOOD.items()}
    mutate(answers)
    c, _ = client(answers)
    with pytest.raises(DeciderMalformed, match=message):
        c.decide(SCHEMA, {"x": 1}, 2.0)


def test_truncation_reported_by_the_model_fails_closed():
    c, _ = client(raw(GOOD, usage={"input_tokens": 512, "truncated": True}))
    with pytest.raises(DeciderTruncated):
        c.decide(SCHEMA, {"x": 1}, 2.0)


def test_oversized_state_is_refused_before_the_model_runs():
    calls = []
    c = LayaClient(lambda *a, **k: calls.append(1) or raw(GOOD), max_state_chars=50)
    with pytest.raises(DeciderTruncated):
        c.decide(SCHEMA, {"text": "x" * 200}, 2.0)
    assert calls == []


def test_unpinned_default_loader_fails_closed(monkeypatch):
    monkeypatch.delenv("LAYA_REVISION", raising=False)
    with pytest.raises(DeciderUnavailable, match="LAYA_REVISION"):
        LayaClient().decide(SCHEMA, {"x": 1}, 2.0)


def test_engine_version_records_the_pinned_revision(monkeypatch):
    monkeypatch.setenv("LAYA_REVISION", "55cf4c4")
    c, _ = client(GOOD)
    assert c.decide(SCHEMA, {"x": 1}, 2.0).engine_version == "convaiinnovations/laya@55cf4c4"
