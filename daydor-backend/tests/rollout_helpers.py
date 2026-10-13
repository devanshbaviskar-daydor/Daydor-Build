"""Test setup for a worker's rollout stage. Production only reaches canary and ga through the evidence checks in the database
(app.worker_rollout_guard, tested in test_agent_safety_ops.py); setup that is not about those checks skips the guard."""
from sqlalchemy import text

from daydor.agents import rollout


def place(engine, tenant, worker: str, stage: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = replica"))        # skips the guard trigger, for setup only
        conn.execute(text("DELETE FROM app.worker_rollout WHERE tenant_id = :t AND worker = :w"), {"t": tenant, "w": worker})
        sha = None if stage == "shadow" else rollout.prompt_sha(worker)
        conn.execute(text("INSERT INTO app.worker_rollout (tenant_id, worker, stage, prompt_sha256) VALUES (:t, :w, :s, :p)"),
                     {"t": tenant, "w": worker, "s": stage, "p": sha})
