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
    assert len(rows) == 89 + 4
    assert {r.worker for r in rows if r.platform_actor} == {"workflow-engine", "root-orchestrator", "hire-intake",
                                                          "exit-intake"}
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
        assert r.enabled is (want.get("enabled_by_default") is not False)


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


# ---------------------------------------------------------------- steps 3 and 4: roles and grants
from daydor.model import load_model                                    # noqa: E402
from daydor.model.ddl import SYSTEM_MANAGED                            # noqa: E402
from daydor.model.loader import READ, WRITE                            # noqa: E402
from daydor.gates.registry import GUARDS                               # noqa: E402
from tests.test_access import _actual_column_privileges                # noqa: E402

GUARDED = {(t, c) for t, c, _ in GUARDS}


def _records():
    return list(W.worker_records())


def test_committed_roles_sql_matches_the_registry_and_model():
    assert W.ROLES_SQL.read_text() == W.generate_roles_sql(), \
        "registry or model changed: run `python -m daydor.agents.roles` and add a migration"


def test_role_inputs_are_sound():
    assert W.validate_roles() == []


def test_every_worker_has_exactly_one_nologin_role_in_the_platform_group(engine, org):
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT r.rolname, r.rolcanlogin, r.rolsuper, r.rolbypassrls,
                   pg_has_role(r.rolname, 'worker_platform', 'MEMBER') AS in_group
            FROM pg_roles r WHERE r.rolname LIKE 'worker\\_%'""")).all()
    live = {r.rolname: r for r in rows if r.rolname != "worker_platform"}
    assert set(live) == {W.role_name(r["worker"]) for r in _records()}
    assert not any(r.rolcanlogin or r.rolsuper or r.rolbypassrls for r in live.values())
    assert all(r.in_group for r in live.values())


def test_worker_roles_belong_to_no_other_group(engine, org):
    """A role inheriting agent_runtime (or any people role) would carry its broad grants."""
    with engine.connect() as conn:
        memberships = conn.execute(text("""
            SELECT m.rolname AS member, g.rolname AS grp
            FROM pg_auth_members am JOIN pg_roles m ON m.oid = am.member JOIN pg_roles g ON g.oid = am.roleid
            WHERE m.rolname LIKE 'worker\\_%'""")).all()
    assert {(m.member, m.grp) for m in memberships if m.grp != "worker_platform"} == set()
    # daydor_app may SET ROLE to them but does not inherit their grants
    with engine.connect() as conn:
        assert conn.execute(text("SELECT pg_has_role('daydor_app', 'worker_gl_poster', 'USAGE')")).scalar_one() is False
        assert conn.execute(text("SELECT pg_has_role('daydor_app', 'worker_gl_poster', 'SET')")).scalar_one() is True


def _expected_worker_privileges() -> set[tuple[str, str, str, str]]:
    """The spec, computed from the registry and the model without using the generator."""
    model = load_model()
    out = set()
    for rec in _records():
        role = W.role_name(rec["worker"])
        for tid in set(rec["reads"]) | set(rec["writes"]):
            t = model.table(tid)
            for c in t.columns:
                if c.encrypted or c.level("G") < READ:
                    continue
                out.add((tid, c.name, role, "SELECT"))
                writable = (tid in rec["writes"] and c.level("G") >= WRITE and c.name not in SYSTEM_MANAGED
                            and not c.derived)
                if writable and (tid, c.name) in GUARDED and rec["worker"] not in W.GUARD_OWNERS[(tid, c.name)]:
                    writable = False
                if writable:
                    out.add((tid, c.name, role, "INSERT"))
                    if not t.append_only:
                        out.add((tid, c.name, role, "UPDATE"))
    return out


def test_column_grants_match_registry_and_model(engine, org):
    """The generated matrix, as test_column_grants_match_model is for the people roles."""
    platform = {(t, c.name, "worker_platform", p) for t in W.PLATFORM_TABLES
                for c in [c for c in load_model().table(t).columns if not c.encrypted]
                for p, ok in (("SELECT", c.level("G") >= READ),
                              ("INSERT", c.level("G") >= WRITE and c.name not in SYSTEM_MANAGED and not c.derived))
                if ok}
    audit = {(t, c.name, "worker_platform", "INSERT") for t in W.PLATFORM_INSERT_ONLY
             for c in load_model().table(t).columns
             if not c.encrypted and c.level("G") >= WRITE and c.name not in SYSTEM_MANAGED and not c.derived}
    expected = _expected_worker_privileges() | platform | audit
    actual = {p for p in _actual_column_privileges(engine) if p[2].startswith("worker_")}
    assert not expected - actual, f"{len(expected - actual)} missing, e.g. {sorted(expected - actual)[:5]}"
    assert not actual - expected, f"{len(actual - expected)} unexpected, e.g. {sorted(actual - expected)[:5]}"
    assert len(expected) > 1500


def test_no_worker_role_has_a_table_level_grant_or_delete(engine, org):
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT grantee, table_schema, table_name, privilege_type FROM information_schema.role_table_grants
            WHERE grantee LIKE 'worker\\_%' AND NOT (grantee = 'worker_platform' AND table_schema = 'app')
              AND NOT (table_schema = 'app' AND table_name IN ('worker_definition', 'worker_tenant_policy'))""")).all()
    assert rows == [], rows[:5]


