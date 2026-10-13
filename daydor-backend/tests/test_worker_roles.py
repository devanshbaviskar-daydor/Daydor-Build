"""Worker definitions and roles in the database (ADR-004, Phase 1).

The committed SQL is generated from registry/ and the model; these tests pin it to the live
schema and prove the rules can fail."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from daydor.agents import roles as W
from daydor.db.session import tenant_session


# ---------------------------------------------------------------- step 1: app.worker_definition
def test_committed_definition_sql_matches_the_registry():
    assert W.DEFINITION_SQL.read_text() == W.generate_definition_sql(), \
        "registry changed: run `python -m daydor.agents.roles` and add a migration"


def test_worker_definition_has_one_row_per_worker_and_actor(engine, org):
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT worker, role_name, kind, platform_actor FROM app.worker_definition")).all()
    expected = {r["worker"] for r in W.worker_records()}
    assert {r.worker for r in rows} == expected
    assert len(rows) == 89 + 2
    assert {r.worker for r in rows if r.platform_actor} == {"workflow-engine", "root-orchestrator"}
    assert all(r.role_name == W.role_name(r.worker) for r in rows)


def test_worker_definition_matches_the_registry_fields(engine, org):
    by = {r["worker"]: r for r in W.worker_records()}
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT worker, home_domain, kind, effect, autonomy, owner, wave, writes, reads, "
                                 "flags, enabled FROM app.worker_definition")).all()
    for r in rows:
        want = by[r.worker]
        assert (r.home_domain, r.kind, r.effect, r.autonomy, r.owner, r.wave) == (
            want["home_domain"], want["kind"], want["effect"], want["autonomy"], want["owner"], want["wave"])
        assert sorted(r.writes) == sorted(want["writes"]) and sorted(r.reads) == sorted(want["reads"])
        assert sorted(r.flags) == sorted(want.get("flags", []))
        assert r.enabled is True


def test_soft_gate_column_only_holds_registered_gates(engine, org):
    with engine.connect() as conn:
        sg = dict(conn.execute(text("SELECT worker, soft_gate FROM app.worker_definition "
                                    "WHERE soft_gate IS NOT NULL")).all())
        proposed = conn.execute(text("SELECT soft_gate_proposed FROM app.worker_definition "
                                     "WHERE worker = 'expense-policy-checker'")).scalar_one()
    assert sg == {"payroll-anomaly-detector": "sg_payroll_anomaly_precheck",
                  "app-access-exception-flagger": "sg_access_request_precheck"}
    assert proposed.startswith("sg_expense_policy_precheck")


def test_only_enabled_can_change_and_only_ops_can_change_it(engine, org):
    with tenant_session(engine, "daydor_ops") as conn:
        conn.execute(text("UPDATE app.worker_definition SET enabled = false WHERE worker = 'gl-poster'"))
        conn.execute(text("UPDATE app.worker_definition SET enabled = true WHERE worker = 'gl-poster'"))
    with pytest.raises(DBAPIError, match="permission denied"):
        with tenant_session(engine, "daydor_ops") as conn:
            conn.execute(text("UPDATE app.worker_definition SET autonomy = 'auto' WHERE worker = 'gl-poster'"))
    with pytest.raises(DBAPIError, match="permission denied"):
        with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
            conn.execute(text("UPDATE app.worker_definition SET enabled = false WHERE worker = 'gl-poster'"))
    with pytest.raises(DBAPIError, match="only worker_definition.enabled may change|permission denied"):
        with engine.begin() as conn:      # even the owner cannot change registry fields at runtime
            conn.execute(text("SET LOCAL ROLE daydor_schema_owner"))
            conn.execute(text("UPDATE app.worker_definition SET autonomy = 'auto' WHERE worker = 'gl-poster'"))
    with pytest.raises(DBAPIError, match="never deleted|permission denied"):
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL ROLE daydor_schema_owner"))
            conn.execute(text("DELETE FROM app.worker_definition WHERE worker = 'gl-poster'"))
