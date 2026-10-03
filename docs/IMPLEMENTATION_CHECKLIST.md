# Implementation and release checklist

Every stage and gate starts as **pending**. Change a status only after recording evidence for work actually completed. Keep recorded observations, derived measures, and hypothetical scenario inputs and outputs distinct.

## Ordered implementation stages

1. [x] **Establish project and instructions — VERIFIED**
   Establish project conventions, ownership, cross-platform workflow, and evidence rules. Evidence: reviewed repository instructions and task handoff format.

2. [x] **Audit data and lock the pilot — VERIFIED**
   Audit the acquired real source archive and its provenance, coverage, identifiers, timestamps, and licence terms. Lock the pilot corridor around Fairfield/Annerley, South Bank, and CBD, the study period, and the historical `as_of` received-data cutoff. Inputs received after that cutoff must not affect the replay. Evidence: source audit, provenance manifest, pilot decision, and cutoff rule.

3. [x] **Establish the development foundation — VERIFIED ON MAC; CROSS-PLATFORM CI PASSED**
   Create the approved, reproducible macOS and Windows development setup for the accepted stack. Evidence: clean setup notes and environment checks on supported systems.

4. [ ] **Collect and archive raw sources — IMPLEMENTED; COMPLETE MORNING WINDOWS PENDING**
   Acquire the approved bus and rail source snapshots, preserve originals outside Git, and record retrieval time and hashes. Inspection downloads are part of the approved source audit; do not request repeated permission for each source file. Evidence: source register, archive manifest, hashes, and integrity check.

5. [x] **Normalize and reconstruct service — VERIFIED**
   Validate and normalize records, preserve source timestamps and identifiers, and reconstruct service events with traceable provenance. Evidence: schema and quality report plus a reproducible transformation.

6. [x] **Implement CSA and independent OpenTripPlanner routing — VERIFIED AT DOCUMENTED SCOPE**
   Implement the approved connection-scan algorithm (CSA) and compare its routes independently with OpenTripPlanner (OTP). Lock pilot route parameters: maximum walk distance 600 m, walking speed 1.2 m/s, transfer slack 300 seconds, and at most three transfers. OTP means OpenTripPlanner throughout this project. Evidence: routing contract, fixtures, independent comparisons, and discrepancy review.

7. [x] **Replay recorded service — VERIFIED ON DEVELOPMENT AFTERNOON FRAMES**
   Replay recorded bus and rail service for the locked pilot using only data received on or before the recorded cutoff. Evidence: reproducible runs for the selected periods and input manifests.

8. [x] **Model disruptions — CORE VERIFIED**
   Add clearly hypothetical disruption scenarios and replacement-bus service constraints; keep their inputs visible and distinct from recorded operations. Evidence: reviewed scenario definitions and traceable scenario outputs.

9. [x] **Calculate impact metrics — VERIFIED ON FIXED 100-REQUEST DEVELOPMENT SET**
   Define and calculate rider-facing and service impact measures against the observed replay and scenario baseline. Evidence: metric definitions, independently checked examples, and documented limits. Service performance indicators that require separate calibration are outside this release.

10. [x] **Search for recovery plans — VERIFIED ON REAL DEVELOPMENT RECORDING**
    Implement the bounded search for feasible replacement-bus recovery under the approved capacity, access, availability, and routing constraints. Evidence: reproducible cases showing feasible and infeasible plans and their assumptions.

11. [ ] **Report robustness findings — DEVELOPMENT SENSITIVITY VERIFIED; MORNING EVALUATION PENDING**
    Assess how findings change across source gaps, timing assumptions, disruption choices, and recovery constraints. Evidence: documented sensitivity runs and limitations tied to recorded inputs.

12. [ ] **Build the product interface and package a static demo — LOCAL UI VERIFIED; PUBLIC MORNING DEMO PENDING**
    Build the replay/scenario interface and package a static, reproducible demo for review. Evidence: walkthrough tied to recorded morning bundles, clearly labeled observations and hypothetical scenarios, and setup instructions.

## Release gates

All gates below remain pending until their evidence is linked. Routing validation means CSA compared independently with OpenTripPlanner; uncalibrated service performance indicators are not release claims.

