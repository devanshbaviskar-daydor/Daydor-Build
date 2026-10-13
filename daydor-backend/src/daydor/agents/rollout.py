"""Rollout of an LLM worker, per tenant (migration 0043): shadow, canary, ga.

    shadow  the proposal is recorded next to everything else a run records, and never applied. Where every worker starts.
    canary  the proposal is applied, but a person acknowledges every run before the next step moves (as if autonomy were `review`).
    ga      the worker acts at its own autonomy.

A worker moves forward only on evidence, enforced by the database (see app.worker_rollout_guard): canary needs a passing eval on the
exact prompt in force; ga needs a passing live eval, a canary on that same prompt, and a clean canary period. A new prompt version drops
the worker back to shadow, and a tenant can always step a worker back.

Workers that are not built LLM workers have no rollout: `stage_for` says `ga` for them.
"""
from __future__ import annotations

import json

from sqlalchemy import Connection, text

from daydor.agents.harness.client import model_for_tier
from daydor.agents.roles import worker_records

STAGES = ("shadow", "canary", "ga")


def _record(worker: str) -> dict:
    return next(r for r in worker_records() if r["worker"] == worker)


def prompt_sha(worker: str) -> str:
    return _record(worker)["contract"]["prompt_sha256"]


def models_in_force(worker: str) -> dict:
    """What a live eval has to have been run against: the worker's tier and the model that tier names today."""
    tier = _record(worker)["llm_tier"]
    return {"tier": tier, "model": model_for_tier(tier)}


def stage_for(conn: Connection, worker: str) -> str:
    from daydor.agents.runs import is_llm
    if not is_llm(worker):
        return "ga"
    return conn.execute(text("SELECT app.worker_rollout_stage(:w, :s)"), {"w": worker, "s": prompt_sha(worker)}).scalar_one()


def promote(conn: Connection, worker: str, stage: str) -> str:
    """Daydor ops, in the tenant's session. The database refuses it without the evidence; this also refuses a live eval that was run
    against a different model than the one now in force."""
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}")
    models = models_in_force(worker)
    if stage == "ga":
        ok = conn.execute(text("SELECT EXISTS (SELECT 1 FROM app.worker_eval_result WHERE worker = :w AND prompt_sha256 = :s AND passed "
                               "AND mode = 'live' AND models @> CAST(:m AS jsonb))"),
                          {"w": worker, "s": prompt_sha(worker), "m": json.dumps(models)}).scalar_one()
        if not ok:
            raise PermissionError(f"{worker}: no passing live eval on file for model {models['model']} and this prompt")
    return conn.execute(text("SELECT app.set_worker_rollout(:w, :st, :s, CAST(:m AS jsonb))"),
                        {"w": worker, "st": stage, "s": None if stage == "shadow" else prompt_sha(worker),
                         "m": None if stage == "shadow" else json.dumps(models)}).scalar_one()


def demote(conn: Connection, worker: str) -> str:
    return conn.execute(text("SELECT app.demote_worker_rollout(:w)"), {"w": worker}).scalar_one()
