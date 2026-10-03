# ARCH-001

- Title: routing, scenarios and recovery core
- Status: owned implementation and bounded reference checks complete; integration/release gates remain
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
version 1.1. Root approved frozen receipt-time snapshots, full GTFS trips, service-day
seconds, actual OSM footpaths/30m association diagnostics, four boardings, scenario
ordering, primary equal-weight metrics and paired-pattern two-hour recovery duties.
Compatible extensions add affected-corridor candidate selection and metadata-only
progress/cancellation callbacks. Engine version is `csa-resilience-1.1.0`.

Root also approved compact display/choices DTOs, snapshot-specific GTFS network
geometry, source-active pilot OD selection with inactive-platform disclosure, and
bounded reference validation with source-specific access explanations. See
`docs/REFERENCE_VALIDATION.md` for actual paths and the unchanged raw disagreements.

The next integration packet is approved: immutable `RunMetadata`, a persisted
source-selected 20-pair/100-request experiment, 0/300/600s hypothetical bus running-time
sensitivity using derived copies and fixed nominal candidate ids, and reviewed
reproduction assets after release gates. `docs/CONTRACTS.md` specifies hash rules,
stress mapping, missing-stop handling and ODbL derivative-data availability.

## Required inputs and dependencies

Python 3.11+, Pydantic 2, pytest. Pipeline supplies validated full-trip snapshots,
OSM paths and paired existing bus patterns. Root owns source collection, licensing/
release gates and operational infrastructure. Integration owns API/pipeline adapters,
metadata persistence, stress preprocessing, fixed experiment and reproduction wiring.
Luna owns the bounded frontend implementation following `docs/API.md`.

Actual schedule-only reference snapshot `94005388692bbc7af14487de` and its retained
quality audit use source-received GTFS/OSM records. Official OpenTripPlanner 2.10.0
requires separate build/save and load/serve processes here. Source inputs and local
reports remain outside Git; they do not establish morning collection completeness.

## Files owned

- `docs/CONTRACTS.md`, `docs/DECISIONS.md`, `docs/METHODOLOGY.md`
- `docs/REFERENCE_VALIDATION.md`, `docs/tasks/ARCH-001.md`
- `services/resilience/contracts.py`
- `services/resilience/engine/__init__.py`, `routing.py`, `scenarios.py`,
  `evaluation.py`, `recovery.py`, `candidates.py` within that same directory
- `tests/engine/__init__.py`, `fixtures.py`, `oracle.py`, `test_routing.py`,
  `test_scenarios_metrics.py`, `test_recovery.py`, `test_candidates.py`
- `scripts/check_otp.py` (root explicitly extended ownership for critical reference analysis)

No scaffold, collector, API, frontend or another owner's pipeline files were edited.

## Expected output

Delivered shared immutable models and engine exports, auditable route legs, four
scenario transformations, explicit all-request metrics, feasible bounded/exhaustive
recovery comparison, source-relevant candidate ranking and independent tests.
Delivered compatible observer/cancellation hooks and run version/assumption contracts.
Delivered bounded real-source reference evidence and approved next integration brief.

## Acceptance checks

- **Passed:** `PYTHONPATH=services .venv/bin/python -m pytest tests/engine -q`,
  40 tests, 0.19s, Python 3.11/Pydantic 2, after final metadata/stress contract additions.
- Independent heap-search ride-edge oracle imports contracts only and matches 288
  queries across 24 seeded networks. Separate fixtures exercise later/fewer-boarding
  Pareto labels, immutable paths, long same-vehicle continuation, walking/transfer
  arithmetic without first-boarding slack, no walk-chain escape, and >24h times.
- Fixtures check four scenario types/half-open windows/future propagated delays,
  unreachable all-request capped duration, timing misses versus unavailable service,
  activation/terminal turns/complete duties/budgets/closure rejection, hand-calculated
  small recovery optimum, topology/relevance selection and progress/cancel behavior.
- **Actual reference:** fresh original six and expanded seven real schedule queries
  reproduced raw exact arrival counts 1/6 and 6/7. Both raw `passed` values remain
  false. Reviewed report finds 6 distinct exact transit paths, 6 source-specific
  access/path explanations and 0 unexplained cases; `passed=true` only for the
  explicitly bounded schedule-core/access-review scope. No arbitrary tolerance pass.
- Final report: `data/processed/otp-reviewed-validation.json`; source/path table:
  `docs/REFERENCE_VALIDATION.md`. Reports bind exact snapshot/checker/engine hashes
  and reject stale input/code/checker versions or GraphQL errors during review.
- Final engine code SHA-256:
  `bcbe5612aa816b76800f3e6516f60a140f639ee87f8670443a7b4f7f99e70240`.
- Walking coverage remains incomplete. The reference snapshot preserves an earlier
  walking derivation; transit-only checks do not depend on it. Schedule comparisons
  do not validate GTFS-RT predictions or measured arrivals. Calendar expansion,
  source freshness and collector completeness remain adapter acceptance checks.
- **Pending other owners:** API immutable metadata/hash capture and legacy export
  rejection; approved stress/fixed experiments/reproduction wiring; broader latency/
  recovery benchmark; compact UI/static checks; future real morning recordings,
  source attribution/licensing/approval evidence and all release gates. Root verified
  the explicitly authorized publication contact message in Sent; approval remains pending.

## Escalation issues

Two repeated atomic documentation patch-context failures were escalated; root
authorized exact-context repairs, which completed without changing analytical rules.
One later batch patch failed atomically because a wrapped line did not match; the
current line was read and the exact-context patch succeeded.

Integration escalated repeated OTP real query `Index 1127 out of bounds for length 0`
errors. Official source inspection identified construction/mapping order; root's
separate saved-graph load process restored actual queries. Source-specific path audits
then resolved the bounded comparison discrepancies; no street model was widened.

Next owner is integration (GPT-6.1 Sol, medium), dispatched by root after this handoff.
Future morning data and unfulfilled licensing/approval gates cannot be satisfied with
synthetic recordings or development afternoon evidence. Public release remains gated.
