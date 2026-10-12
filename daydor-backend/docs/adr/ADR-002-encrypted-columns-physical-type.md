# ADR-002: Encrypted columns are stored as bytea

Status: accepted, Oct 8 2026

Columns marked `enc` in the model (Aadhaar e-KYC ref, PAN, SSN, bank account, ER notes and
others) are stored as `bytea` whatever their logical type, and are never granted to any role.
They are read only through `app.decrypt_pii(table.column, row_id, purpose)`, which checks the
purpose registry and consent, then writes `audit_log`. Dev uses a pgcrypto symmetric key held in
a server setting; production replaces it with per-tenant data keys from a KMS.
