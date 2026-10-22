# PACK-001: public reproduction candidate eligibility guard

- **Task ID:** PACK-001
- **Status:** implementation complete; coordinator review pending
- **Owner:** bounded implementation

## Model and reasoning

Requested model and effort: GPT-6 Luna Max. Serving identity is not independently
introspectable. The implementation stayed within the assigned reproduction guard,
focused integration tests, and task handoff.

## Approved specification and decisions

Implemented the public-candidate guard approved under ARCH-003 and Decision 28.
Candidate preparation requires all three existing preparation gates, exactly three
selected public service dates, and a non-empty unique explicit run list. Every run is
verified before any output is written. Each run must be a completed normalized run
whose snapshot falls on a selected weekday from 06:00 through 11:59:59 Brisbane
time. The requested pack must represent all three dates. Every referenced realtime
receipt must be on that snapshot date in the same morning window and explicitly have
`development_capture: false`. Static GTFS and OSM receipts continue through the
existing cutoff and integrity checks in `verify_run` without a morning-time restriction.

Candidate preparation remains local and does not authorize publication. The private
pack path and the root-owned `on_progress` callback remain intact. No release gate,
source timestamp, receipt, engine, or recomputation behavior was weakened or edited.

## Required inputs and dependencies

- Approved ARCH-003 local candidate preparation rules and Decision 28 deployment boundary.
- Existing immutable run, snapshot, and source-receipt verification in
  `services/resilience/pipeline/integrity.py`.
- Synthetic in-memory archive fixtures only; the running private reproduction and its data were not accessed.

## Files owned

- `services/resilience/pipeline/reproduction.py`
- `tests/integration/test_public_reproduction.py`
- `docs/tasks/PACK-001.md`

## Expected output

The public candidate packer preflights the full requested run set and its realtime
provenance before writing, reuses each verified run/input/snapshot tuple during pack
creation, rejects any incomplete eligibility set without silently dropping runs, and
records the existing candidate-only manifest flags.

## Acceptance checks

- [x] Synthetic three-date candidate is accepted with all requested run IDs and the
  `private_only: false` / `candidate_preparation_only: true` flags preserved.
- [x] Pending preparation gate, empty, duplicate, and unknown IDs, missing selected date,
  non-selected date, noon capture, weekend capture, development realtime receipt,
  mismatched realtime receipt date, and legacy run are rejected before output appears.
- [x] Static receipt outside the morning window remains acceptable when its existing
  verification/cutoff path passes in the valid synthetic candidate.
- [x] Private pack can still contain a non-morning snapshot and retains its private
  manifest flags without calling the public gate.
- [x] `.venv/bin/python -m pytest tests/integration/test_public_reproduction.py -q` — 13 passed.
- [x] Scoped `git diff --check` for the three owned paths — passed.

## Escalation issues

None. No real archive data, private reproduction process, services, network, or
publication path was used.
