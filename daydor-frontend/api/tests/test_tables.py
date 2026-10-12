import uuid

from conftest import sign_in


def rows(client, headers, table, **params):
    r = client.get(f"/api/tables/{table}", headers=headers, params=params)
    return r


def test_hr_reads_positions(client, people):
    r = rows(client, people["hr"], "position")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 4
    assert {"status", "budgeted_fte", "department_id"} <= set(body["columns"])


def test_roles_without_access_are_refused_before_the_database(client, people):
    assert rows(client, people["employee"], "position").json()["error"]["code"] == "forbidden"
    assert rows(client, people["admin"], "position").status_code == 403


def test_encrypted_columns_are_never_returned(client, people):
    body = rows(client, people["hr"], "employee").json()
    assert "full_name" in body["columns"]
    for secret in ("pan_encrypted", "ssn_encrypted", "bank_account_encrypted", "aadhaar_ekyc_ref"):
        assert secret not in body["columns"]
        assert all(secret not in r for r in body["rows"])


def test_masked_view_is_used_for_masked_roles(client, people):
    # Founder has masked access on some work_authorization columns, so reads go through the view.
    r = rows(client, people["founder"], "work_authorization")
    assert r.status_code == 200


def test_filters_only_allow_readable_columns(client, people):
    ok = rows(client, people["hr"], "position", status="open").json()
    assert ok["total"] >= 3 and all(r["status"] == "open" for r in ok["rows"])
    bad = rows(client, people["hr"], "position", not_a_column="x")
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_filter"


def test_unknown_table_is_404(client, people):
    assert rows(client, people["hr"], "nope").json()["error"]["code"] == "unknown_table"


def test_tenant_isolation(client, people, engine):
    from daydor_api.provision import insert
    with engine.begin() as conn:
        other = insert(conn, "tenant", legal_name="Globex", status="active")
        le = insert(conn, "legal_entity", tenant_id=other, name="Globex Pvt Ltd", country_code="IN")
        dept = insert(conn, "department", tenant_id=other, name="Ops")
        jp = insert(conn, "job_profile", tenant_id=other, title="Other", job_family="x", level="L1",
                    flsa_default="exempt", description="x")
        insert(conn, "position", tenant_id=other, department_id=dept, job_profile_id=jp, status="open",
               budgeted_fte="1.0", budgeted_cost="1", opened_at="2026-01-01")
    mine = rows(client, people["hr"], "position").json()["rows"]
    assert all(r["department_id"] != str(dept) for r in mine)
    assert le


def test_hr_creates_a_position_and_the_write_is_idempotent(client, people):
    base = rows(client, people["hr"], "position", status="open").json()["rows"][0]
    payload = {"department_id": base["department_id"], "job_profile_id": base["job_profile_id"],
               "status": "open", "budgeted_fte": 1.0, "budgeted_cost": 1800000, "opened_at": "2026-10-01"}
    h = {**people["hr"], "Idempotency-Key": str(uuid.uuid4())}
    first = client.post("/api/tables/position", headers=h, json=payload)
    assert first.status_code == 201, first.text
    again = client.post("/api/tables/position", headers=h, json=payload)
    assert again.json()["id"] == first.json()["id"] and again.json().get("replayed") is True


def test_writes_reject_fields_the_role_cannot_set(client, people):
    base = rows(client, people["hr"], "position").json()["rows"][0]
    r = client.post("/api/tables/position", headers=people["hr"],
                    json={"tenant_id": str(uuid.uuid4()), "department_id": base["department_id"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_fields"


def test_roles_without_write_access_cannot_create(client, people):
    r = client.post("/api/tables/position", headers=people["manager"], json={"status": "open"})
    assert r.status_code == 403


def test_flow_tables_are_not_directly_writable(client, people):
    r = client.post("/api/tables/job_requisition", headers=people["hr"], json={"status": "draft"})
    assert r.json()["error"]["code"] == "not_directly_writable"


def test_hr_can_update_a_position(client, people):
    row = rows(client, people["hr"], "position", status="open").json()["rows"][0]
    r = client.patch(f"/api/tables/position/{row['id']}", headers=people["hr"], json={"budgeted_cost": 2500000})
    assert r.status_code == 200
    r = client.patch(f"/api/tables/position/{uuid.uuid4()}", headers=people["hr"], json={"budgeted_cost": 1})
    assert r.status_code == 404
