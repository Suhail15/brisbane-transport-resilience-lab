# ARCH-008

- Title: independent reconciliation of the frozen morning evaluation
- Status: implementation and corruption tests complete; coordinator final 54-run review pending
- Owner: ARCH-008 independent analytical review agent
- Reviewer: root coordinator

## Model and reasoning

- Requested model: GPT-6.1 Sol.
- Requested reasoning: max.
- Actual configuration exposed to this agent: a full-history child of the parent session, inheriting its configuration. Serving model identity and reasoning effort are not independently introspectable. No additional agent or model override was created.

## Approved specification and decisions

- Coordinator dispatch authorizes this independent review under Decision 27, `docs/tasks/ARCH-007.md`, `docs/CONTRACTS.md`, `docs/METHODOLOGY.md` and the already frozen `configs/morning-evaluation.v1.json`.
- Preserve evaluation dates 19/20/21 October 2026, cutoff 07:30:05 Australia/Brisbane, twenty fixed OD pairs expanded at offsets 0/900/1800/2700/3600 to 100 equally weighted requests, four source-selected scenarios, budgets 0/2/4/8, and maximum 128 swap evaluations.
- Stop-closure budget two at stress 0/300/600 shares the nominal candidate list. Its zero-stress run is already a nominal cell, giving exactly 54 distinct prescribed combinations across the three dates.
- Do not generate replacement targets, rewrite source artifacts, modify the engine or rerun expensive recovery searches. Actual jobs, OTP, performance and offline reproduction remain with the coordinator.

## Required inputs and dependencies

- Immutable normalized full snapshots, canonical run inputs/metadata, source receipts/payloads, and completed full runs under `data/processed/{snapshots,derived-inputs,run-inputs,run-results}`.
- Existing `data/processed/morning-evaluation-v1/{decision-manifest.json,plan.json,targets,results,summary.json}` and the fixed journey specification.
- Existing `resilience.pipeline.integrity.verify_run` supplies hash, receipt, source availability and matching historical code checks. The verifier independently calculates metrics and transformations from plain JSON and does not call routing, recovery, scenario or metric helpers.
- Python 3.11/3.12 and the repository dependencies. Tests use only synthetic local archives and hand-built route outputs; they do not execute recovery or contact OTP.

## Files owned

- `scripts/verify_morning_results.py`
- `tests/integration/test_morning_result_verifier.py`
- `docs/tasks/ARCH-008.md`

## Expected output

- CLI: `.venv/bin/python scripts/verify_morning_results.py --output data/processed/morning-evaluation-v1/independent-verification.json`.
- `--summary` defaults to the existing morning summary path. Optional `--data-dir` and `--config` support isolated archives/tests. `--allow-partial` permits a clean partial invocation to exit successfully while retaining `passed: false` and `status: partial`; a final pass always requires all 54 fixed combinations.
- The report binds the exact summary/config/target hashes, verifier hash, and each checked immutable completed-result hash, and lists every missing combination or error.
- Checks cover frozen dates/cutoffs/targets, all 100 ordered equal-weight requests, exact summary/local-final/archive agreement, shared ordered scenario/candidate identities, baseline/disrupted route-array equality across compared budgets, and unchanged nominal candidates across sensitivity levels.
- Independent metrics include every configured request: reachable within 3,600 seconds, lost/restored sets and null restored fraction, all-request 5,400-second capped totals including unreachable journeys, and planned missed changes/affected-request counts. Missed-change details are recalculated from baseline legs and independently transformed effective source events, excluding cancelled services and unavailable boarding/alighting events.
- Nonzero sensitivity snapshots are independently checked against the documented integer proportional transform, including nominal provenance, unchanged rail/walking/metadata, scaled source bus events and relief-pattern offsets.
- Resource checks enforce at most twelve supplied candidates, two bus-hours and 7,200 seconds per candidate, activation at least T+600, at most four selected buses within budget, complete paired cycles with both 300-second turns, source bus topology, selected duty identifiers/end/cycle counts, and closure feasibility. Selected/no-action objectives must reconcile with independently computed metrics; the selected objective cannot be worse than the reported simple-policy comparator.

## Acceptance checks

- PASS on 22 October 2026, macOS: `.venv/bin/python -m pytest tests/integration/test_morning_result_verifier.py -q` → **22 passed in 10.12s**.
- The synthetic full matrix verifies 54/54 while retaining null benefits. Other tests reject coherent archive/summary metric corruption, comparison objective corruption, fixed-request reordering with recomputed hashes, candidate drift across budgets and stress, equal-metric changed route arrays, local-final/archive disagreement, a future receipt, duplicate run IDs, an unapproved date, invalid candidate costs/activation/duration, corrupted selected cycles and over-budget resources. Hand-calculated boundary/miss cases check inclusive 3,600 seconds, late/unreachable 5,400 caps, baseline-unreachable requests in totals, actual transfer walks, exact connection feasibility equality and cancelled/unavailable service exclusion.
- PASS: CLI help exposes `--summary`, required `--output`, `--data-dir`, `--config` and `--allow-partial`.
- PASS: `git diff --check -- scripts/verify_morning_results.py tests/integration/test_morning_result_verifier.py` returned exit 0. These are new files, so the coordinator should include them in final staged/full checks.
- PARTIAL RECORDED CHECK: `.venv/bin/python scripts/verify_morning_results.py --allow-partial --output data/processed/morning-evaluation-v1/independent-verification.partial.json` → **23 of 54 completed indexed combinations verified; zero errors; 31 pending; `status: partial`, `passed: false`**. The report records the precise reviewed summary hash. Jobs continued after this snapshot; this count is not a final evaluation claim.
- PENDING: coordinator runs the strict command above after every job has completed and records the actual 54/54 result. No final morning acceptance is claimed here.

## Escalation issues

- The driver rewrites a summary loaded once at startup, so multiple simultaneous filtered drivers would lose one another's summary rows. Raised to root; root confirmed one sequential driver and one API worker. No orchestration edit was needed. The verifier checks summary/local-final/archive consistency and requires all cells at final review.
- An initial verifier check compared equivalent UTC strings (`Z` versus `+00:00`) literally. Corrected the comparison to aware datetime equality before subsequent real validation. No source or result was rewritten. No repeated unresolved failure occurred.
- A source-only extension of the separate OTP validation set can improve coverage when frozen before its own comparisons, but must be labelled as added after the original checks, retain all original denominators/disagreements, and never offset unexplained differences with added exact cases. The inspected 20 October raw report remains 4/7 exact. Its -16-second case shares the same rail trip/times and differs only in final platform walking interpretation; the other two differences use different access/transit paths and need concrete explanation or narrowly scoped acceptance. OTP evidence remains coordinator-owned.
- Limits: stored route arrays support independent arithmetic and source-event reconciliation, not a proof that every route is globally earliest or that bounded recovery is globally optimal. The simple-policy comparator has no separate route arrays in the schema, so its duration is checked only as a reported comparison objective. Recorded-before-results chronology relies on the coordinator's frozen protocol/artifact evidence; mutable filesystem timestamps are not presented as independent proof. Collection completeness, walking access quality, OTP, performance, public permissions and offline recovery reproduction are separate checks.
- Next owner: root coordinator completes the actual jobs, executes strict final verification, reviews the reported scope/limits, and incorporates the evidence into the release assessment. No commit was created by this task.