def test_encrypted_columns_are_never_granted_to_a_worker(engine, org):
    enc = {(t.id, c.name) for t in load_model().tables for c in t.columns if c.encrypted}
    leaked = {p for p in _actual_column_privileges(engine) if p[2].startswith("worker_") and (p[0], p[1]) in enc}
    assert leaked == set()


def test_derived_columns_are_never_writable_by_a_worker(engine, org):
    derived = {(t.id, c.name) for t in load_model().tables for c in t.columns if c.derived}
    bad = {p for p in _actual_column_privileges(engine)
           if p[2].startswith("worker_") and (p[0], p[1]) in derived and p[3] != "SELECT"}
    assert bad == set()


def test_guarded_columns_belong_only_to_their_named_owners(engine, org):
    privs = _actual_column_privileges(engine)
    for (table, column), owners in W.GUARD_OWNERS.items():
        holders = {p[2] for p in privs if p[0] == table and p[1] == column and p[2].startswith("worker_")
                   and p[3] in ("INSERT", "UPDATE")}
        # The model gives agents no write on a column such as er_case.outcome (a person adjudicates), so
        # then nobody holds it; the owner list says who may, if the model ever allows an agent.
        agent_may_write = load_model().table(table).column(column).level("G") >= WRITE
        assert holders == ({W.role_name(o) for o in owners} if agent_may_write else set()), (table, column, holders)


def test_no_worker_role_can_resolve_an_approval_or_drive_the_queue(engine, org):
    with engine.connect() as conn:
        for rec in _records():
            role = W.role_name(rec["worker"])
            for fn in ("app.resolve_approval(uuid, text, text)", "app.claim_jobs(text, text, integer, interval)",
                       "app.complete_job(uuid, text, jsonb)", "app.relay_outbox(integer)"):
                assert conn.execute(text("SELECT has_function_privilege(:r, :f, 'EXECUTE')"),
                                    {"r": role, "f": fn}).scalar_one() is False, (role, fn)


def test_function_grants_go_only_to_the_named_workers(engine, org):
    with engine.connect() as conn:
        for fn, ws in W.FUNCTION_GRANTS.items():
            holders = {r["worker"] for r in _records()
                       if conn.execute(text("SELECT has_function_privilege(:r, :f, 'EXECUTE')"),
                                       {"r": W.role_name(r["worker"]), "f": fn}).scalar_one()}
            assert holders == set(ws), (fn, holders)


# ---------------------------------------------------------------- step 5: sessions and the queue
import uuid                                                            # noqa: E402
from datetime import date                                              # noqa: E402

