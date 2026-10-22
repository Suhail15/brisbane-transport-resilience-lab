# ARCH-007

- Title: final recorded-morning evaluation and private release preparation
- Status: specification approved; execution pending
- Owner: root coordinator
- Task ID: ARCH-007

## Model and reasoning

Coordinator role: GPT-6.1 Sol, max reasoning as requested by the project. Integration
dispatch explicitly requests GPT-6.1 Sol medium; bounded implementation explicitly
requests GPT-6 Luna max. Serving identity is not independently introspectable.

## Approved specification and decisions

Decision 27 and `configs/morning-evaluation.v1.json` freeze the final evaluation.
The original engine, contracts, objective, source cutoffs, primary equal weights,
walking rules and resource constraints remain in force. Root approves these interfaces
before dependent implementation. No real source record or completed run is rewritten.

## Required inputs and dependencies

Six complete 06:00–12:00 weekday windows have been independently counted on 22 October:
9, 13, 19, 20, 21 and 22 October; 20,160 valid non-development feed captures. The
unchanged maximum gaps are 35/35/65 seconds including edges. Source freshness, joining
and pedestrian coverage remain distinct from collection completeness.

## Files owned

- Root: shared contracts/decisions, evaluation config, findings/checklist/release docs,
  release evidence, current task, reproduction and independent validation scripts.
- INT-008: `services/resilience/pipeline/morning.py`, `scripts/run_mornings.py`,
  `tests/integration/test_morning_evaluation.py`, `docs/tasks/INT-008.md`.
- UI-002: `services/resilience/pipeline/snapshots.py`,
  `services/resilience/pipeline/bundle.py`,
  `frontend/src/App.jsx`, `tests/integration/test_morning_labels.py`,
  `docs/tasks/UI-002.md`.

## Expected output

Three recorded morning replay sets and decision snapshots; immutable target/request
manifests; all four disruptions at 0/2/4/8 bus-hours on each final morning; stop-closure
budget-two running-time sensitivity at 0/300/600 seconds; independent reconciliation,
morning findings, reproducible private demo and exact publication blockers.

## Acceptance checks

- Dates and source-only targets fixed before policy outcomes; same 100 equal-weight
  requests within a date and same 20 OD pairs across dates.
- Final dates 19/20/21 October, fixed cutoff 07:30:05 Brisbane; 9/13 are development,
  22 October is reserve. Source availability cutoffs cannot be advanced retrospectively.
- Recorded replay samples every 15 minutes from 06:00:05 to 11:45:05; clearly labelled
  sampling, no invented position interpolation. Decision frame is one of those samples.
- Full paths preserved; source gaps/fallbacks and incomplete walking coverage visible.
- Nominal search keeps at most 12 candidates, 128 bounded swap evaluations and the
  frozen lexicographic objective. Comparisons include no action and the simple policy.
- One paired sensitivity uses the same nominal candidate identities; no post-result
  selection of an easier scenario. Null or infeasible outcomes remain in findings.
- Exactly three dates in the final private morning bundle. Public gating is retained;
  no publisher permission is inferred from an unanswered request or GitHub CI email.
  The user supplied a written Translink reply on 22 October covering portfolio GTFS
  use; retain its actual provenance and apply its required attribution/branding/
  simulation labels. No independently checked sender or email timestamp is claimed.
- Source immutability, independent OTP checks, end-to-end performance and offline
  reproduction must be verified at their actual documented scopes.

## Escalation issues

Stop after two unsuccessful attempts at one issue. Escalate missing target services,
ambiguous source interpretation, changes to analytical inputs/interfaces, failed
algorithm assertions and any publication limitation. Continue independent private
work while the written source approval is pending. Do not weaken the release gate.
