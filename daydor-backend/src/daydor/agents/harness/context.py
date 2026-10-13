"""The context a model is given: declared columns only, capped by data class, and untrusted text kept apart."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from daydor.model import load_model

CLASS_RANK = {"S": 0, "C0": 1, "C1": 2, "C2": 3, "C3": 4, "C4": 5}
MAX_UNTRUSTED_CHARS = 4000


class ForbiddenContext(ValueError):
    pass


def check_refs(refs: Sequence[str], max_class: str) -> None:
    """Every ref is a real, unencrypted model column no more sensitive than `max_class`, which is itself never C3 or C4.
    The registry checks the same at validation time; this is the runtime's own check, as for soft gates."""
    if max_class not in ("S", "C0", "C1", "C2"):
        raise ForbiddenContext(f"max_data_class {max_class} may never reach a model")
    model = load_model()
    for ref in refs:
        table, _, column = ref.partition(".")
        col = model.table(table).column(column)
        if col.encrypted or CLASS_RANK[col.cls] >= CLASS_RANK["C3"]:
            raise ForbiddenContext(f"{ref} is {col.cls}; restricted data never reaches a model")
        if CLASS_RANK[col.cls] > CLASS_RANK[max_class]:
            raise ForbiddenContext(f"{ref} is {col.cls}, above this worker's limit {max_class}")


def check_context(context: Mapping[str, Any], refs: Sequence[str]) -> None:
    """What a builder returned has exactly the declared fields and no others."""
    extra = set(context) - set(refs)
    if extra:
        raise ForbiddenContext(f"context has undeclared fields {sorted(extra)}")


@dataclass(frozen=True)
class Untrusted:
    """Text a person or a document supplied. It is shown to the model as data, never as instructions, and anything
    extracted from it still passes the proposal's schema and rules before it can reach a tool or a table."""
    source: str
    text: str


def render_untrusted(items: Sequence[Untrusted]) -> str:
    out = []
    for item in items:
        text = item.text[:MAX_UNTRUSTED_CHARS]
        text = text.replace("<", "&lt;")                         # nothing inside can close or open a tag of ours
        out.append(f'<untrusted_input source="{item.source}">\n{text}\n</untrusted_input>')
    return "\n".join(out)


def render_context(context: Mapping[str, Any]) -> str:
    lines = [f"{k}: {v}" for k, v in sorted(context.items())]
    return "<context>\n" + "\n".join(lines) + "\n</context>"