from daydor.agents.session import worker_session                       # noqa: E402
from daydor.db.session import SessionContext                           # noqa: E402
from daydor.gates.hard import resolve                                  # noqa: E402
from daydor.payroll.disbursement import disburse_payroll_run, request_disbursal_approval  # noqa: E402
from daydor.payroll.run_builder import build_payroll_run               # noqa: E402
from daydor.privacy.pii import decrypt_pii, encrypt_pii                # noqa: E402
from daydor.queue import enqueue                                       # noqa: E402
from daydor.queue.worker import Worker                                 # noqa: E402
from tests.test_payroll_run import payroll_run_tenant, seeded_run      # noqa: E402,F401
from tests.hire_helpers import retention_policy                        # noqa: E402,F401
from tests.test_privacy import _grant_consent                          # noqa: E402


def test_session_accepts_registry_worker_roles_only():
    SessionContext("worker_gl_poster")
    with pytest.raises(ValueError, match="unknown role"):
        SessionContext("worker_not_in_the_registry")
    with pytest.raises(ValueError, match="unknown role"):
        SessionContext("worker_platform")      # the group is not something to switch into


def test_worker_session_switches_to_the_workers_role(engine, org):
    with worker_session(engine, "job-posting-publisher", org.tenant_a) as conn:
        assert conn.execute(text("SELECT app.current_agent_role()")).scalar_one() == "worker_job_posting_publisher"
        assert conn.execute(text("SELECT app.current_app_role()")).scalar_one() == "agent_runtime"
        assert conn.execute(text("SELECT app.assert_worker_enabled('job-posting-publisher')")).scalar_one() == "review"
    with pytest.raises(KeyError):
        with worker_session(engine, "no-such-worker", org.tenant_a):
            pass


def test_a_worker_cannot_read_or_write_outside_its_scope(engine, org):
    with worker_session(engine, "job-posting-publisher", org.tenant_a) as conn:
        conn.execute(text("SELECT id FROM job_posting")).all()           # its own table
    for sql in ("SELECT id FROM employee", "SELECT id FROM payroll_run", "UPDATE job_posting SET id = id",
                "INSERT INTO employee (full_name) VALUES ('x')", "SELECT id FROM audit_log"):
        with pytest.raises(DBAPIError, match="permission denied"):
            with worker_session(engine, "job-posting-publisher", org.tenant_a) as conn:
                conn.execute(text(sql))


def test_a_worker_still_sees_only_its_tenant(engine, org):
    with worker_session(engine, "employee-record-writer", org.tenant_a) as conn:
        seen = set(conn.execute(text("SELECT id FROM employee")).scalars())
    assert seen == set(org.emp.values()) and org.emp_b not in seen


def _enqueue_for(engine, tenant, queue, kind):
    with worker_session(engine, "workflow-engine", tenant) as conn:
        return enqueue(conn, queue, kind)


def test_queue_runs_a_worker_handler_as_its_registry_role(engine, org):
    queue, seen = f"q_{uuid.uuid4().hex[:8]}", {}
    _enqueue_for(engine, org.tenant_a, queue, "post")

    def post(conn, job):
        seen["agent"] = conn.execute(text("SELECT app.current_agent_role()")).scalar_one()

    w = Worker(engine, queue, "w1")
    w.register("post", worker="job-posting-publisher", fn=post)
    assert w.tick()["succeeded"] == 1 and seen == {"agent": "worker_job_posting_publisher"}


def test_register_needs_exactly_one_of_role_or_worker(engine):
    w = Worker(engine, "q", "w")
    with pytest.raises(TypeError):
        w.register("k", fn=lambda c, j: None)
    with pytest.raises(TypeError):
        w.register("k", role="tenant_hr", worker="gl-poster", fn=lambda c, j: None)
    with pytest.raises(KeyError):
        w.register("k", worker="no-such-worker", fn=lambda c, j: None)


