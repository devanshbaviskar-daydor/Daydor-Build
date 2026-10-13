"""Queue, outbox, timers and business-day calendars."""
import time
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from daydor.agents.session import worker_session
from daydor.db.session import tenant_session
from daydor.queue import Worker, emit_event, enqueue, schedule_timer, cancel_timer


def q() -> str:
    return f"q_{uuid.uuid4().hex[:8]}"


def job_row(engine, job_id):
    with engine.connect() as conn:
        return conn.execute(text("SELECT * FROM app.job WHERE id = :j"), {"j": job_id}).one()


def test_enqueue_stamps_tenant_and_is_idempotent(engine, org):
    queue = q()
    with worker_session(engine, "workflow-engine", org.tenant_a) as conn:
        a = enqueue(conn, queue, "noop", {"x": 1}, idempotency_key="k1")
        b = enqueue(conn, queue, "noop", {"x": 2}, idempotency_key="k1")
    assert a == b
    assert job_row(engine, a).tenant_id == org.tenant_a


def test_same_idempotency_key_in_other_tenant_is_separate(engine, org):
    queue = q()
    with worker_session(engine, "workflow-engine", org.tenant_a) as conn:
        a = enqueue(conn, queue, "noop", idempotency_key="shared")
    with worker_session(engine, "workflow-engine", org.tenant_b) as conn:
        b = enqueue(conn, queue, "noop", idempotency_key="shared")
    assert a != b


def test_tenant_roles_cannot_read_queue_tables(engine, org):
    with pytest.raises(ProgrammingError, match="permission denied"):
        with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
            conn.execute(text("SELECT * FROM app.job"))


def test_handler_runs_as_registered_role_with_job_tenant(engine, org):
    queue, seen = q(), {}
    with worker_session(engine, "workflow-engine", org.tenant_a) as conn:
        enqueue(conn, queue, "whoami")

    def whoami(conn, job):
        seen["role"] = conn.execute(text("SELECT app.current_app_role()")).scalar_one()
        seen["agent"] = conn.execute(text("SELECT app.current_agent_role()")).scalar_one()
        seen["employees"] = conn.execute(text("SELECT count(*) FROM employee")).scalar_one()
        return {"ok": True}

    w = Worker(engine, queue, "w1")
    w.register("whoami", worker="employee-record-writer", fn=whoami)
    assert w.tick()["succeeded"] == 1
    assert seen == {"role": "agent_runtime", "agent": "worker_employee_record_writer", "employees": len(org.emp)}


def test_skip_locked_gives_concurrent_workers_distinct_jobs(engine, org):
    queue = q()
    with worker_session(engine, "workflow-engine", org.tenant_a) as conn:
        for i in range(4):
            enqueue(conn, queue, "noop", {"i": i})
    # Worker 1 holds its claim transaction open while worker 2 claims.
    with tenant_session(engine, "daydor_worker") as c1:
        first = c1.execute(text("SELECT id FROM app.claim_jobs(:q, 'w1', 2)"), {"q": queue}).scalars().all()
        with tenant_session(engine, "daydor_worker") as c2:
            second = c2.execute(text("SELECT id FROM app.claim_jobs(:q, 'w2', 10)"), {"q": queue}).scalars().all()
    assert len(first) == 2 and len(second) == 2 and not set(first) & set(second)


def test_failure_retries_with_backoff_then_dead_letters(engine, org):
    queue = q()
    with worker_session(engine, "workflow-engine", org.tenant_a) as conn:
        jid = enqueue(conn, queue, "boom", max_attempts=2)

    def boom(conn, job):
        raise RuntimeError("carrier API down")

    w = Worker(engine, queue, "w1")
    w.register("boom", worker="election-processor", fn=boom)
    assert w.tick().get("queued") == 1
    row = job_row(engine, jid)
    assert row.status == "queued" and row.attempts == 1 and "carrier API down" in row.last_error
    assert row.run_at > datetime.now(timezone.utc) + timedelta(seconds=5)   # backed off ~10s

    with engine.begin() as conn:   # skip the wait
        conn.execute(text("UPDATE app.job SET run_at = now() WHERE id = :j"), {"j": jid})
    assert w.tick().get("dead") == 1
    assert job_row(engine, jid).status == "dead"

    with tenant_session(engine, "daydor_ops") as conn:
        conn.execute(text("SELECT app.retry_dead_job(:j)"), {"j": jid})
    assert job_row(engine, jid).status == "queued"


