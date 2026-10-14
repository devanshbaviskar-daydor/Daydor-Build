"""The consumer of clock and escalation events: turns them into notifications for the role that must act (0044).

Queue handler for kind 'notify.event' (queue 'notify'), run as the `root-orchestrator` platform actor. Idempotent: a notification has a
dedupe key, so a redelivered event adds nothing. A notification tells a role something; it never does anything.
"""
from __future__ import annotations

from sqlalchemy import Connection, text

from daydor.queue.worker import Job

QUEUE, KIND = "notify", "notify.event"
OWNER_ROLE = {"hr": "tenant_hr", "payroll": "tenant_payroll", "it": "tenant_it", "founder": "tenant_founder", "ops": "daydor_ops"}


def _notify(conn: Connection, audience: str, kind: str, severity: str, title: str, subject_table, subject_id, detail: dict, dedupe: str):
    import json
    return conn.execute(text("SELECT app.notify(:a, :k, :s, :t, :st, CAST(:si AS uuid), CAST(:d AS jsonb), :dk)"),
                        {"a": audience, "k": kind, "s": severity, "t": title, "st": subject_table, "si": subject_id,
                         "d": json.dumps(detail, default=str), "dk": dedupe}).scalar_one_or_none()


def handle_notify_event(conn: Connection, job: Job) -> dict:
    topic, data = job.payload.get("topic"), job.payload.get("data") or {}
    table, subject = job.payload.get("subject_table"), job.payload.get("subject_id")
    if topic in ("clock.due_soon", "clock.overdue"):
        stage = topic.split(".", 1)[1]
        verb = "due" if stage == "due_soon" else "overdue since"
        made = _notify(conn, OWNER_ROLE[data["owner"]], "clock", stage, f"{data['label']}: {verb} {data['due_on']}", table, subject,
                       {"clock": data["clock"], "due_on": data["due_on"]}, f"{topic}:{data['clock']}:{subject}")
    elif topic == "approval.escalated":
        made = _notify(conn, data["escalate_to"], "approval", "escalated", f"Waiting too long: {data['gate_label']}", table, subject,
                       {"approval_request_id": data["approval_request_id"], "gate": data["gate_id"], "deadline_at": data["deadline_at"]},
                       f"approval.escalated:{data['approval_request_id']}")
    else:
        return {"ignored": topic}
    return {"notification": str(made) if made else None}