def test_a_disabled_worker_fails_its_job_closed(engine, org):
    """Globally or per tenant: the handler never runs and the job is recorded as failed, not skipped."""
    queue, ran = f"q_{uuid.uuid4().hex[:8]}", []
    w = Worker(engine, queue, "w1")
    w.register("post", worker="gl-poster", fn=lambda conn, job: ran.append(job.id))

    jid = _enqueue_for(engine, org.tenant_a, queue, "post")
    with tenant_session(engine, "daydor_ops") as conn:
        conn.execute(text("UPDATE app.worker_definition SET enabled = false WHERE worker = 'gl-poster'"))
    try:
        assert w.tick().get("queued") == 1               # failed and queued for retry, not "succeeded"
    finally:
        with tenant_session(engine, "daydor_ops") as conn:
            conn.execute(text("UPDATE app.worker_definition SET enabled = true WHERE worker = 'gl-poster'"))
    with engine.connect() as conn:
        row = conn.execute(text("SELECT status, attempts, last_error FROM app.job WHERE id = :j"), {"j": jid}).one()
    assert ran == [] and row.attempts == 1 and "worker gl-poster is disabled" in row.last_error

    _set_policy(engine, org.tenant_a, "gl-poster", None, enabled=False)
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE app.job SET run_at = now() WHERE id = :j"), {"j": jid})
        w.tick()
        with engine.connect() as conn:
            err = conn.execute(text("SELECT last_error FROM app.job WHERE id = :j"), {"j": jid}).scalar_one()
        assert ran == [] and "disabled for this tenant" in err
    finally:
        _clear_policy(engine, org.tenant_a, "gl-poster")
    with engine.begin() as conn:
        conn.execute(text("UPDATE app.job SET run_at = now() WHERE id = :j"), {"j": jid})
    assert w.tick()["succeeded"] == 1 and ran == [jid]


def test_payroll_chain_on_worker_roles_and_only_the_disburser_may_disburse(engine, seeded_run):
    tenant, founder = seeded_run["tenant"], seeded_run["founder_user"]
    with worker_session(engine, "payroll-run-builder", tenant) as conn:
        run_id = build_payroll_run(conn, legal_entity_id=seeded_run["legal_entity"],
                                   period_start=date(2026, 8, 1), period_end=date(2026, 8, 31),
                                   retention_class_id=seeded_run["retention_policy"])["payroll_run_id"]
    with worker_session(engine, "direct-deposit-disburser", tenant) as conn:
        approval_id = request_disbursal_approval(conn, payroll_run_id=run_id)
    with tenant_session(engine, "tenant_founder", tenant, user_id=founder) as conn:
        assert resolve(conn, approval_id, "approved") == "approved"

    # Even with an approved gate for this exact row, the builder has no grant on the guarded column.
    with pytest.raises(DBAPIError, match="permission denied"):
        with worker_session(engine, "payroll-run-builder", tenant) as conn:
            disburse_payroll_run(conn, payroll_run_id=run_id, approval_request_id=approval_id)
    # The disburser, with the approved gate, can.
    with worker_session(engine, "direct-deposit-disburser", tenant) as conn:
        disburse_payroll_run(conn, payroll_run_id=run_id, approval_request_id=approval_id)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT disbursed_at FROM payroll_run WHERE id = :r"), {"r": run_id}).scalar_one()


def test_the_disburser_still_needs_an_approved_gate(engine, seeded_run):
    """Holding the column grant is not enough: app.enforce_gate_guard still refuses without approval."""
    tenant = seeded_run["tenant"]
    with worker_session(engine, "payroll-run-builder", tenant) as conn:
        run_id = build_payroll_run(conn, legal_entity_id=seeded_run["legal_entity"],
                                   period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
                                   retention_class_id=seeded_run["retention_policy"])["payroll_run_id"]
    with worker_session(engine, "direct-deposit-disburser", tenant) as conn:
        approval_id = request_disbursal_approval(conn, payroll_run_id=run_id)     # still pending
    with pytest.raises(DBAPIError, match="approved|approval|gate"):
        with worker_session(engine, "direct-deposit-disburser", tenant) as conn:
            disburse_payroll_run(conn, payroll_run_id=run_id, approval_request_id=approval_id)
    with pytest.raises(DBAPIError):
        with worker_session(engine, "direct-deposit-disburser", tenant) as conn:
            disburse_payroll_run(conn, payroll_run_id=run_id, approval_request_id=uuid.uuid4())


