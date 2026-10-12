# ADR-001: Postgres-based queue and state machines

Status: accepted, Oct 8 2026

## Context
Workflows (hire, payroll, exit, erasure, merit, threshold) need durable steps, retries, timers
(I-9 three-business-day clock, COBRA windows, 409A staleness, expiries) and human waits at gates.
Options were a durable-execution engine (e.g. Temporal) or Postgres queues and state machines.

## Decision
Use Postgres for now: a `job` table claimed with `FOR UPDATE SKIP LOCKED`, an `outbox` table
written in the same transaction as business data, a `timer` table for due-dated wake-ups, and
state machines whose definitions and transitions are rows.

## Consequences
- One system to operate; workflow state commits atomically with business data.
- Fine for the expected load (tens of tenants, thousands of jobs per day).
- We own retries, leases, backoff and dead-lettering. Revisit if job volume, fan-out or
  long-running orchestration outgrows a single Postgres primary.
- Workflow and queue code sits behind small interfaces so an engine can replace it later.
