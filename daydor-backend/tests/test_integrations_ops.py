"""Phase F: adapter circuit breakers, the webhook inbox, platform health and alerts."""
from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from daydor import webhooks
from daydor.adapters.bank import FakeBankAdapter, TransferRequest
from daydor.adapters.resilient import AdapterRejected, IntegrationUnavailable, guard
from daydor.agents.session import worker_session
from daydor.db.session import tenant_session
from daydor.queue import Worker
from tests.factories import insert


@pytest.fixture
def own(engine):
    with engine.begin() as conn:
        tenant = insert(conn, "tenant", legal_name="Hooks Co", status="active")
        ops = insert(conn, "app_user", role="ops")
        conn.execute(text("INSERT INTO app.ops_tenant_assignment (user_id, tenant_id) VALUES (:u, :t)"), {"u": ops, "t": tenant})
        admin = insert(conn, "app_user", role="admin")
    return {"tenant": tenant, "ops": ops, "admin": admin}


@pytest.fixture(autouse=True)
def clean(engine):
    def reset():
        with engine.begin() as conn:
            conn.execute(text("UPDATE app.integration_circuit SET state = 'closed', failures = 0, opened_at = NULL, threshold = 5"))
        webhooks.HANDLERS.clear()
    reset()
    yield
    reset()


def ops(engine, own):
    return tenant_session(engine, "daydor_ops", own["tenant"], user_id=own["ops"])


def endpoint(engine, own, integration="bank"):
    with ops(engine, own) as conn:
        return conn.execute(text("SELECT app.create_webhook_endpoint(:i)"), {"i": integration}).scalar_one()


def receive(engine, token, external_id=None, integration="bank", payload=None):
    with tenant_session(engine, "daydor_worker") as conn:
        return conn.execute(text("SELECT * FROM app.receive_webhook(:t, :i, :e, CAST(:p AS jsonb))"),
                            {"t": webhooks.token_sha256(token), "i": integration, "e": external_id or uuid.uuid4().hex,
                             "p": json.dumps(payload or {"kind": "transfer.settled"})}).one()


def drain(engine):
    w = Worker(engine, webhooks.QUEUE, f"wh-{uuid.uuid4().hex[:6]}")
    w.register(webhooks.KIND, worker="root-orchestrator", fn=webhooks.handle_webhook_received)
    total: dict[str, int] = {}
    for _ in range(10):
        out = w.tick()
        for k, v in out.items():
            total[k] = total.get(k, 0) + v
        if not out.get("succeeded"):
            break
    return total


def event(engine, own, event_id):
    with ops(engine, own) as conn:
        return conn.execute(text("SELECT status, attempts, last_error FROM app.webhook_event WHERE id = :i"), {"i": event_id}).one()


# ------------------------------------------------------------------ signatures
def test_a_signature_must_match_the_body_the_secret_and_the_clock():
    body = b'{"id": "e1"}'
    good = webhooks.sign("s3cret", body)
    assert webhooks.verify_signature("s3cret", body, good)
    assert not webhooks.verify_signature("s3cret", body + b" ", good)           # tampered body
    assert not webhooks.verify_signature("other", body, good)                   # another secret
    assert not webhooks.verify_signature("s3cret", body, None) and not webhooks.verify_signature("s3cret", body, "sha256=")
    ts = "1000000"
    signed = webhooks.sign("s3cret", body, ts)
    assert webhooks.verify_signature("s3cret", body, signed, ts, now=1000100)
    assert not webhooks.verify_signature("s3cret", body, signed, ts, now=1000000 + 301)          # a replay, five minutes on
    assert not webhooks.verify_signature("s3cret", body, signed, "1000001", now=1000100)         # timestamp not the one signed
    assert not webhooks.verify_signature("s3cret", body, signed, "soon", now=1000100)


