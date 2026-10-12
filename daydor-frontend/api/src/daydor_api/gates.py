"""Gate catalog: the model's hard gates plus the platform's own, with approver roles as database
roles. Read from the backend's own definitions, never re-typed here."""
from __future__ import annotations

from daydor.gates.registry import PLATFORM_HARD_GATES, SOFT_GATES
from daydor.model.loader import ROLE_DB

from .access import model


def catalog() -> list[dict]:
    out = [{"id": g["id"], "label": g["label"], "kind": "hard", "tables": g["tables"],
            "approver_roles": [ROLE_DB[a] for a in g["ap"]], "source": g["src"]} for g in model().gates]
    out += [{"id": g.gate_id, "label": g.label, "kind": "hard", "tables": list(g.tables),
             "approver_roles": list(g.approver_roles), "source": "platform"} for g in PLATFORM_HARD_GATES]
    out += [{"id": s.gate_id, "label": s.label, "kind": "soft", "tables": list(s.tables),
             "approver_roles": [], "source": "platform", "escalates_to": s.escalate_to, "mode": s.mode}
            for s in SOFT_GATES]
    return out


def by_id() -> dict[str, dict]:
    return {g["id"]: g for g in catalog()}
