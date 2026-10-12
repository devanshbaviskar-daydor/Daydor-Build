"""Hire flow step 12: consent_record.

`consent_record` has no agent writer by design -- only the employee may grant their own consent
(table grant `E: WRITE`; see docs/backend-plan.md's "known model gaps" list and
daydor.privacy.pii, which is what actually checks these rows later). So s12_consent_record has no
`enter_jobs`: there is no agent work to do here, only a gate (`dpdp_consent`) to wait on.

`request_consent` is the function that actually advances past it -- called once the employee has
done their part (granted whatever consent_record rows they're going to grant). Unlike
`daydor.hire.screening.submit_application` and other "a real-world event happened" triggers, this
one doesn't need to look at whether consent_record rows actually exist: that's what the
`dpdp_consent` gate is for (the employee resolves it themselves, same mechanism as every other
hard gate), not something this function should duplicate-check.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection

from daydor.workflow.engine import TransitionResult, WorkflowEngine


def request_consent(conn: Connection, engine: WorkflowEngine, instance_id: UUID) -> TransitionResult:
    return engine.fire(conn, instance_id, "advance")
