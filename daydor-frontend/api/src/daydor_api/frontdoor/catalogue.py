"""The command catalogue: the reviewed list (commands.json) joined to what the API's own typed endpoints say (their OpenAPI schemas).

An endpoint is a command only if it is listed in commands.json, and the list is checked against the real endpoints, so a renamed or
removed endpoint fails a test instead of confusing the agent. Request schemas come from the endpoints' pydantic models, never retyped.
`commands.generated.json` is the committed result (`python -m daydor_api.frontdoor.catalogue`) so a reviewer sees what the agent can ask for.
"""
from __future__ import annotations

import functools
import json
import re
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
AUTHORED, GENERATED = HERE / "commands.json", HERE / "commands.generated.json"
# Never commands, whatever commands.json says: deciding, paying, filing, posting, removing access, and the platform's own surfaces.
FORBIDDEN_PATH = re.compile(r"/(approvals|inbox|worker-controls|auth|meta|tables|workflows|webhooks|ops|frontdoor)\b|/(disburse|post|deprovision|send-notice|file|resolve)\b")


def _resolve(node: Any, components: dict) -> Any:
    if isinstance(node, dict):
        if "$ref" in node:
            return _resolve(components[node["$ref"].rsplit("/", 1)[-1]], components)
        return {k: _resolve(v, components) for k, v in node.items() if k not in ("title",)}
    if isinstance(node, list):
        return [_resolve(v, components) for v in node]
    return node


def _extra_required(command_id: str) -> list[str]:
    """Fields an endpoint insists on although its schema calls them optional (see hire.py's REQUIRED_AT_START)."""
    if command_id == "hire.start":
        from ..routers.hire import REQUIRED_AT_START
        return sorted(REQUIRED_AT_START)
    return []


def build(app=None) -> list[dict]:
    if app is None:
        from ..app import create_app
        app = create_app()
    spec = app.openapi()
    components = spec.get("components", {}).get("schemas", {})
    out = []
    for c in json.loads(AUTHORED.read_text())["commands"]:
        if FORBIDDEN_PATH.search(c["path"]) or c["method"] not in ("GET", "POST") or (c["kind"] == "query") != (c["method"] == "GET"):
            raise ValueError(f"{c['id']}: {c['method']} {c['path']} cannot be a front-door command")
        op = spec["paths"].get(c["path"], {}).get(c["method"].lower())
        if op is None:
            raise ValueError(f"{c['id']}: {c['method']} {c['path']} is not an endpoint of the API")
        path_params = [{"name": p["name"], "type": "string", "format": "uuid"} for p in op.get("parameters", []) if p["in"] == "path"]
        body = None
        content = op.get("requestBody", {}).get("content", {}).get("application/json")
        if content:
            body = _resolve(content["schema"], components)
        query = [{"name": p["name"], "type": p["schema"].get("type", "string")} for p in op.get("parameters", [])
                 if p["in"] == "query" and p["name"] in ("status", "limit")]
        required = [p["name"] for p in path_params] + list(dict.fromkeys((body or {}).get("required", []) + _extra_required(c["id"])))
        out.append({**c, "path_params": path_params, "query_params": query, "body_schema": body, "required": required})
    return out


@functools.lru_cache(maxsize=1)
def cached() -> list[dict]:
    """build() once per process: the endpoints do not change while it runs."""
    return build()


def for_role(catalogue: list[dict], role: str) -> list[dict]:
    return [c for c in catalogue if role in c["roles"]]


def by_id(catalogue: list[dict]) -> dict[str, dict]:
    return {c["id"]: c for c in catalogue}


def fields(command: dict) -> dict[str, dict]:
    """Every argument a command takes, flattened: name -> {type, required, description, enum, format}."""
    out: dict[str, dict] = {}
    for p in command["path_params"]:
        out[p["name"]] = {"type": "id", "required": True, "format": "uuid"}
    for p in command.get("query_params", []):
        out[p["name"]] = {"type": p["type"], "required": False}
    for name, spec in ((command["body_schema"] or {}).get("properties", {})).items():
        options = spec.get("anyOf") or [spec]
        main = next((o for o in options if o.get("type") != "null"), options[0])
        out[name] = {"type": main.get("type", "string"), "required": name in command["required"], "format": main.get("format"),
                     "enum": main.get("enum"), "description": spec.get("description")}
    return out


def render_for_prompt(commands: list[dict]) -> str:
    lines = []
    for c in commands:
        lines.append(f"- {c['id']} [{c['kind']}, risk {c['risk']}]: {c['summary']}. Use when: {c['when_to_use']}")
        for name, f in fields(c).items():
            bits = [f["type"] + (f" ({f['format']})" if f.get("format") else ""), "required" if f["required"] else "optional"]
            if f.get("enum"):
                bits.append("one of " + "/".join(map(str, f["enum"])))
            lines.append(f"    {name}: {', '.join(bits)}")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    GENERATED.write_text(json.dumps(build(), indent=1, sort_keys=True) + "\n")
