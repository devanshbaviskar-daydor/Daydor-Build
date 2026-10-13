"""The exit flow's hand-written workflow definition, replacing the generated skeleton for
`name='exit'` (same convention as `daydor.hire.workflow`).

Three departures from the hire flow's own pattern, beyond the usual "position check runs
synchronously before start()" (`termination` here, same as `job_requisition` there):

1. **`g_legalhold` and `g_finalpay` are native, engine-level transition gates** (checked against
   the instance's fixed subject, `termination.id`, same as every one of hire's gates) because
   neither approval corresponds to a specific guarded column elsewhere -- `g_legalhold` is a pure
   override-to-proceed-despite-a-hold checkpoint (conditional on `requires_g_legalhold`, set by
   `daydor.exit.legal_hold.handle_legal_hold_checker`, the model's "root orchestrator"); `g_finalpay`
   approves the *calculated settlement amounts* themselves (`daydor.exit.final_settlement.
   handle_final_pay_calculator` sets them via `context_patch` on the same transition that gates on
   them, the same "gate the outgoing transition" correction hire uses for `g_aedt`/`g_offer_band`).

2. **`g_it_deprov`, `g_pay_disburse` and `g_cobra` are *not* engine-level gates**, even though
   they're real hard gates with real DB-enforced column guards
   (`migrations/sql/0006_gates.sql`/`0022_exit_gate_guards.sql`). Each one's guard checks the
   approval's `subject_id` against a *different* row's own id
   (`identity_account`/`final_settlement`/`cobra_event`, not `termination`) -- using the engine's
   native `gate` field here would request a second, redundant approval against the wrong subject
   that could never satisfy the real guard. So these three transitions carry no `gate` key at all;
   `daydor.exit.deprovisioning.deprovision_identity`, `daydor.exit.final_settlement.
   disburse_final_settlement` and `daydor.exit.cobra.send_cobra_notice` are the functions that
   actually fire `advance`, and each is only reachable once its own guarded write has already
   succeeded.

3. **`final_settlement` is written in two steps, not one** (s06/s07): `g_finalpay` has to resolve
   before anything is persisted (point 1), but `final_settlement.total_settlement` is `derived` --
   no role has an INSERT grant on it at all (finding 20) -- so s07's `final_settlement_opener`
   calls `app.open_final_settlement` once the amounts are approved, rather than s06 writing the
   row directly.

Versions: `app.workflow_definition` version 1 is the generated skeleton (`0010_workflow_seed.sql`),
version 2 (this one) is Sprints 10-11's full definition (`0023_exit_workflow.sql`), covering all
14 model steps across both sprints in one go since they were built together.
"""
from __future__ import annotations

import json
from datetime import date
from uuid import UUID

from sqlalchemy import Connection

from daydor.exit.termination import initiate_termination
from daydor.workflow.engine import WorkflowEngine

