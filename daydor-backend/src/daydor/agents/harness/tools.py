"""Tools a model may call. Read-only, declared in the worker's contract, and tied to the trusted context."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from sqlalchemy import Connection

from daydor.agents.harness.client import ToolDef

SUBMIT = "submit_proposal"
MAX_RESULT_CHARS = 6000


class ToolArgError(ValueError):
    """The arguments are not allowed: wrong shape, or not tied to the trusted context."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    run: Callable[[Connection, Mapping[str, Any], Mapping[str, Any]], Any]          # (conn, args, context) -> JSON-able
    check: Callable[[Mapping[str, Any], Mapping[str, Any]], None] | None = None      # (args, context): raise ToolArgError

    def definition(self) -> ToolDef:
        return ToolDef(self.name, self.description, self.input_schema)


def submit_tool(output_schema: dict[str, Any]) -> ToolDef:
    """The only way to finish: its input IS the typed proposal."""
    return ToolDef(SUBMIT, "Submit your finished draft. Call this exactly once, when you are done.", output_schema)
