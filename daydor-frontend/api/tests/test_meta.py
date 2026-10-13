from pathlib import Path

import daydor

from daydor_api import enum_scan, gates
from daydor_api.enums import load  # noqa: F401  (module import check)


def test_gate_catalog_has_the_models_gates_the_platform_gate_and_soft_gates():
    cat = {g["id"]: g for g in gates.catalog()}
    hard = [g for g in cat.values() if g["kind"] == "hard"]
    assert len(hard) == 24 and "g_requisition_budget" in cat and "g_agent_action" in cat       # the model's 20 plus platform gates
    assert cat["g_requisition_budget"]["approver_roles"] == ["tenant_founder"]
    assert cat["g_pay_anomaly"]["approver_roles"] == ["tenant_payroll", "daydor_ops"]
    assert {g["id"] for g in cat.values() if g["kind"] == "soft"} == {
        "sg_payroll_anomaly_precheck", "sg_access_request_precheck"}


def test_gates_and_enums_are_served(client, people):
    assert len(client.get("/api/meta/gates", headers=people["hr"]).json()["gates"]) == 26
    enums = client.get("/api/meta/enums", headers=people["hr"]).json()
    assert enums["enums"]["approval_request.status"]["values"] == ["approved", "expired", "pending", "rejected"]


def test_hire_workflow_definition_is_version_6(client, people):
    d = client.get("/api/meta/workflows/hire", headers=people["hr"]).json()
    assert d["version"] == 6 and "s18_payroll_profile" in d["definition"]["states"]
    assert "s08_offer" in d["definition"]["states"]
    assert client.get("/api/meta/workflows/hire", headers=people["employee"]).status_code == 403


def test_provisional_enum_file_matches_what_the_backend_writes():
    """Fails when a backend service starts writing a value the committed file lacks.
    Fix: python scripts/gen_enums.py"""
    import json
    root = Path(daydor.__file__).resolve().parents[2]
    pkg = Path(enum_scan.__file__).parent
    fresh = enum_scan.build(root, json.loads((pkg / "enums" / "overrides.json").read_text()))
    committed = json.loads((pkg / "enums" / "provisional.json").read_text())
    assert fresh == committed, "enum values drifted; run python scripts/gen_enums.py"
