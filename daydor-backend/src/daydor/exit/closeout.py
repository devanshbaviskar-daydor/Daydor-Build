"""Exit flow steps 12-14: vesting-schedule-tracker (read, may legitimately be empty --
equity/vesting is written by Merit's backlogged grant-drafter/vesting-schedule-tracker, not this
flow), rehire-eligibility-flagger, and employee-record-writer's close-out
(`is_active = false`, `date_of_exit` -- the Gratuity Act retention anchor).
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import Connection, text

from daydor.exit.termination import close_employee_record, flag_rehire_eligibility
from daydor.queue.worker import Job
from daydor.workflow.engine import WorkflowEngine


def read_vesting_events(conn: Connection, *, employee_id: UUID) -> list[UUID]:
    return conn.execute(
        text("SELECT ve.id FROM vesting_event ve JOIN equity_grant eg ON eg.id = ve.equity_grant_id "
             "WHERE eg.employee_id = :e"), {"e": employee_id}).scalars().all()


def close_out_employee(conn: Connection, *, employee_id: UUID, termination_id: UUID,
                       last_working_day: date, rehire_eligible: str) -> dict:
    vesting_ids = read_vesting_events(conn, employee_id=employee_id)
    flag_rehire_eligibility(conn, termination_id=termination_id, rehire_eligible=rehire_eligible)
    close_employee_record(conn, employee_id=employee_id, date_of_exit=last_working_day)
    return {"vesting_event_ids": vesting_ids}


def handle_employee_closeout(engine: WorkflowEngine):
    """Queue handler for kind 'employee_closeout' (exit flow steps 12-14, queue 'hr'). Defaults to
    rehire-eligible; a real flagger would weigh the termination_type/reason_code."""
    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        employee_id = UUID(ctx["employee_id"])
        termination_id = UUID(ctx["termination_id"])
        last_working_day = conn.execute(
            text("SELECT last_working_day FROM termination WHERE id = :t"),
            {"t": termination_id}).scalar_one()
        result = close_out_employee(conn, employee_id=employee_id, termination_id=termination_id,
                                    last_working_day=last_working_day, rehire_eligible="eligible")
        engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}")
        return {"vesting_event_count": len(result["vesting_event_ids"])}
    return handle


# ---------------------------------------------------------------------------------------------
# One handler per worker (exit workflow version 3). `employee_closeout` above does three workers'
# jobs in one transaction, which a single worker role cannot do; these split it so each step runs as
# the worker that owns it. Version 2 instances in flight keep using `employee_closeout`.
# ---------------------------------------------------------------------------------------------
def handle_vesting_schedule_tracker(engine: WorkflowEngine):
    """Queue handler for kind 'vesting_schedule_tracker' (exit step 12, queue 'hr'). Read-only here:
    equity is written by Merit's grant-drafter, so an employee with none is a normal case."""
    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        vesting_ids = read_vesting_events(conn, employee_id=UUID(ctx["employee_id"]))
        engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}")
        return {"vesting_event_count": len(vesting_ids)}
    return handle


def handle_rehire_eligibility_flagger(engine: WorkflowEngine):
    """Queue handler for kind 'rehire_eligibility_flagger' (exit step 13, queue 'hr'). Defaults to
    rehire-eligible; a real flagger would weigh the termination_type/reason_code."""
    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        flag_rehire_eligibility(conn, termination_id=UUID(ctx["termination_id"]), rehire_eligible="eligible")
        engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}")
        return {"rehire_eligible": "eligible"}
    return handle


def handle_employee_record_writer_closeout(engine: WorkflowEngine):
    """Queue handler for kind 'employee_record_writer_closeout' (exit step 14, queue 'hr'):
    employee-record-writer's close-out, `is_active = false` and `date_of_exit`."""
    def handle(conn: Connection, job: Job) -> dict:
        ctx = job.payload["context"]
        last_working_day = conn.execute(
            text("SELECT last_working_day FROM termination WHERE id = :t"),
            {"t": UUID(ctx["termination_id"])}).scalar_one()
        close_employee_record(conn, employee_id=UUID(ctx["employee_id"]), date_of_exit=last_working_day)
        engine.fire(conn, UUID(job.payload["workflow_instance_id"]), "advance", event_id=f"job:{job.id}")
        return {"date_of_exit": str(last_working_day)}
    return handle
