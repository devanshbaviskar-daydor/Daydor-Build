from conftest import sign_in


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_every_people_facing_role_can_sign_in(client, people):
    roles = {}
    for key, headers in people.items():
        me = client.get("/api/auth/me", headers=headers).json()
        roles[key] = me["role"]
    assert roles == {
        "founder": "tenant_founder", "hr": "tenant_hr", "payroll": "tenant_payroll", "it": "tenant_it",
        "manager": "tenant_manager", "employee": "tenant_employee", "ops": "daydor_ops",
        "admin": "daydor_admin", "auditor": "external_auditor",
    }


def test_unknown_email_is_rejected(client):
    r = client.post("/api/auth/dev-login", json={"email": "nobody@acme.test"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unknown_account"


def test_requests_without_a_valid_token_are_rejected(client):
    assert client.get("/api/auth/me").json()["error"]["code"] == "not_signed_in"
    bad = client.get("/api/auth/me", headers={"Authorization": "Bearer abc.def"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "session_expired"


def test_dev_users_lists_the_demo_accounts(client):
    users = client.get("/api/auth/dev-users").json()["users"]
    assert {u["role"] for u in users} >= {"tenant_founder", "tenant_hr", "daydor_ops", "daydor_admin"}


def test_a_deactivated_backend_user_cannot_sign_in(client, engine):
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("UPDATE app_user SET is_active = false WHERE email = 'sana.qureshi@acme.test'"))
    try:
        r = client.post("/api/auth/dev-login", json={"email": "sana.qureshi@acme.test"})
        assert r.status_code == 401 and r.json()["error"]["code"] == "identity_mismatch"
    finally:
        with engine.begin() as conn:
            conn.execute(text("UPDATE app_user SET is_active = true WHERE email = 'sana.qureshi@acme.test'"))
    assert sign_in(client, "sana.qureshi@acme.test")
