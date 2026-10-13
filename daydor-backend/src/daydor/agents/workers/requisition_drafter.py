"""requisition-drafter: drafts a job description for a requisition from the seat's job profile and the hiring manager's notes.

The reference LLM worker for the harness. What it is given, may do and must produce is its registry contract
(registry/worker_classification.json, `contract`), the prompt is pinned (registry/prompts/requisition-drafter/v1.md), and the
output is `requisition_draft/1` (registry/schemas).

The model has no place to put a job description: no model table has a column for one (finding 32). So the committed proposal is the
draft: it is stored, validated and attributed in app.agent_proposal, and committing it tells the next step (`requisition_drafted`,
queue 'ta') that a draft is ready for a person. That job is held until a person acknowledges the run, because this worker acts at
`review`. Writing the text onto a requisition or a posting is a model change someone has to decide.

Queue handler: kind 'requisition_drafter', queue 'ta', payload {"requisition_id": ..., "hiring_manager_notes": ...}.
Not wired into the hire flow: the flow still opens the requisition deterministically (daydor.hire.requisition).
"""
from __future__ import annotations

import re
from typing import Any, Mapping
from uuid import UUID

from sqlalchemy import Connection, text

from daydor.agents.harness.context import Untrusted
from daydor.agents.harness.handler import LLMWorkerSpec, make_handler
from daydor.agents.harness.tools import ToolArgError, ToolSpec
from daydor.queue import enqueue
from daydor.queue.worker import Job

WORKER = "requisition-drafter"
QUEUE, KIND, NEXT_KIND = "ta", "requisition_drafter", "requisition_drafted"

# A first pass at what a job description must not say. It is a safety net under the prompt, not the policy: a person reads the draft.
PROTECTED = re.compile(
    r"\b(young|youthful|energetic young|digital native|recent graduates?|fresh graduates?|mature|elderly|older|"
    r"male|female|man|woman|men|women|he|she|his|her|salesman|chairman|manpower|"
    r"christian|muslim|hindu|jewish|sikh|buddhist|"
    r"married|unmarried|single|pregnan\w*|disabled|able-bodied|healthy|"
    r"native speaker|local candidates?|caste|race|ethnic\w*)\b", re.I)
PAY = re.compile(r"(?:[$₹€£]|\brs\.?|\binr\b|\busd\b|\beur\b)\s?\d|\b\d[\d,.]*\s?(?:lpa|lakhs?|crores?|k\b)|\bper annum\b|\bsalary\b|\bcompensation\b", re.I)


def build_context(conn: Connection, job: Job) -> tuple[dict, list[Untrusted]]:
    requisition_id = UUID(str(job.payload["requisition_id"]))
    row = conn.execute(text(
        "SELECT jp.title, jp.job_family, jp.level, jp.description, d.name AS department "
        "FROM job_requisition jr JOIN position p ON p.id = jr.position_id "
        "JOIN job_profile jp ON jp.id = p.job_profile_id JOIN department d ON d.id = p.department_id "
        "WHERE jr.id = :r"), {"r": requisition_id}).one()
    context = {"job_profile.title": row.title, "job_profile.job_family": row.job_family, "job_profile.level": row.level,
               "job_profile.description": row.description, "department.name": row.department}
    notes = str(job.payload.get("hiring_manager_notes") or "")
    return context, ([Untrusted("hiring_manager_notes", notes)] if notes.strip() else [])


def rules(proposal: Mapping[str, Any], context: Mapping[str, Any]) -> list[str]:
    """Business rules a schema cannot say."""
    problems = []
    text_parts = [proposal["title"], proposal["summary"], *proposal["responsibilities"], *proposal["requirements"],
                  *proposal.get("nice_to_have", [])]
    blob = "\n".join(text_parts)
    if (m := PROTECTED.search(blob)):
        problems.append(f"the draft uses '{m.group(0)}', which can read as a preference for or against a group of people; say what the work needs instead")
    if (m := PAY.search(blob)):
        problems.append(f"the draft mentions pay ('{m.group(0)}'); pay is handled elsewhere, leave it out")
    for field_name, items in (("responsibilities", proposal["responsibilities"]), ("requirements", proposal["requirements"])):
        if len({i.strip().lower() for i in items}) != len(items):
            problems.append(f"{field_name} repeats an item")
    return problems


def _similar_titles(conn: Connection, args: Mapping[str, Any], context: Mapping[str, Any]) -> list[str]:
    return conn.execute(text("SELECT DISTINCT title FROM job_profile WHERE job_family = :f ORDER BY title LIMIT 10"),
                        {"f": args["job_family"]}).scalars().all()


def _only_this_family(args: Mapping[str, Any], context: Mapping[str, Any]) -> None:
    if args["job_family"] != context["job_profile.job_family"]:
        raise ToolArgError("job_family must be the family of the role you are drafting")


TOOLS = {"list_similar_titles": ToolSpec(
    "list_similar_titles", "List job titles that already exist in the same job family, for wording consistency.",
    {"type": "object", "additionalProperties": False, "required": ["job_family"],
     "properties": {"job_family": {"type": "string", "maxLength": 100}}},
    _similar_titles, _only_this_family)}


def commit(conn: Connection, job: Job, proposal: Mapping[str, Any], context: Mapping[str, Any]) -> dict:
    """Tell the next step a draft is ready. Under review the job is held until a person acknowledges the run."""
    requisition_id = str(job.payload["requisition_id"])
    nxt = enqueue(conn, QUEUE, NEXT_KIND, {"requisition_id": requisition_id, "title": proposal["title"]},
                  idempotency_key=f"{NEXT_KIND}:{requisition_id}")
    return {"requisition_id": requisition_id, "title": proposal["title"], "next_job": str(nxt)}


SPEC = LLMWorkerSpec(WORKER, TOOLS, build_context, rules, commit)


def handle_requisition_drafter(client_factory=None):
    return make_handler(SPEC, client_factory) if client_factory else make_handler(SPEC)