- [ ] **Five complete weekdays, 06:00–12:00 Brisbane local time — PENDING**: identify the exact weekdays and source snapshots; document completeness and every missing interval.
- [ ] **Three recorded morning bundles — PENDING**: provide three reproducible bundles with source/scenario provenance, manifests, and hashes.
- [ ] **Independent CSA/OpenTripPlanner verification and tests — PENDING**: record the independent route reference, parameters, comparison, test commands, and actual outcomes.
- [ ] **Performance — PENDING**: record the approved workload, measured environment, thresholds, and actual results.
- [ ] **Licences — PENDING**: document terms, attribution, and permission for all data included in a release or demo.
- [ ] **Secrets — PENDING**: inspect tracked files and release configuration for credentials, private data, and machine-specific paths.
- [ ] **CI — PENDING**: record a successful GitHub Actions run for the release candidate and its commit/run reference.
- [ ] **Static demo — PENDING**: provide a reproducible static package and walkthrough that labels recorded observations and hypothetical scenarios accurately.
- [ ] **Public release and verification — PENDING**: after the preceding gates pass, publish under the authorization already provided in the accepted plan; verify the repository and demo are publicly accessible.

## Evidence log

### 2026-10-02 development evidence

- Primary private checkout and explicit model profiles: `AGENTS.md`, `.codex/agents/`, `docs/tasks/SETUP-001.md`.
- Real GTFS, three realtime feeds, monthly OD and mapped walking-source audit: `docs/DATA_AUDIT.md`, `docs/SOURCES.md`, `configs/pilot.json`.
- Pipeline/operational verification: `docs/tasks/DATA-001.md`, `docs/INTEGRATION.md`; native Mac PostGIS/Redpanda health passed. A clean Docker API image built and returned healthy archive/PostGIS/Redpanda at port8001; temporary verification container was then stopped.
- Python verification at commit `fec68f7b18c8ffe95352f6f547f74ed6a28ccf11`: [GitHub Actions run36965117356](https://github.com/Suhail15/brisbane-transport-resilience-lab/actions/runs/36965117356), successful Linux/Windows/macOS matrix. This precedes frontend completion and is not final-release CI evidence.
- Max architecture acceptance: `docs/tasks/ARCH-001.md`; 40 engine tests passed, including 288 independent oracle queries. Separate real PostGIS integration test passed.
- Independent reference scope: `docs/REFERENCE_VALIDATION.md`; six distinct exact real transit paths, six explained access differences, zero unexplained cases. Raw exact agreement stays1/6 and6/7. Walking coverage remains incomplete.
- Final development workload: 100 sequential end-to-end journey HTTP queries on Apple M2 / 16 GB RAM, p95 0.06917s, median 0.04617s, maximum 0.09779s. ARCH-002 independently recomputed the p95. Recovery runtime is separate; this is not a final morning release benchmark.
- Frozen 100-request development comparisons use one archived afternoon snapshot and source-selected targets. Stop closure at budgets 0/2/4/8 yielded capped duration reductions 0/320/376/376 seconds across test queries, used 0/2/4/4 bus-hours and restored zero lost requests. Null cancellation/corridor cases and 0/300/600-second running-time sensitivity remain documented in `docs/FINDINGS.md`. ARCH-002 independently reconciled seven final runs.
- UI browser review confirmed 280 recorded positions and five source alerts for snapshot35f84816f6e208318ed8e49a. The map worker now loads and lossless geometry compression is 612 KB; the rebuilt private static preview now opens readable scenario/budget groups and reconciled four-hour results with the backend stopped.
- Publication request sent with explicit user authorization and verified in Sent on2026-10-02. Contact details remain in ignored local records. Translink approval is pending.
- Earlier local Python suite: 57 passed, with one optional live PostGIS check skipped; actual PostGIS was also checked separately. The final expanded suite is recorded below.
- Complete weekday morning windows: **0/5**. Three final public morning bundles: **0/3**. Future evidence must be collected; afternoon recordings cannot satisfy these gates.

### 2026-10-03 private milestone checks

- Expanded local Python suite: 75 passed including the live PostGIS checks; eight frontend checks passed. The expanded suite includes final export/verifier corruption and exact-file-set regressions; ARCH-004 records independent acceptance.
- Root independently verified the reviewed reproduction manifest digest, all 65 file hashes and the current frozen analytical engine/adapter identities. ARCH-004 records the separate recomputation and proxy review.
- Bounded scan of 125 proposed nonignored files found no known credential-pattern hits, files over 5 MB, raw/runtime archive paths or the account email address. The exact scan scope and file hashes remain private.
- Persistent Mac collector is running; planned first eligible mornings remain 5–9 October, 06:00–12:00 Brisbane time, subject to complete actual coverage.