def test_secrets_come_from_the_environment_and_none_means_none(monkeypatch):
    monkeypatch.setenv("DAYDOR_WEBHOOK_SECRETS", json.dumps({"bank": "abc"}))
    assert webhooks.secret_for("bank") == "abc" and webhooks.secret_for("gl") is None
    monkeypatch.setenv("DAYDOR_WEBHOOK_SECRETS", "not json")
    assert webhooks.secret_for("bank") is None
    monkeypatch.delenv("DAYDOR_WEBHOOK_SECRETS")
    assert webhooks.secret_for("bank") is None


# ------------------------------------------------------------------ the inbox
def test_an_endpoint_is_created_by_ops_for_a_registered_integration_and_only_its_hash_is_kept(engine, own):
    token = endpoint(engine, own)
    assert len(token) == 64
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT token_sha256 FROM app.webhook_endpoint WHERE tenant_id = :t"), {"t": own["tenant"]}).scalars().all()
    assert rows == [webhooks.token_sha256(token)] and token not in rows[0]
    with pytest.raises(DBAPIError):
        with ops(engine, own) as conn:
            conn.execute(text("SELECT app.create_webhook_endpoint('made-up')"))
    for role in ("tenant_founder", "tenant_hr"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            with tenant_session(engine, role, own["tenant"]) as conn:
                conn.execute(text("SELECT app.create_webhook_endpoint('bank')"))
    with pytest.raises(ProgrammingError, match="permission denied"):
        with ops(engine, own) as conn:
            conn.execute(text("SELECT token_sha256 FROM app.webhook_endpoint"))


def test_an_event_is_stored_once_for_the_endpoints_tenant_and_a_redelivery_is_recognised(engine, own):
    token = endpoint(engine, own)
    a = receive(engine, token, "evt-1")
    assert a.outcome == "received" and a.event_id
    assert receive(engine, token, "evt-1").outcome == "duplicate"
    assert receive(engine, token, "evt-2").outcome == "received"
    with ops(engine, own) as conn:
        n = conn.execute(text("SELECT count(*) FROM app.webhook_event")).scalar_one()
    assert n == 2
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM app.job WHERE tenant_id = :t AND kind = 'webhook.received'"), {"t": own["tenant"]}).scalar_one() == 2


def test_an_unknown_token_the_wrong_integration_or_a_disabled_endpoint_is_unknown(engine, own):
    token = endpoint(engine, own)
    assert receive(engine, "0" * 64).outcome == "unknown"
    assert receive(engine, token, integration="gl").outcome == "unknown"
    with engine.begin() as conn:
        conn.execute(text("UPDATE app.webhook_endpoint SET enabled = false WHERE tenant_id = :t"), {"t": own["tenant"]})
    assert receive(engine, token).outcome == "unknown"


def test_only_the_edge_role_can_receive_and_the_payload_is_not_readable_from_the_table(engine, own):
    token = endpoint(engine, own)
    for role in ("tenant_founder", "tenant_hr", "daydor_ops"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            with tenant_session(engine, role, own["tenant"], user_id=own["ops"]) as conn:
                conn.execute(text("SELECT * FROM app.receive_webhook(:t, 'bank', 'x', '{}')"), {"t": webhooks.token_sha256(token)})
    receive(engine, token, "secret-event", payload={"account": "1234567890"})
    with pytest.raises(ProgrammingError, match="permission denied"):
        with ops(engine, own) as conn:
            conn.execute(text("SELECT payload FROM app.webhook_event"))


def test_events_are_per_tenant(engine, own, org):
    receive(engine, endpoint(engine, own), "evt-x")
    with tenant_session(engine, "external_auditor", org.tenant_a) as conn:
        assert conn.execute(text("SELECT count(*) FROM app.webhook_event")).scalar_one() == 0


def test_with_no_handler_the_event_is_kept_and_ignored_then_replayable(engine, own):
    token = endpoint(engine, own)
    eid = receive(engine, token, "evt-ign").event_id
    assert drain(engine)["succeeded"] >= 1
    row = event(engine, own, eid)
    assert row.status == "ignored" and "no handler" in row.last_error
    seen = []
    webhooks.register("bank", lambda conn, e: seen.append(e["payload"]) or {"n": 1})          # a handler ships; ops replays
    with ops(engine, own) as conn:
        conn.execute(text("SELECT app.replay_webhook(:i)"), {"i": eid})
    drain(engine)
    assert event(engine, own, eid).status == "processed" and seen == [{"kind": "transfer.settled"}]
    with pytest.raises(DBAPIError, match="cannot be replayed"):                              # processed events are not replayed
        with ops(engine, own) as conn:
            conn.execute(text("SELECT app.replay_webhook(:i)"), {"i": eid})


def test_a_handler_that_raises_fails_the_event_not_the_queue_and_the_event_can_be_replayed(engine, own):
    token = endpoint(engine, own)
    state = {"boom": True}

    def handler(conn, e):
        if state["boom"]:
            raise ValueError("vendor sent something odd")
    webhooks.register("bank", handler)
    eid = receive(engine, token, "evt-bad").event_id
    assert drain(engine)["succeeded"] >= 1                                                      # the job itself succeeded
    row = event(engine, own, eid)
    assert (row.status, row.attempts) == ("failed", 1) and "ValueError" in row.last_error
    state["boom"] = False
    with ops(engine, own) as conn:
        conn.execute(text("SELECT app.replay_webhook(:i)"), {"i": eid})
    drain(engine)
    assert event(engine, own, eid).status == "processed"


def test_a_handlers_database_work_is_undone_when_it_fails(engine, own):
    token = endpoint(engine, own)

    def handler(conn, e):
        conn.execute(text("SELECT app.notify('tenant_hr', 'x', 'info', 'from a webhook', NULL, NULL, '{}', :k)"), {"k": uuid.uuid4().hex})
        raise RuntimeError("after writing")
    webhooks.register("bank", handler)
    eid = receive(engine, token, "evt-half").event_id
    drain(engine)
    assert event(engine, own, eid).status == "failed"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM app.notification WHERE tenant_id = :t AND title = 'from a webhook'"), {"t": own["tenant"]}).scalar_one() == 0


# ------------------------------------------------------------------ adapter breakers
def state(engine, name="bank"):
    with engine.connect() as conn:
        return conn.execute(text("SELECT state, failures FROM app.integration_circuit WHERE integration = :i"), {"i": name}).one()


class Flaky:
    def __init__(self, error):
        self.calls, self.error, self.name = 0, error, "flaky"

    def transfer(self, request):
        self.calls += 1
        if self.error:
            raise self.error
        return "ok"


def test_every_adapter_has_a_breaker(engine):
    with tenant_session(engine, "daydor_ops") as conn:
        have = set(conn.execute(text("SELECT integration FROM app.integration_circuit")).scalars())
    assert {"bank", "tax_filing", "gl", "background_check", "everify", "idp", "job_board", "model_provider"} <= have


def test_a_guarded_adapter_passes_calls_through_and_records_success(engine):
    bank = guard(FakeBankAdapter(), "bank", engine)
    assert bank.transfer(TransferRequest("r", Decimal("1"))).transfer_ref.startswith("fake-transfer-")
    assert state(engine).failures == 0


def test_failures_open_the_breaker_and_an_open_breaker_does_not_call_the_vendor(engine):
    vendor = Flaky(TimeoutError("vendor timed out"))
    bank = guard(vendor, "bank", engine)
    for _ in range(5):
        with pytest.raises(TimeoutError):
            bank.transfer(None)
    assert tuple(state(engine)) == ("open", 5)
    with pytest.raises(IntegrationUnavailable) as caught:
        bank.transfer(None)
    assert vendor.calls == 5 and 0 < caught.value.seconds <= 60 and caught.value.integration == "bank"
    assert tuple(state(engine, "gl")) == ("closed", 0)                                          # other integrations are untouched


def test_a_vendor_that_refuses_is_not_an_outage(engine):
    bank = guard(Flaky(AdapterRejected("account closed")), "bank", engine)
    for _ in range(8):
        with pytest.raises(AdapterRejected):
            bank.transfer(None)
    assert tuple(state(engine)) == ("closed", 0)


def test_a_failure_is_recorded_even_though_the_caller_rolls_back(engine):
    vendor = Flaky(ConnectionError("reset"))
    with pytest.raises(ConnectionError):
        with engine.begin() as conn:
            guard(vendor, "bank", conn).transfer(None)
    assert state(engine).failures == 1


def test_an_open_breaker_defers_a_job_without_spending_an_attempt(engine, own):
    with engine.begin() as conn:
        conn.execute(text("UPDATE app.integration_circuit SET state = 'open', opened_at = now() WHERE integration = 'bank'"))
    from daydor.queue import enqueue
    with worker_session(engine, "workflow-engine", own["tenant"]) as conn:
        jid = enqueue(conn, "pay", "bank_call", {}, idempotency_key=uuid.uuid4().hex)
    calls = []

    def handler(conn, job):
        calls.append(1)
        guard(FakeBankAdapter(), "bank", conn).transfer(TransferRequest("r", Decimal("1")))
    w = Worker(engine, "pay", f"d-{uuid.uuid4().hex[:6]}")
    w.register("bank_call", worker="direct-deposit-disburser", fn=handler)
    out = w.tick()
    assert out.get("deferred", 0) >= 1
    with engine.connect() as conn:
        job = conn.execute(text("SELECT status, attempts, run_at > now() AS later, last_error FROM app.job WHERE id = :j"), {"j": jid}).one()
    assert (job.status, job.attempts, job.later) == ("queued", 0, True) and "circuit is open" in job.last_error


# ------------------------------------------------------------------ platform health
def health(engine, own, fn="ops_health"):
    with tenant_session(engine, "daydor_admin", user_id=own["admin"]) as conn:
        return conn.execute(text(f"SELECT * FROM app.{fn}()")).all()


def test_health_is_aggregate_numbers_for_the_platform_admin_only(engine, own):
    endpoint(engine, own)
    rows = health(engine, own)
    metrics = {r.metric for r in rows}
    assert {"queue_jobs", "circuit_open", "notifications_open", "ai_tokens_this_month", "tenants_near_ai_cap"} <= metrics
    assert all(isinstance(r.value, Decimal) for r in rows)
    for role in ("daydor_ops", "tenant_founder", "tenant_hr", "external_auditor"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            with tenant_session(engine, role, own["tenant"], user_id=own["ops"]) as conn:
                conn.execute(text("SELECT * FROM app.ops_health()"))
        with pytest.raises(ProgrammingError, match="permission denied"):
            with tenant_session(engine, role, own["tenant"], user_id=own["ops"]) as conn:
                conn.execute(text("SELECT * FROM app.ops_alerts()"))


def test_alerts_say_what_needs_a_person(engine, own):
    with engine.begin() as conn:
        conn.execute(text("UPDATE app.integration_circuit SET state = 'open', opened_at = now() WHERE integration = 'gl'"))
    token = endpoint(engine, own)
    webhooks.register("bank", lambda c, e: 1 / 0)
    receive(engine, token, "evt-fail")
    drain(engine)
    alerts = {(a.code, a.severity): a for a in health(engine, own, "ops_alerts")}
    assert ("circuit_open", "critical") in alerts and "gl" in alerts[("circuit_open", "critical")].message
    assert ("webhook_failed", "warning") in alerts and alerts[("webhook_failed", "warning")].value >= 1


def test_a_tenant_near_its_ai_cap_is_an_alert(engine, own):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO app.tenant_ai_budget (tenant_id, monthly_cap_tokens) VALUES (:t, 1000)"), {"t": own["tenant"]})
        conn.execute(text("INSERT INTO app.frontdoor_turn (tenant_id, role, status, utterance_sha256, utterance_chars, input_tokens, output_tokens) "
                          "VALUES (:t, 'tenant_hr', 'ready', 'x', 1, 700, 200)"), {"t": own["tenant"]})
    assert any(a.code == "tenants_near_ai_cap" for a in health(engine, own, "ops_alerts"))