EXIT_DEFINITION = {
    "title": "Termination to full and final (hand-written, steps 1-14)",
    "description": "Holds checked, access cut, settlement gated, retention clocks start: "
                   "termination, legal hold check, termination checklist, identity "
                   "deprovisioning, device return, final settlement (calculated, approved, "
                   "disbursed), COBRA (US only), close-out.",
    "initial": "start",
    "states": {
        "start": {"terminal": False, "on": {"advance": {"to": "s01_termination"}}},
        "s01_termination": {
            "terminal": False,
            "on": {"advance": {"to": "s02_legal_hold_check"}},
        },
        "s02_legal_hold_check": {
            "terminal": False,
            "enter_jobs": [{"queue": "hr", "kind": "legal_hold_checker"}],
            "on": {"advance": {"to": "s03_checklist", "gate": "g_legalhold",
                              "gate_if": "requires_g_legalhold"}},
        },
        "s03_checklist": {
            "terminal": False,
            "enter_jobs": [{"queue": "hr", "kind": "termination_checklist_builder"}],
            "on": {"advance": {"to": "s04_identity_account"}},
        },
        "s04_identity_account": {
            "terminal": False,
            "enter_jobs": [{"queue": "it", "kind": "deprovisioning_agent"}],
            "on": {"advance": {"to": "s05_device_assignment"}},
        },
        "s05_device_assignment": {
            "terminal": False,
            "enter_jobs": [{"queue": "it", "kind": "equipment_return_tracker"}],
            "on": {"advance": {"to": "s06_final_settlement_calc"}},
        },
        "s06_final_settlement_calc": {
            "terminal": False,
            "enter_jobs": [{"queue": "pay", "kind": "final_pay_calculator"}],
            "on": {"advance": {"to": "s07_final_settlement_created", "gate": "g_finalpay"}},
        },
        "s07_final_settlement_created": {
            "terminal": False,
            "enter_jobs": [{"queue": "pay", "kind": "final_settlement_opener"}],
            "on": {"advance": {"to": "s08_disbursed"}},
        },
        "s08_disbursed": {
            "terminal": False,
            "enter_jobs": [{"queue": "pay", "kind": "direct_deposit_disburser"}],
            "on": {"advance": {"to": "s09_cobra"}},
        },
        "s09_cobra": {
            "terminal": False,
            "enter_jobs": [{"queue": "hr", "kind": "cobra_trigger_detector"}],
            "on": {"advance": {"to": "s10_closeout"}},
        },
        "s10_closeout": {
            "terminal": False,
            "enter_jobs": [{"queue": "hr", "kind": "employee_closeout"}],
            "on": {"advance": {"to": "done"}},
        },
        "done": {"terminal": True},
    },
}


def start_exit(conn: Connection, engine: WorkflowEngine, *, employee_id: UUID, termination_type: str,
              reason_code: str, notice_date: date, last_working_day: date,
              initiated_by_user_id: UUID) -> UUID:
    """Creates the termination row and starts the exit workflow instance against it, advancing
    synchronously through the one already-done step so the transition log records it. Returns the
    workflow_instance id. Idempotent per employee: a replay returns the existing instance
    without advancing it."""
    termination_id = initiate_termination(
        conn, employee_id=employee_id, termination_type=termination_type, reason_code=reason_code,
        notice_date=notice_date, last_working_day=last_working_day,
        initiated_by_user_id=initiated_by_user_id)
    context = {"employee_id": str(employee_id), "termination_id": str(termination_id)}
    instance_id = engine.start(conn, "exit", "termination", termination_id, context)
    # Fixed event ids make a replayed start a no-op (see daydor.hire.workflow.start_hire).
    engine.fire(conn, instance_id, "advance", event_id=f"start:{instance_id}:1")  # start -> s01_termination
    engine.fire(conn, instance_id, "advance", event_id=f"start:{instance_id}:2")  # -> s02_legal_hold_check (enqueues the checker)
    return instance_id


def seed_sql(version: int) -> str:
    """Each call is a one-off, hand-authored migration (see daydor.hire.workflow.seed_sql)."""
    body = json.dumps(EXIT_DEFINITION, sort_keys=True).replace("'", "''")
    return "\n".join([
        "-- Hand-written, NOT generated: see daydor.exit.workflow.EXIT_DEFINITION for why.",
        f"-- Supersedes 'exit' version {version - 1}.",
        "SET ROLE daydor_schema_owner;",
        "",
        "UPDATE app.workflow_definition SET active = false WHERE name = 'exit' AND active;",
        "INSERT INTO app.workflow_definition (name, version, definition, source) "
        f"VALUES ('exit', {version}, '{body}'::jsonb, 'hand-written');",
        "",
        "RESET ROLE;",
        "",
    ])


if __name__ == "__main__":  # pragma: no cover
    from pathlib import Path
    Path("migrations/sql/0023_exit_workflow.sql").write_text(seed_sql(2))
    print("wrote migrations/sql/0023_exit_workflow.sql")
