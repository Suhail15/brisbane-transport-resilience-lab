# ARCH-014 / DATA-002

- Title: source-fixed walking-catchment bus coverage for the new study
- Status: implementation, focused tests and prepared-development source checks complete; root owns execution/release
- Owner: ARCH-014 source-network adapter agent
- Reviewer: root coordinator

## Model and reasoning

- Dispatch model `gpt-6.1-sol`, reasoning `max`, original `fork_turns=none`, as confirmed by the coordinator. No subagents.

## Approved specification and decisions

- Root approved the union of all bus line short names active on either 9/13 October development service day and touching actual existing walking-link catchments of the eight fixed study platforms. Include the unchanged base pilot and preserve complete source trips. Expected source-derived bounds are 29 bus stops, 103 development bus short names, 84 added names and 156 total pilot names.
- This is a pre-confirmation coverage correction. Preserve the original v1.0.0 54 results/72 frames and the initial separate-study development/profiling/parity artifacts. No 22 October recovery outcome may inform network selection.
- Root authorized optional `pilot_path` plumbing in `snapshots.py`, actual pilot bytes in its method digest, and a separate nondefault pilot-aware filtered stop-time cache in `schedule.py`. Preserve default behavior and original stored artifacts. Numerical engine and walking rules remain unchanged.
- Decision 31 records the approved source correction; `configs/corridor-impact.v2.json` is the separate analytical protocol. This task does not authorize confirmation execution or publication.

## Required inputs and dependencies

- Frozen development normalized snapshots for 9/13 October, their receipt-bounded original GTFS/OSM references, and `configs/pilot.json`.
- Source audit found all 30 morning Roma catchment bus routes absent from the old network on both dates. Forty of 120 previously modeled losses have direct omitted scheduled bus plus existing-walk alternatives within 60 minutes on each development date. This is a schedule counterexample, without applying real-time predictions or claiming observed operations.
- Root owns the new analytical config; integration owns `case_study.py`, CLI, immutable experiment runs and source/code freeze. Coordinate before producer edits.

## Files owned

- `services/resilience/pipeline/case_network.py`
- `services/resilience/pipeline/snapshots.py` — optional pilot selection and actual-pilot hash only
- `services/resilience/pipeline/schedule.py` — nondefault pilot-aware filtered cache only
- `configs/station-access-network.v1.json`
- `tests/test_case_network.py`
- `docs/tasks/ARCH-014.md`

## Expected output

- Executable source-only derivation and frozen small network config binding all selected bus stops/line names, real directed walking-link hashes, development snapshot/receipt/GTFS/OSM hashes, calendar-active route witnesses and resource bounds.
- `derive_network(archive, development_snapshots, base_pilot_path)` reads unfiltered development GTFS; `write_network_config(...)` freezes the spec; `materialize_pilot(network_config_path, output_path, base_pilot_path)` writes an immutable derived pilot and returns its path/hash for the optional builder input.
- `snapshot_coverage(archive, snapshot, pilot_path, cancelled_trip_ids=())` reads raw GTFS independently of filtered caches and verifies every selected dated trip's complete ordered stop/route/mode/connection-ID topology. Declared cancellation exclusions come from recorded builder diagnostics; the adapter does not certify independent real-time cancellation interpretation or measured arrival times.
- No route frequency/time/outcome threshold, radius-built pedestrian edge, partial trip, date-specific platform substitution or recursive network expansion. New full source routes can reveal additional real walking paths under existing rules.
- Default/custom cache separation, complete trip retention, source-witness checks and actual-pilot method-digest tests. Integration then re-normalizes development snapshots and confirms real M2/61/222/333 movements; root approves v2 freeze before held-out policy work.

## Acceptance checks

- PASS (read-only source audit): 9 October has 103 active bus names over all eight catchments versus 44 Roma-only; 13 October 96 versus 43. The union has 103 bus names. Morning-only diagnostic counts are 88/81 over all eight versus 30/30 Roma; these counts do not filter selection.
- PASS (resource projection): the final frozen union retains 211,851 adjacent movements over 8,457 full trips on 9 October and 210,759/8,108 on 13 October. Original base counts were 59,686/2,141 and 60,375/1,875 respectively. The earlier 13 October own-date-only bound, 206,686/7,952, was superseded by the approved union across both development dates.
- PASS (preservation boundary): the two approved normalizer files are outside the 530-file original preservation baseline. Original files/results and producer files have not been edited by this task.
- PASS (frozen spec): `configs/station-access-network.v1.json` exact SHA-256 `c26aebd89ac143cf8e13e3171d6fcfa940873d54c212fa2b83b0b18e8ffc8f1a`; 29 real-link bus stops, 103 development-active bus names, 84 additions and 156 total route names. It records source receipt/snapshot/OSM hashes, directed walking-link hashes, source route witnesses and final resource counts.
- PASS (focused tests): `tests/test_case_network.py` → **8 passed in 0.85s**. Default/custom cache separation, full stop-time rows, exact custom-pilot bytes in snapshot identity, repeat default identity, calendar exceptions, either-direction real-link discovery, immutable base-bound pilot/config, raw topology, clipping and cancellation accounting are covered.
- PASS (combined suite): source tests plus `tests/integration/test_case_study_verifier.py` → **41 passed in 17.71s**. The verifier imports no producer or source-adapter calculation helper; it separately parses raw CSV and fresh recorded cancellation entities.
- PASS (actual prepared development inputs): `data/runtime/impact-study-2026-10-23/v2-independent-source-review.json` reconciles all 8,457/8,108 trips and 211,851/210,759 adjacent connections against unfiltered GTFS, with no recorded cancellations. M2/61/222/333 trip counts are 374/174/166/178 on 9 October and 366/169/166/178 on 13 October. Every old walking link is preserved identically: 4,138/4,050 links.
- PASS (format/scope): `git diff --check` returned exit 0 for owned paths. No confirmation/replication policy calculation was executed by this task. Implementation is ready for root's commit/CI checkpoint; no active source edits remain.
- Root owns final review/release. The arithmetic checker is independent of producer metrics; this task's author also owns the source adapter, so its derivation must not be described as an independent review by another author.

## Escalation issues

- Source coverage is a material validity issue: the old 120-loss rail scenario must not be presented as realistic impact while known bus alternatives are omitted. Fix source coverage before confirmation, then retain any null recovery outcome.
- Current network still has bounded OSM coverage, unresolved platform access and uncalibrated transfers. No available fleet, capacity or real-world incident effect is established.
- Root decides the final v2 config/source freeze and obtains separate source-adapter review. No repeated implementation failure has occurred.
