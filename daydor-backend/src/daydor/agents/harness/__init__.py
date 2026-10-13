"""The LLM runtime (Phase B of docs/agentic-infra-plan.md).

A model never touches the database and never decides. It reads a declared, class-capped context and may call a few
read-only tools; its only way to finish is to submit a typed proposal. The proposal is validated against a JSON Schema and
the worker's own rules, stored, and only then committed by an ordinary domain function running under the worker's own
database role, so a misled model cannot exceed the worker's grants. Budgets bound every run.

    client.py    ModelClient interface, the Claude implementation, and a scripted client for tests
    tools.py     tool specs and the argument checks that tie a tool call to the trusted context
    context.py   the declared context, its data-class cap, and the wrapper for untrusted text
    loop.py      the bounded tool loop
    handler.py   turns a worker spec into a queue handler: propose, validate, store, commit or hold
"""
