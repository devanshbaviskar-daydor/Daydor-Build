"""Model clients. Everything else in the harness talks to `ModelClient`, never to a vendor SDK."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence

# Model by tier. Override per tier with DAYDOR_MODEL_SMALL / _MEDIUM / _LARGE.
DEFAULT_MODELS = {"small": "claude-haiku-5-5", "medium": "claude-sonnet-5-5", "large": "claude-opus-5-5"}


def model_for_tier(tier: str) -> str:
    return os.environ.get(f"DAYDOR_MODEL_{tier.upper()}") or DEFAULT_MODELS[tier]


def prices() -> dict[str, tuple[float, float]]:
    """USD per million input and output tokens, by model id, from DAYDOR_MODEL_PRICES (a JSON object). Nothing is built in:
    a price that is not configured is a cost that is not known, and a cost budget is only enforced where it is."""
    raw = os.environ.get("DAYDOR_MODEL_PRICES", "").strip()
    return {m: (float(v[0]), float(v[1])) for m, v in json.loads(raw).items()} if raw else {}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    p = prices().get(model)
    return None if p is None else (input_tokens * p[0] + output_tokens * p[1]) / 1_000_000


class ModelError(RuntimeError):
    """The model call failed (network, API error, timeout). Retried by the queue like any other job failure."""


@dataclass(frozen=True)
class Block:
    """One content block of a model turn: text, or a request to call a tool."""
    type: str                                   # 'text' | 'tool_use'
    text: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict[str, Any] | None = None

    def as_message(self) -> dict[str, Any]:
        if self.type == "text":
            return {"type": "text", "text": self.text or ""}
        return {"type": "tool_use", "id": self.id, "name": self.name, "input": self.input or {}}


@dataclass(frozen=True)
class ModelTurn:
    blocks: tuple[Block, ...]
    stop_reason: str                            # 'end_turn' | 'tool_use' | 'max_tokens' | ...
    input_tokens: int
    output_tokens: int
    model: str
    latency_ms: int = 0

    @property
    def tool_uses(self) -> list[Block]:
        return [b for b in self.blocks if b.type == "tool_use"]


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    input_schema: dict[str, Any]


class ModelClient(Protocol):
    def complete(self, *, model: str, system: str, messages: list[dict[str, Any]], tools: Sequence[ToolDef],
                 max_tokens: int, timeout_s: float) -> ModelTurn: ...


class ClaudeClient:
    """The Anthropic Messages API with tool use. Reads ANTHROPIC_API_KEY. Not used by the test suite: CI never calls the
    network (see ScriptedClient)."""

    def __init__(self, sdk_client: Any | None = None) -> None:
        self._sdk = sdk_client

    def _client(self):
        if self._sdk is None:
            try:
                import anthropic
            except ImportError as exc:
                raise ModelError("the anthropic package is not installed") from exc
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise ModelError("ANTHROPIC_API_KEY is not set")
            self._sdk = anthropic.Anthropic(max_retries=0)           # retries belong to the queue, which also records them
        return self._sdk

    def complete(self, *, model: str, system: str, messages: list[dict[str, Any]], tools: Sequence[ToolDef],
                 max_tokens: int, timeout_s: float) -> ModelTurn:
        started = time.monotonic()
        try:
            resp = self._client().messages.create(
                model=model, max_tokens=max_tokens, system=system, messages=messages, timeout=timeout_s,
                tools=[{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools])
        except ModelError:
            raise
        except Exception as exc:  # noqa: BLE001 - any SDK or network failure is a failed model call
            raise ModelError(f"{type(exc).__name__}: {exc}") from exc
        blocks = []
        for b in resp.content:
            if b.type == "text":
                blocks.append(Block("text", text=b.text))
            elif b.type == "tool_use":
                blocks.append(Block("tool_use", id=b.id, name=b.name, input=dict(b.input)))
        return ModelTurn(tuple(blocks), resp.stop_reason or "", resp.usage.input_tokens, resp.usage.output_tokens, model,
                         int((time.monotonic() - started) * 1000))


@dataclass
class ScriptedClient:
    """A fake model for tests: plays back prepared turns and records what it was asked. No network, no randomness."""
    turns: list[ModelTurn]
    seen: list[dict[str, Any]] = field(default_factory=list)

    def complete(self, *, model, system, messages, tools, max_tokens, timeout_s) -> ModelTurn:
        self.seen.append({"model": model, "system": system, "messages": json.loads(json.dumps(messages)),
                          "tools": [t.name for t in tools], "max_tokens": max_tokens})
        if not self.turns:
            raise ModelError("the scripted client ran out of turns")
        return self.turns.pop(0)


def turn(*blocks: Block, stop: str = "tool_use", inp: int = 100, out: int = 50, model: str = "scripted-model") -> ModelTurn:
    return ModelTurn(tuple(blocks), stop, inp, out, model, 5)


def call(name: str, args: dict[str, Any], id: str = "t1") -> Block:
    return Block("tool_use", id=id, name=name, input=args)


def say(text: str) -> Block:
    return Block("text", text=text)
