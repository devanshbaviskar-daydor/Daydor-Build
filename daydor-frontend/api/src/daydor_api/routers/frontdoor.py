"""The front door over HTTP (backend 0045; `daydor_api.frontdoor`).

`POST /frontdoor/interpret` turns a sentence into a typed command and never runs it. The app shows the command, the person confirms, and the
app calls that endpoint itself, as that person, so permissions, gates and idempotency are the endpoint's own. Off until Daydor enables it for the tenant."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..deps import get_identity
from ..errors import ApiError
from ..frontdoor import agent, catalogue
from ..identity import Identity

router = APIRouter(prefix="/frontdoor", tags=["frontdoor"])


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=agent.MAX_TURN_CHARS)


class Partial(BaseModel):
    id: str = Field(max_length=80)
    args: dict = Field(default_factory=dict)


class Interpret(BaseModel):
    partial: Partial | None = None
    message: str = Field(max_length=agent.MAX_MESSAGE_CHARS)
    history: list[Turn] = Field(default_factory=list, max_length=agent.MAX_HISTORY)


def _need_front_door(ident: Identity) -> None:
    if ident.role not in agent.FRONT_DOOR_ROLES:
        raise ApiError(403, "forbidden", "The front door is for people in a company, not Daydor staff or auditors.")


@router.get("/commands")
def commands(ident: Identity = Depends(get_identity)):
    """What this person's role may ask for: for a command palette, and the same list the agent is shown."""
    _need_front_door(ident)
    return {"commands": [{"id": c["id"], "kind": c["kind"], "risk": c["risk"], "summary": c["summary"],
                          "fields": {k: {"type": f["type"], "required": f["required"]} for k, f in catalogue.fields(c).items()}}
                         for c in catalogue.for_role(catalogue.cached(), ident.role)]}


@router.post("/interpret")
def interpret(body: Interpret, ident: Identity = Depends(get_identity)):
    _need_front_door(ident)
    return agent.interpret(ident, body.message, [t.model_dump() for t in body.history],
                           body.partial.model_dump() if body.partial else None)
