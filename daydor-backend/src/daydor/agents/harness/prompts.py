"""Prompts are registry data: a file per worker and version, pinned by sha256 in the worker's contract."""
from __future__ import annotations

import hashlib
import json

from daydor.agents.registry import prompt_path, schema_files


class PromptPinMismatch(RuntimeError):
    pass


def load_prompt(worker: str, version: str, sha256: str) -> str:
    """The prompt text, refused if the file is not the one the contract pinned. A changed prompt is a new version
    (and, from Phase C, a new rollout), never an edit in place."""
    data = prompt_path(worker, version).read_bytes()
    if hashlib.sha256(data).hexdigest() != sha256:
        raise PromptPinMismatch(f"prompt {worker}/{version} does not match its pinned sha256")
    return data.decode()


def load_schema(schema_id: str) -> dict:
    return json.loads(schema_files()[schema_id].read_text())