# ---------------------------------------------------------------- the PII role-check fix (0027, 0028)
def test_worker_roles_can_collect_and_decrypt_pii(engine, org):
    """Regression: app.current_app_role() is 'agent_runtime' for every agent, so the registries naming
    agent_hr / agent_pay never matched. Worker roles are matched by their real role name."""
    _grant_consent(engine, org.tenant_a, org.emp["deep_report"], "pan")
    with worker_session(engine, "employee-record-writer", org.tenant_a) as conn:
        encrypt_pii(conn, "employee", "pan_encrypted", org.emp["deep_report"], "ABCDE1234G")
        assert decrypt_pii(conn, "employee", "pan_encrypted", org.emp["deep_report"],
                           "identity_verification") == "ABCDE1234G"


def test_only_the_named_workers_can_decrypt_for_a_purpose(engine, org):
    _grant_consent(engine, org.tenant_a, org.emp["founder"], "bank_account")
    with worker_session(engine, "employee-record-writer", org.tenant_a) as conn:
        encrypt_pii(conn, "employee", "bank_account_encrypted", org.emp["founder"], "99887766")
    with worker_session(engine, "direct-deposit-disburser", org.tenant_a) as conn:
        assert decrypt_pii(conn, "employee", "bank_account_encrypted", org.emp["founder"],
                           "payroll_disbursal") == "99887766"
    # in the function grant list but not in the purpose's allowed roles: refused by the purpose check
    with pytest.raises(DBAPIError, match="may not decrypt PII for purpose"):
        with worker_session(engine, "tax-filing-submitter", org.tenant_a) as conn:
            decrypt_pii(conn, "employee", "bank_account_encrypted", org.emp["founder"], "payroll_disbursal")
    # not in the function grant list at all: refused by the database before the function runs
    with pytest.raises(DBAPIError, match="permission denied for function"):
        with worker_session(engine, "gl-poster", org.tenant_a) as conn:
            decrypt_pii(conn, "employee", "bank_account_encrypted", org.emp["founder"], "payroll_disbursal")


# ---------------------------------------------------------------- mutation tests for the generator rules
def test_mutation_guard_owner_must_be_a_worker_that_writes_the_table(monkeypatch):
    monkeypatch.setattr(W, "GUARD_OWNERS", {**W.GUARD_OWNERS, ("payroll_run", "disbursed_at"): ["gl-poster"]})
    assert any("does not write payroll_run" in e for e in W.validate_roles())
    monkeypatch.setattr(W, "GUARD_OWNERS", {**W.GUARD_OWNERS, ("payroll_run", "disbursed_at"): ["nobody"]})
    assert any("is not a worker" in e for e in W.validate_roles())


def test_mutation_guard_owners_must_cover_every_guard(monkeypatch):
    short = {k: v for k, v in W.GUARD_OWNERS.items() if k != ("er_case", "outcome")}
    monkeypatch.setattr(W, "GUARD_OWNERS", short)
    assert any("do not match gates.registry.GUARDS" in e for e in W.validate_roles())


def test_mutation_a_model_using_worker_may_not_be_a_pii_reader(monkeypatch):
    monkeypatch.setitem(W.PII_PURPOSES, "tax_filing", ["tax-filing-submitter", "requisition-drafter"])
    assert any("requisition-drafter" in e and "never be a PII" in e for e in W.validate_roles())


def test_mutation_role_names_must_be_unique():
    recs = _records() + [dict(_records()[0])]
    assert any("collision" in e for e in W.validate_roles(recs))


def test_mutation_guarded_columns_are_excluded_unless_the_worker_is_the_owner():
    model = load_model()
    builder = next(r for r in _records() if r["worker"] == "payroll-run-builder")
    disburser = next(r for r in _records() if r["worker"] == "direct-deposit-disburser")
    assert "disbursed_at" not in W.table_grants(builder, model)["payroll_run"]["update"]
    assert "disbursed_at" in W.table_grants(disburser, model)["payroll_run"]["update"]
    # rename the builder into the owner and the column appears: the rule is the owner list, nothing else
    stand_in = {**builder, "worker": "direct-deposit-disburser"}
    assert "disbursed_at" in W.table_grants(stand_in, model)["payroll_run"]["update"]


