# ARCH-001

- Title: routing, scenarios and recovery core
- Status: implementation in progress; version 1 contracts frozen
- Owner: architecture agent
- Reviewer: root integrator

## Task ID

ARCH-001

## Model and reasoning

GPT-6.1 Sol, reasoning max (explicitly dispatched by the integrator).

## Objective

Freeze shared interfaces and implement auditable routing, scenario evaluation and
bounded feasible recovery with independent fixture calculations.

## Approved specification and decisions

`docs/CONTRACTS.md`, `docs/DECISIONS.md` and `services/resilience/contracts.py` are
version 1. They define receipt-time snapshots, full GTFS trips, service-day seconds,
actual OSM footpaths, four boardings, scenario ordering, primary equal-weight metrics,
and paired-pattern two-hour recovery duties with explicit search limits.

## Required inputs and dependencies

Python 3.11+, Pydantic 2, pytest. Pipeline supplies validated full-trip snapshots,
OSM paths and paired existing bus patterns. Integrator supplies source collection,
source licensing/release gates, API adapters and real-source OTP validation.

## Files owned

- `docs/CONTRACTS.md`, `docs/DECISIONS.md`, `docs/METHODOLOGY.md`
- `services/resilience/contracts.py`, `services/resilience/engine/`
- `tests/engine/`, `docs/tasks/ARCH-001.md`

## Expected output

Shared models, pure engine exports matching the frozen signatures, route audit legs,
scenario impacts, explicit metrics, feasible recovery comparison and independent tests.

## Acceptance checks

Receipt-time rejection; calendar/time adapter contract; same-vehicle continuation;
minimum-transfer/walking arithmetic; earliest-arrival and tie rules; four scenario
types and future-only delay propagation; unreachable denominator/capped duration;
complete duties, activation, budget and closure feasibility; bounded/exhaustive small
case comparison. Full verification results are added at handoff.

## Escalation issues

Escalate a repeated failure after two attempts or an incompatible interface change
to the integrator before adapting another owner's files. Dataset absence or five-day
collection delay cannot be resolved with synthetic public-demo evidence.
