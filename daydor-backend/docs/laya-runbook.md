# Laya runbook

How to run the Laya smoke test, pin a checkpoint and promote a soft gate. Written Oct 13 2026 with the
adoption of ADR-005. Nothing here changes behaviour until you follow it: the default `LayaClient` refuses to
load weights without `LAYA_REVISION`, so every soft gate fails closed and, in shadow mode, escalates.

## 1. Smoke test (once per checkpoint or library bump)
```bash
python3 -m venv .venv-laya && source .venv-laya/bin/activate
pip install -e ".[dev,laya]"                 # pulls PyTorch; about 0.65 to 0.8 GB of weights per checkpoint
LAYA_REVISION=reviewed pytest tests/test_laya_smoke.py -s
```
`reviewed` uses the library's own reviewed pins. For production use a commit SHA, and see section 2.
The test checks parsing of real output, a valid distribution, a pinned `engine_version`, and fail-closed
truncation, and prints latency (expect 0.2 to 0.5 s on CPU, 33 to 40 ms on a T4). It asserts no accuracy.
**Do not enable a gate beyond shadow mode on the strength of this test.**

## 2. Pinning and vendoring (production images)
- Set `LAYA_REVISION` (commit SHA) and `LAYA_SHA256_DIGESTS`; vendor the weights into the image; set
  `HF_HUB_OFFLINE=1` so nothing downloads at runtime.
- Every evaluation stores `engine_version` (repo and revision).
- `laya-serve` (later) binds `0.0.0.0` without authentication by default: bind it privately and set
  `LAYA_API_KEY`.

## 3. Shadow, calibration, enforce
1. Leave the gate in `shadow`: the database forces `escalate`, and each evaluation is logged beside the
   human outcome on the hard gate.
2. Label from shadow data (needs the example store, not built), fit temperatures per (question type,
   option count) with `laya.calibrate`, and publish a `calibration_version`.
3. Only then `UPDATE app.gate_definition SET mode = 'enforce', calibration_version = '<v>'`. The database
   refuses `enforce` without one (`gate_definition_enforce_needs_calibration`).
4. Promotion criteria are in `docs/backend-plan.md`, "Soft gates with Laya".