def test_mutation_encrypted_and_derived_columns_never_appear_in_generated_grants():
    model = load_model()
    for rec in _records():
        for tid, g in W.table_grants(rec, model).items():
            t = model.table(tid)
            enc = {c.name for c in t.columns if c.encrypted}
            der = {c.name for c in t.columns if c.derived}
            assert not enc & {c for cols in g.values() for c in cols}, (rec["worker"], tid)
            assert not der & set(g.get("insert", []) + g.get("update", [])), (rec["worker"], tid)


# ---------------------------------------------------------------- ADR-006 defaults (0032)
def test_committed_defaults_sql_matches_the_registry():
    assert W.DEFAULTS_SQL.read_text() == W.generate_defaults_sql()


def test_unbuilt_irreversible_workers_start_disabled_and_fail_closed(engine, org):
    with engine.connect() as conn:
        off = {r.worker for r in conn.execute(text("SELECT worker FROM app.worker_definition WHERE NOT enabled"))}
    assert off == {"device-purchase-initiator", "in-country-tax-remitter"}
    with pytest.raises(DBAPIError, match="device-purchase-initiator is disabled"):
        with worker_session(engine, "device-purchase-initiator", org.tenant_a):
            pass
    with worker_session(engine, "gl-poster", org.tenant_a):      # an enabled worker is unaffected
        pass


# ---------------------------------------------------------------- the domain roles are gone (0034)
DOMAIN_ROLES = ("ro", "priv", "ref", "hr", "ta", "ob", "it", "pay", "ben", "time", "comp", "perf", "learn", "fin", "er")


def test_the_agent_domain_roles_are_dropped_and_agent_runtime_is_inert(engine, org):
    with engine.connect() as conn:
        left = conn.execute(text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:r)"),
                            {"r": [f"agent_{d}" for d in DOMAIN_ROLES]}).scalars().all()
        members = conn.execute(text("""SELECT m.rolname FROM pg_auth_members am JOIN pg_roles g ON g.oid = am.roleid
                                       JOIN pg_roles m ON m.oid = am.member WHERE g.rolname = 'agent_runtime'""")).all()
    assert left == [] and members == []


def test_sessions_refuse_the_dropped_domain_roles():
    from daydor.db.session import APP_ROLES
    assert not [r for r in APP_ROLES if r.startswith("agent_")]
    for d in DOMAIN_ROLES:
        with pytest.raises(ValueError, match="unknown role"):
            SessionContext(f"agent_{d}")


def test_pii_registries_name_no_agent_roles(engine, org):
    with engine.connect() as conn:
        roles = conn.execute(text("""SELECT unnest(collect_roles) FROM app.pii_column
                                     UNION ALL SELECT unnest(allowed_roles) FROM app.pii_purpose""")).scalars().all()
    assert roles and not [r for r in roles if r.startswith("agent_")]
    assert "worker_employee_record_writer" in roles and "tenant_hr" in roles


def test_dropping_the_roles_is_refused_while_a_version_2_exit_is_running(engine, org):
    """The migration's own guard, run against a real in-flight version 2 instance (rolled back after)."""
    sql = (W.SQL_DIR / "0034_drop_agent_domain_roles.sql").read_text()
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT set_config('app.tenant_id', %s, true)", (str(org.tenant_a),))
        cur.execute("SET LOCAL ROLE daydor_schema_owner")
        cur.execute("INSERT INTO app.workflow_instance (tenant_id, definition_name, definition_version, subject_table, "
                    "subject_id, state, status) VALUES (%s, 'exit', 2, 'termination', gen_random_uuid(), "
                    "'s10_closeout', 'running')", (str(org.tenant_a),))
        cur.execute("RESET ROLE")
        with pytest.raises(Exception, match="still running"):
            cur.execute(sql)
    finally:
        conn.rollback()
        conn.close()
