"""Phase F over HTTP: the webhook edge, request ids and logs, platform health."""
import json
import logging
import time
import uuid

import pytest
from sqlalchemy import text

from conftest import run_workers
from daydor import webhooks

SECRET = "whsec-test"


@pytest.fixture
def hook(engine, people, monkeypatch):
    """A bank webhook endpoint on the demo tenant with a configured secret; returns (token, tenant)."""
    monkeypatch.setenv("DAYDOR_WEBHOOK_SECRETS", json.dumps({"bank": SECRET}))
    token = uuid.uuid4().hex + uuid.uuid4().hex
    with engine.begin() as conn:
        tenant = conn.execute(text("SELECT tenant_id FROM app_user WHERE role = 'hr' LIMIT 1")).scalar_one()
        conn.execute(text("INSERT INTO app.webhook_endpoint (tenant_id, integration, token_sha256) VALUES (:t, 'bank', :h)"),
                     {"t": tenant, "h": webhooks.token_sha256(token)})
    return token, tenant


def post(client, token, payload, *, secret=SECRET, integration="bank", headers=None, raw=None, timestamp=None):
    body = raw if raw is not None else json.dumps(payload).encode()
    h = {"Content-Type": "application/json", "X-Signature": webhooks.sign(secret, body, timestamp), **(headers or {})}
    if timestamp:
        h["X-Timestamp"] = timestamp
    return client.post(f"/api/webhooks/{integration}/{token}", content=body, headers=h)


def test_a_signed_event_is_stored_once_and_a_redelivery_is_recognised(client, hook, engine):
    token, tenant = hook
    first = post(client, token, {"id": "evt-1", "kind": "transfer.settled"})
    assert first.status_code == 202 and first.json() == {"status": "received"}
    again = post(client, token, {"id": "evt-1", "kind": "transfer.settled"})
    assert again.status_code == 200 and again.json() == {"status": "duplicate"}
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT external_id, status FROM app.webhook_event WHERE tenant_id = :t AND external_id = 'evt-1'"), {"t": tenant}).all()
    assert [(r.external_id, r.status) for r in rows] == [("evt-1", "received")]
    run_workers()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT status FROM app.webhook_event WHERE external_id = 'evt-1'")).scalar_one() == "ignored"     # no handler yet: kept


def test_the_event_id_header_wins_and_a_body_with_no_id_is_deduplicated_by_content(client, hook, engine):
    token, _ = hook
    assert post(client, token, {"x": 1}, headers={"X-Event-Id": "hdr-1"}).status_code == 202
    assert post(client, token, {"x": 2}, headers={"X-Event-Id": "hdr-1"}).status_code == 200           # same vendor id
    assert post(client, token, {"anonymous": True}).status_code == 202
    assert post(client, token, {"anonymous": True}).status_code == 200                                   # same bytes


def test_a_bad_signature_is_refused_before_anything_is_looked_up(client, hook):
    token, _ = hook
    assert post(client, token, {"id": "e"}, secret="wrong").status_code == 401
    assert post(client, "0" * 64, {"id": "e"}, secret="wrong").status_code == 401         # same answer for a token that does not exist
    r = client.post(f"/api/webhooks/bank/{token}", content=b"{}", headers={"Content-Type": "application/json"})
    assert r.status_code == 401


def test_a_valid_signature_for_an_unknown_token_or_an_integration_with_no_secret(client, hook, monkeypatch):
    token, _ = hook
    assert post(client, "0" * 64, {"id": "e"}).status_code == 404
    assert post(client, token, {"id": "e"}, integration="gl").status_code == 503                           # no secret for gl: closed
    monkeypatch.delenv("DAYDOR_WEBHOOK_SECRETS")
    assert post(client, token, {"id": "e"}).status_code == 503


def test_replays_oversized_and_malformed_bodies_are_refused(client, hook):
    token, _ = hook
    assert post(client, token, {"id": "old"}, timestamp=str(int(time.time()) - 3600)).status_code == 401
    assert post(client, token, {"id": "fresh-ts"}, timestamp=str(int(time.time()))).status_code == 202
    assert post(client, token, None, raw=b"[1, 2]").status_code == 422
    assert post(client, token, None, raw=b"not json").status_code == 422
    assert post(client, token, None, raw=b'{"pad": "' + b"x" * webhooks.MAX_BODY_BYTES + b'"}').status_code == 413


def test_every_response_has_a_request_id_and_the_log_never_holds_the_secret_url(client, hook, caplog):
    token, _ = hook
    with caplog.at_level(logging.INFO, logger="daydor_api.request"):
        r = post(client, token, {"id": "log-1"}, headers={"X-Request-ID": "trace-12345678"})
        plain = client.get("/api/health")
    assert r.headers["X-Request-ID"] == "trace-12345678" and len(plain.headers["X-Request-ID"]) == 32
    lines = [json.loads(rec.message) for rec in caplog.records if rec.name == "daydor_api.request"]
    assert {"request_id": "trace-12345678", "method": "POST", "route": "/api/webhooks/{integration}/{token}", "status": 202}.items() <= lines[0].items()
    assert token not in caplog.text
    r = client.get("/api/health", headers={"X-Request-ID": "bad id with spaces!"})
    assert r.headers["X-Request-ID"] != "bad id with spaces!"


def test_platform_health_is_for_daydor_admins(client, people):
    for who in ("founder", "hr", "ops", "auditor", "employee"):
        assert client.get("/api/ops/health", headers=people[who]).status_code == 403
        assert client.get("/api/ops/metrics", headers=people[who]).status_code == 403
    body = client.get("/api/ops/health", headers=people["admin"]).json()
    assert body["status"] in ("ok", "alert") and isinstance(body["alerts"], list)
    assert {"queue_jobs", "circuit_open", "tenants_near_ai_cap"} <= {m["metric"] for m in body["metrics"]}


def test_metrics_are_prometheus_text(client, people):
    r = client.get("/api/ops/metrics", headers=people["admin"])
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    lines = [l for l in r.text.splitlines() if l]
    assert any(l.startswith("daydor_circuit_open{integration=") for l in lines) and any(l.startswith("daydor_tenants_near_ai_cap ") for l in lines)
    assert all(len(l.rsplit(" ", 1)) == 2 and float(l.rsplit(" ", 1)[1]) is not None for l in lines)


def test_outside_development_the_api_will_not_connect_as_the_owner_or_with_the_dev_password():
    from daydor_api.config import check_database_login
    check_database_login("postgresql+psycopg://daydor_owner:dev@db/x", "dev")                       # development: anything goes
    for bad in ("postgresql+psycopg://daydor_owner:strong-secret-value@db/x", "postgresql+psycopg://postgres:pw@db/x",
                "postgresql+psycopg://daydor_app:dev@db/x", "postgresql+psycopg://daydor_app@db/x"):
        with pytest.raises(RuntimeError, match="real password"):
            check_database_login(bad, "production")
    check_database_login("postgresql+psycopg://daydor_app:a-long-random-secret-value@db/x", "production")
