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

## 5. Smoke test result (Oct 13 2026)
Run on CPU (Apple silicon, PyTorch 2.12) with `laya==0.4.6` and `LAYA_REVISION=reviewed`, which the library resolves to
`convaiinnovations/laya` at `55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851` (English checkpoint). 5 tests passed.
- **Parsing works on real output.** Choice answers from both gate schemas parse, probabilities form a distribution,
  `engine_version` carries the pin, and an oversized state fails closed.
- **Latency:** 50 to 300 ms per call once loaded; the first call after load was about 2 s.
- **Quality is what the model card warned about.** A payroll run with a 98% anomaly score and net pay of 1% of gross was
  called `normal` at 0.856 confidence. Do not read anything into the accuracy; this is why gates stay in shadow mode and
  need a fitted calibration. The library also warned that the checkpoint ships invalid temperatures for 11+ option
  questions (not ours: gates use 2 to 3 options).
- **A bug the test found:** `LayaClient` used `Router(preload=True)`, which loads all three checkpoints (about 1.16B
  parameters, three downloads). It now loads only the one it serves (`model="english"` by default).
- Weights download once to the Hugging Face cache; with `HF_HUB_OFFLINE=1` a second run loads from disk in seconds.

