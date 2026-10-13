"""Smoke test of LayaClient against a REAL pinned checkpoint (ADR-005, docs/laya-runbook.md).

Skipped unless `laya` is installed and LAYA_REVISION is set, so the normal suite never loads weights:

    pip install -e ".[laya]"
    LAYA_REVISION=reviewed pytest tests/test_laya_smoke.py -s

It checks that real output parses through `LayaClient._parse`, that the gates' own schemas work, that
truncation fails closed, and records latency. It does NOT assert accuracy: base checkpoints are near
chance zero-shot, and only fine-tuning, calibration and our own shadow data count as evidence.
"""
import os
import time

import pytest

pytest.importorskip("laya", reason="laya is not installed (pip install -e '.[laya]')")
if not os.environ.get("LAYA_REVISION"):
    pytest.skip("LAYA_REVISION is not set", allow_module_level=True)

from daydor.gates.decider import DeciderTruncated, LayaClient  # noqa: E402
from daydor.hire.access_grant import SCHEMA as ACCESS_SCHEMA  # noqa: E402
from daydor.payroll.anomaly import SCHEMA as PAYROLL_SCHEMA  # noqa: E402


@pytest.fixture(scope="module")
def client():
    c = LayaClient(model="english")      # the soft gates read English text; load once, outside the timed calls
    c._predict()
    return c


CASES = [
    (PAYROLL_SCHEMA, {"gross_total": 1_200_000.0, "net_total": 980_000.0, "anomaly_score": 0.02}, "run_looks"),
    (PAYROLL_SCHEMA, {"gross_total": 9_900_000.0, "net_total": 120_000.0, "anomaly_score": 0.97}, "run_looks"),
    (ACCESS_SCHEMA, {"app_name": "email", "permission_level": "standard", "title": "Engineer"}, "request_looks"),
    (ACCESS_SCHEMA, {"app_name": "prod-db", "permission_level": "admin", "title": "Receptionist"}, "request_looks"),
]


@pytest.mark.parametrize("schema,state,question", CASES)
def test_real_output_parses_and_is_a_distribution(client, schema, state, question):
    started = time.monotonic()
    result = client.decide(schema, state, timeout_s=5.0)
    ms = (time.monotonic() - started) * 1000
    answer = result.answers[question]
    assert result.engine == "laya" and result.engine_version and "unpinned" not in result.engine_version
    assert abs(sum(answer.probabilities.values()) - 1) < 0.02
    assert 0 <= answer.confidence <= 1
    print(f"\n{schema.name} {state} -> {answer.value} {answer.confidence:.3f} in {ms:.0f} ms ({result.engine_version})")


def test_an_oversized_state_fails_closed(client):
    with pytest.raises(DeciderTruncated):
        client.decide(PAYROLL_SCHEMA, {"note": "x" * 5000}, timeout_s=5.0)
