"""Privacy services (ADR-002): app.encrypt_pii / app.decrypt_pii, purpose and consent checks.

Scope: the 4 encrypted `employee` columns. `er_case_note.note_body` is append-only and NOT NULL,
so it needs insert-time encryption (a different design); it is not wired up yet (see the note
at the top of migrations/sql/0011_privacy.sql).
"""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from daydor.db.session import tenant_session
from daydor.privacy.pii import decrypt_pii, encrypt_pii
from tests.factories import insert


def _grant_consent(engine, tenant, employee, data_category, purpose="identity_verification"):
    with engine.begin() as conn:
        insert(conn, "consent_record", tenant_id=tenant, employee_id=employee, data_category=data_category,
               purpose=purpose, status="granted", granted_at="2026-01-01", consent_artifact_ref="doc-1")


def test_encrypt_requires_consent(engine, org):
    with pytest.raises(DBAPIError, match="no active consent"):
        with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
            encrypt_pii(conn, "employee", "pan_encrypted", org.emp["report"], "ABCDE1234F")


def test_encrypt_requires_collector_role(engine, org):
    _grant_consent(engine, org.tenant_a, org.emp["peer"], "pan")
    with pytest.raises(DBAPIError, match="may not collect"):
        with tenant_session(engine, "tenant_payroll", org.tenant_a) as conn:
            encrypt_pii(conn, "employee", "pan_encrypted", org.emp["peer"], "ABCDE1234F")


def test_round_trip_through_purpose_and_role_gates(engine, org):
    _grant_consent(engine, org.tenant_a, org.emp["manager"], "bank_account")
    with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
        encrypt_pii(conn, "employee", "bank_account_encrypted", org.emp["manager"], "1234567890")
    with tenant_session(engine, "tenant_payroll", org.tenant_a) as conn:
        value = decrypt_pii(conn, "employee", "bank_account_encrypted", org.emp["manager"], "payroll_disbursal")
    assert value == "1234567890"


def test_decrypt_rejects_purpose_outside_column_scope(engine, org):
    _grant_consent(engine, org.tenant_a, org.emp["manager"], "bank_account")
    with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
        encrypt_pii(conn, "employee", "bank_account_encrypted", org.emp["manager"], "1234567890")
    with pytest.raises(DBAPIError, match="does not cover"):
        with tenant_session(engine, "tenant_payroll", org.tenant_a) as conn:
            decrypt_pii(conn, "employee", "bank_account_encrypted", org.emp["manager"], "tax_filing")


def test_decrypt_rejects_unknown_purpose(engine, org):
    with pytest.raises(DBAPIError, match="unknown purpose"):
        with tenant_session(engine, "tenant_payroll", org.tenant_a) as conn:
            decrypt_pii(conn, "employee", "bank_account_encrypted", org.emp["manager"], "curiosity")


def test_decrypt_denied_for_role_without_grant(engine, org):
    # tenant_manager is not in app.pii_purpose.allowed_roles for any purpose, so the SQL GRANT
    # on the function itself already stops it before the function body runs.
    with pytest.raises(ProgrammingError, match="permission denied for function decrypt_pii"):
        with tenant_session(engine, "tenant_manager", org.tenant_a) as conn:
            decrypt_pii(conn, "employee", "pan_encrypted", org.emp["manager"], "tax_filing")


def test_decrypt_requires_registered_column(engine, org):
    with pytest.raises(DBAPIError, match="not a registered PII column"):
        with tenant_session(engine, "tenant_payroll", org.tenant_a) as conn:
            decrypt_pii(conn, "employee", "full_name", org.emp["manager"], "tax_filing")


def test_tenant_isolation_on_decrypt(engine, org):
    _grant_consent(engine, org.tenant_b, org.emp_b, "pan")
    with tenant_session(engine, "tenant_hr", org.tenant_b) as conn:
        encrypt_pii(conn, "employee", "pan_encrypted", org.emp_b, "ZZZZZ9999Z")
    with pytest.raises(DBAPIError, match="not found"):
        with tenant_session(engine, "tenant_payroll", org.tenant_a) as conn:
            decrypt_pii(conn, "employee", "pan_encrypted", org.emp_b, "tax_filing")


def test_withdrawn_consent_blocks_decrypt(engine, org):
    _grant_consent(engine, org.tenant_a, org.emp["deep_report"], "ssn")
    with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
        encrypt_pii(conn, "employee", "ssn_encrypted", org.emp["deep_report"], "123-45-6789")
    with engine.begin() as conn:
        conn.execute(text("UPDATE consent_record SET status = 'withdrawn', withdrawn_at = now() "
                          "WHERE employee_id = :e AND data_category = 'ssn'"),
                     {"e": org.emp["deep_report"]})
    with pytest.raises(DBAPIError, match="no active consent"):
        with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
            decrypt_pii(conn, "employee", "ssn_encrypted", org.emp["deep_report"], "identity_verification")


def test_pii_access_is_audited(engine, org):
    _grant_consent(engine, org.tenant_a, org.emp["founder"], "aadhaar")
    with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
        encrypt_pii(conn, "employee", "aadhaar_ekyc_ref", org.emp["founder"], "ekyc-ref-1")
    with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
        decrypt_pii(conn, "employee", "aadhaar_ekyc_ref", org.emp["founder"], "identity_verification")
    with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
        events = conn.execute(text("SELECT event_type FROM audit_log WHERE subject_id = :e ORDER BY created_at"),
                              {"e": org.emp["founder"]}).scalars().all()
    assert events == ["pii.collected", "pii.decrypted"]


def test_encrypted_values_are_never_plaintext_on_disk(engine, org):
    _grant_consent(engine, org.tenant_a, org.emp["report"], "pan")
    with tenant_session(engine, "tenant_hr", org.tenant_a) as conn:
        encrypt_pii(conn, "employee", "pan_encrypted", org.emp["report"], "ABCDE1234F")
    with engine.begin() as conn:
        raw = conn.execute(text("SELECT pan_encrypted FROM employee WHERE id = :e"),
                           {"e": org.emp["report"]}).scalar_one()
    assert b"ABCDE1234F" not in bytes(raw)