def test_unknown_kind_is_failed_not_dropped(engine, org):
    queue = q()
    with worker_session(engine, "workflow-engine", org.tenant_a) as conn:
        jid = enqueue(conn, queue, "nobody-handles-this", max_attempts=1)
    Worker(engine, queue, "w1").tick()
    row = job_row(engine, jid)
    assert row.status == "dead" and "no handler" in row.last_error


def test_expired_lease_is_reclaimed_and_old_worker_cannot_complete(engine, org):
    queue = q()
    with worker_session(engine, "workflow-engine", org.tenant_a) as conn:
        jid = enqueue(conn, queue, "slow")
    with tenant_session(engine, "daydor_worker") as conn:
        conn.execute(text("SELECT * FROM app.claim_jobs(:q, 'crashed', 1, interval '0 seconds')"), {"q": queue})
    time.sleep(0.05)
    with tenant_session(engine, "daydor_worker") as conn:
        again = conn.execute(text("SELECT id, attempts FROM app.claim_jobs(:q, 'w2', 1)"), {"q": queue}).one()
    assert again.id == jid and again.attempts == 2
    with pytest.raises(DBAPIError, match="lease lost"):
        with tenant_session(engine, "daydor_worker") as conn:
            conn.execute(text("SELECT app.complete_job(:j, 'crashed', NULL)"), {"j": jid})


def test_outbox_event_commits_with_business_write_and_fans_out(engine, org):
    queue, topic = q(), f"employee.hired.{uuid.uuid4().hex[:6]}"
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO app.subscription VALUES (:t, :q, 'build-checklist'), "
                          "(:t, :q, 'provision-identity')"), {"t": topic, "q": queue})
    # Rolled-back transaction: neither the write nor the event survives.
    with pytest.raises(RuntimeError):
        with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
            emit_event(conn, topic, "employee", org.emp["peer"], {"note": "rolled back"})
            raise RuntimeError("abort")
    with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
        emit_event(conn, topic, "employee", org.emp["peer"], {"start": "2026-11-02"})

    done = []
    w = Worker(engine, queue, "w1")
    w.register("build-checklist", worker="onboarding-checklist-builder", fn=lambda c, j: done.append(("checklist", j.payload["subject_id"])))
    w.register("provision-identity", worker="sso-identity-provisioner", fn=lambda c, j: done.append(("identity", j.payload["subject_id"])))
    out = w.tick()
    assert out["succeeded"] == 2
    assert sorted(d[0] for d in done) == ["checklist", "identity"]
    assert all(d[1] == str(org.emp["peer"]) for d in done)
    assert w.tick().get("succeeded") is None   # published once only


def test_timer_fires_once_and_can_be_rescheduled_or_cancelled(engine, org):
    queue = q()
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    future = datetime.now(timezone.utc) + timedelta(days=3)
    with worker_session(engine, "workflow-engine", org.tenant_a) as conn:
        schedule_timer(conn, "i9:section2:peer", queue, "i9-deadline", future)
        schedule_timer(conn, "i9:section2:peer", queue, "i9-deadline", past)      # reschedule earlier
        schedule_timer(conn, "cert-expiry:x", queue, "cert-expiry", past)
        assert cancel_timer(conn, "cert-expiry:x") is True
    fired = []
    w = Worker(engine, queue, "w1")
    w.register("i9-deadline", worker="root-orchestrator", fn=lambda c, j: fired.append(j.payload["timer_key"]))
    w.register("cert-expiry", worker="certification-expiry-monitor", fn=lambda c, j: fired.append(j.payload["timer_key"]))
    w.tick()
    w.tick()
    assert fired == ["i9:section2:peer"]


def test_i9_clock_counts_business_days_skipping_weekends_and_holidays(engine, org):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO app.holiday VALUES ('US-FED', '2026-11-11', 'Veterans Day') "
                          "ON CONFLICT DO NOTHING"))
    with worker_session(engine, "workflow-engine", org.tenant_a) as conn:
        # First day worked Friday Nov 6 2026 -> Mon 9, Tue 10, (Wed 11 holiday), Thu 12
        due = conn.execute(text("SELECT app.add_business_days('2026-11-06', 3, 'US-FED')")).scalar_one()
    assert due == date(2026, 11, 12)
