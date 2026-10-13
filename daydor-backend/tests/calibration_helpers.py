"""An approved calibration for a soft gate, for tests that switch a gate to enforce mode.

The database refuses `mode = 'enforce'` without an approved calibration of that gate (0036), and an approved
calibration must meet the promotion criteria and carry a sign-off, so a test that enforces a gate says so by
recording one that does. Calibrations are never deleted, so this is idempotent and leaves the row in place."""
from sqlalchemy import Connection, text


def approve_calibration(conn: Connection, gate_id: str, version: str | None = None) -> str:
    version = version or f"test-cal:{gate_id}"
    conn.execute(text(
        "INSERT INTO app.gate_calibration (version, gate_id, checkpoint, n_labels, n_rarer_label, ece, "
        "rule_baseline_beaten, disagreement_rate, auto_pass_threshold, shadow_clean_since) "
        "VALUES (:v, :g, 'english', 400, 80, 0.05, true, 0.005, 0.5, DATE '2026-01-01') "
        "ON CONFLICT (version) DO NOTHING"), {"v": version, "g": gate_id})
    conn.execute(text("UPDATE app.gate_calibration SET status = 'approved', signed_off_by = 'test owner', "
                      "signed_off_at = now() WHERE version = :v AND status = 'candidate'"), {"v": version})
    return version
