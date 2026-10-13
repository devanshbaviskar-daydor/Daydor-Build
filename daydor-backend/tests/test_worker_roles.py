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


# ---------------------------------------------------------------- step 2: app.worker_tenant_policy
def _default_autonomy(engine, worker):
    with engine.connect() as conn:
        return conn.execute(text("SELECT autonomy FROM app.worker_definition WHERE worker = :w"),
                            {"w": worker}).scalar_one()


def _set_policy(engine, tenant, worker, autonomy=None, enabled=True, role="tenant_hr"):
    with tenant_session(engine, role, tenant) as conn:
        conn.execute(text("INSERT INTO app.worker_tenant_policy (worker, autonomy, enabled) VALUES (:w, :a, :e) "
                          "ON CONFLICT (tenant_id, worker) DO UPDATE SET autonomy = EXCLUDED.autonomy, "
                          "enabled = EXCLUDED.enabled"), {"w": worker, "a": autonomy, "e": enabled})


def _clear_policy(engine, tenant, worker):
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL ROLE daydor_schema_owner"))
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
        conn.execute(text("DELETE FROM app.worker_tenant_policy WHERE tenant_id = :t AND worker = :w"),
                     {"t": tenant, "w": worker})


def test_tenant_can_lower_autonomy_toward_approve(engine, org):
    assert _default_autonomy(engine, "gross-pay-calculator") == "auto"
    for level in ("review", "approve"):
        _set_policy(engine, org.tenant_a, "gross-pay-calculator", level)
        with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
            assert conn.execute(text("SELECT app.worker_effective_autonomy('gross-pay-calculator')")).scalar_one() == level
    _clear_policy(engine, org.tenant_a, "gross-pay-calculator")


def test_tenant_cannot_raise_autonomy_above_the_default(engine, org):
    assert _default_autonomy(engine, "employee-record-writer") == "review"
    with pytest.raises(DBAPIError, match="cannot raise autonomy"):
        _set_policy(engine, org.tenant_a, "employee-record-writer", "auto")
    assert _default_autonomy(engine, "direct-deposit-disburser") == "approve"
    for level in ("auto", "review"):
        with pytest.raises(DBAPIError, match="cannot raise autonomy"):
            _set_policy(engine, org.tenant_a, "direct-deposit-disburser", level)
    # an update that lowers it again is also refused
    _set_policy(engine, org.tenant_a, "employee-record-writer", "approve")
    with pytest.raises(DBAPIError, match="cannot raise autonomy"):
        _set_policy(engine, org.tenant_a, "employee-record-writer", "auto")
    _clear_policy(engine, org.tenant_a, "employee-record-writer")


def test_mutation_the_trigger_is_what_stops_a_raise(engine, org):
    """With the guard trigger off, the same insert succeeds: the rule lives in that trigger."""
    with engine.connect() as conn:
        trans = conn.begin()
        conn.execute(text("SET LOCAL ROLE daydor_schema_owner"))
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(org.tenant_a)})
        conn.execute(text("ALTER TABLE app.worker_tenant_policy DISABLE TRIGGER worker_tenant_policy_guard"))
        conn.execute(text("INSERT INTO app.worker_tenant_policy (tenant_id, worker, autonomy) "
                          "VALUES (:t, 'direct-deposit-disburser', 'auto')"), {"t": org.tenant_a})
        trans.rollback()


def test_platform_actors_and_unknown_workers_cannot_be_overridden(engine, org):
    with pytest.raises(DBAPIError, match="platform actor"):
        _set_policy(engine, org.tenant_a, "workflow-engine", None, enabled=False)
    with pytest.raises(DBAPIError, match="foreign key|unknown worker"):
        _set_policy(engine, org.tenant_a, "no-such-worker", "approve")


def test_policy_is_tenant_isolated_and_role_limited(engine, org):
    _set_policy(engine, org.tenant_a, "gl-poster", "approve")
    with tenant_session(engine, "tenant_hr", org.tenant_b) as conn:
        assert conn.execute(text("SELECT count(*) FROM app.worker_tenant_policy")).scalar_one() == 0
    with pytest.raises(DBAPIError, match="permission denied"):
        _set_policy(engine, org.tenant_a, "gl-poster", "approve", role="tenant_employee")
    with pytest.raises(DBAPIError, match="permission denied"):
        _set_policy(engine, org.tenant_a, "gl-poster", "approve", role="tenant_manager")
    _clear_policy(engine, org.tenant_a, "gl-poster")


def test_disabled_worker_fails_the_check_globally_and_per_tenant(engine, org):
    with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
        assert conn.execute(text("SELECT app.assert_worker_enabled('gl-poster')")).scalar_one() == "approve"
    _set_policy(engine, org.tenant_a, "gl-poster", None, enabled=False)
    try:
        with pytest.raises(DBAPIError, match="disabled for this tenant"):
            with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
                conn.execute(text("SELECT app.assert_worker_enabled('gl-poster')"))
        with tenant_session(engine, "tenant_hr", org.tenant_b) as conn:      # other tenants unaffected
            conn.execute(text("SELECT app.assert_worker_enabled('gl-poster')"))
    finally:
        _clear_policy(engine, org.tenant_a, "gl-poster")
    with tenant_session(engine, "daydor_ops") as conn:
        conn.execute(text("UPDATE app.worker_definition SET enabled = false WHERE worker = 'gl-poster'"))
    try:
        with pytest.raises(DBAPIError, match="worker gl-poster is disabled"):
            with tenant_session(engine, "tenant_hr", org.tenant_b) as conn:
                conn.execute(text("SELECT app.assert_worker_enabled('gl-poster')"))
    finally:
        with tenant_session(engine, "daydor_ops") as conn:
            conn.execute(text("UPDATE app.worker_definition SET enabled = true WHERE worker = 'gl-poster'"))
    with pytest.raises(DBAPIError, match="unknown worker"):
        with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
            conn.execute(text("SELECT app.assert_worker_enabled('nope')"))
