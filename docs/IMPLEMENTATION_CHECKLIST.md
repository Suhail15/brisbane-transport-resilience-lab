# Implementation and release checklist

Every stage and gate starts as **pending**. Change a status only after recording evidence for work actually completed. Keep recorded observations, derived measures, and hypothetical scenario inputs and outputs distinct.

## Ordered implementation stages

1. [x] **Establish project and instructions — VERIFIED**
   Establish project conventions, ownership, cross-platform workflow, and evidence rules. Evidence: reviewed repository instructions and task handoff format.

2. [x] **Audit data and lock the pilot — VERIFIED**
   Audit the acquired real source archive and its provenance, coverage, identifiers, timestamps, and licence terms. Lock the pilot corridor around Fairfield/Annerley, South Bank, and CBD, the study period, and the historical `as_of` received-data cutoff. Inputs received after that cutoff must not affect the replay. Evidence: source audit, provenance manifest, pilot decision, and cutoff rule.

3. [x] **Establish the development foundation — VERIFIED ON MAC; CROSS-PLATFORM CI PASSED**
   Create the approved, reproducible macOS and Windows development setup for the accepted stack. Evidence: clean setup notes and environment checks on supported systems.

4. [x] **Collect and archive raw sources — SIX COMPLETE MORNING WINDOWS VERIFIED**
   Acquire the approved bus and rail source snapshots, preserve originals outside Git, and record retrieval time and hashes. Inspection downloads are part of the approved source audit; do not request repeated permission for each source file. Evidence: source register, archive manifest, hashes, and integrity check.

5. [x] **Normalize and reconstruct service — VERIFIED**
   Validate and normalize records, preserve source timestamps and identifiers, and reconstruct service events with traceable provenance. Evidence: schema and quality report plus a reproducible transformation.

6. [x] **Implement CSA and independent OpenTripPlanner routing — VERIFIED AT DOCUMENTED SCOPE**
   Implement the approved connection-scan algorithm (CSA) and compare its routes independently with OpenTripPlanner (OTP). Lock pilot route parameters: maximum walk distance 600 m, walking speed 1.2 m/s, transfer slack 300 seconds, and at most three transfers. OTP means OpenTripPlanner throughout this project. Evidence: routing contract, fixtures, independent comparisons, and discrepancy review.

7. [x] **Replay recorded service — 72 SAMPLED FRAMES ON THREE FINAL MORNINGS VERIFIED**
   Replay recorded bus and rail service for the locked pilot using only data received on or before the recorded cutoff. Evidence: reproducible runs for the selected periods and input manifests.

8. [x] **Model disruptions — CORE VERIFIED**
   Add clearly hypothetical disruption scenarios and replacement-bus service constraints; keep their inputs visible and distinct from recorded operations. Evidence: reviewed scenario definitions and traceable scenario outputs.

9. [x] **Calculate impact metrics — 54 FINAL CASES INDEPENDENTLY RECONCILED**
   Define and calculate rider-facing and service impact measures against the observed replay and scenario baseline. Evidence: metric definitions, independently checked examples, and documented limits. Service performance indicators that require separate calibration are outside this release.

10. [x] **Search for recovery plans — 54 FINAL CASES EXACTLY REPRODUCED**
    Implement the bounded search for feasible replacement-bus recovery under the approved capacity, access, availability, and routing constraints. Evidence: reproducible cases showing feasible and infeasible plans and their assumptions.

11. [x] **Report robustness findings — FINAL MORNING MATRIX AND PAIRED SENSITIVITY VERIFIED**
    Assess how findings change across source gaps, timing assumptions, disruption choices, and recovery constraints. Evidence: documented sensitivity runs and limitations tied to recorded inputs.

12. [ ] **Build the product interface and package a static demo — PRIVATE MORNING PACKAGE VERIFIED; FINAL PUBLIC PACKAGE PENDING**
    Build the replay/scenario interface and package a static, reproducible demo for review. Evidence: walkthrough tied to recorded morning bundles, clearly labeled observations and hypothetical scenarios, and setup instructions.

## Release gates

All gates below remain pending until their evidence is linked. Routing validation means CSA compared independently with OpenTripPlanner; uncalibrated service performance indicators are not release claims.

- [x] **Five complete weekdays, 06:00–12:00 Brisbane — VERIFIED**: six dates October 9/13/19/20/21/22; 20,160 valid non-development captures, unchanged 35/35/65-second edge-inclusive limits. `docs/tasks/ARCH-007.md` and `data/processed/morning-evaluation-v1/coverage-at-preparation.json` record the audit.
- [x] **Three recorded morning replay sets — VERIFIED PRIVATELY**: fixed October 19/20/21, 72 sampled frames and 54 completed cases; exact public package remains under the static-demo gate. `frames.json`, frozen targets and final report under `data/processed/morning-evaluation-v1/`.
- [x] **Independent CSA/OpenTripPlanner verification and analytical tests — VERIFIED AT DOCUMENTED SCOPE**: 54/54 independent primary-run reconciliation; ARCH-008's 22 synthetic corruption/boundary checks passed. Morning OTP retains raw 4/7 core and 1/6 walking (the latter an absent-origin null), four original exact transit paths plus two post-initial diagnostics, 53 checked source movements, twelve walk paths and zero unexplained cases at the bounded review scope. See `REFERENCE_VALIDATION.md`, ARCH-008/009 and `independent-verification.json`. Release-candidate CI is a separate pending gate.
- [x] **Performance and offline reproduction — VERIFIED AT MEASURED SCOPE**: 300 journey HTTP calls, worst-date p95 0.17285 s on Apple M2/16 GB; October 20/21 clients overlapped. Offline 225-file pack reproduced 54/54 exactly in 508.35 s. These are separate journey-query and total-reproduction scopes, not original recovery queue timings. Evidence: `data/runtime/release-2026-10-22/journey-performance-summary.json` and `reproduction-report.json`.
- [ ] **Licences — FINAL PACKAGE BINDING PENDING**: Translink public terms and the user-supplied October 22 written reply reviewed, with required independent branding/simulation labels and exact attribution. Original sender headers/timestamp were not independently inspected. OSM remains separately ODbL. Root must bind the actual released contents/licence review to the final artifact. See `SOURCES.md`.
- [ ] **Secrets — FINAL CANDIDATE REVIEW PENDING**: inspect exact tracked/released bytes and configuration for credentials, private data and machine-specific paths; historical scans do not certify the final candidate.
- [ ] **CI — RELEASE CANDIDATE PENDING**: require successful GitHub Actions for the actual release revision and its commit/run reference.
- [ ] **Static demo — FINAL PUBLIC PACKAGE/WALKTHROUGH PENDING**: private three-morning package and filtered UI are prepared; root must bind the final dist (including HTML/assets), verify the actual walkthrough and confirm the source/candidate/public flags. The compact data manifest alone is not a complete-site manifest.
- [ ] **Public release and verification — PENDING**: after preceding gates pass, publish under the accepted authorization and verify actual public repository/demo access. Planned demo: https://Suhail15.github.io/brisbane-transport-resilience-lab/ . No live deployment success is claimed here.

## Evidence log

### 2026-10-02 development evidence

- Primary private checkout and explicit model profiles: `AGENTS.md`, `.codex/agents/`, `docs/tasks/SETUP-001.md`.
- Real GTFS, three realtime feeds, monthly OD and mapped walking-source audit: `docs/DATA_AUDIT.md`, `docs/SOURCES.md`, `configs/pilot.json`.
- Pipeline/operational verification: `docs/tasks/DATA-001.md`, `docs/INTEGRATION.md`; native Mac PostGIS/Redpanda health passed. A clean Docker API image built and returned healthy archive/PostGIS/Redpanda at port8001; temporary verification container was then stopped.
- Python verification at commit `fec68f7b18c8ffe95352f6f547f74ed6a28ccf11`: [GitHub Actions run36965117356](https://github.com/Suhail15/brisbane-transport-resilience-lab/actions/runs/36965117356), successful Linux/Windows/macOS matrix. This precedes frontend completion and is not final-release CI evidence.
- Max architecture acceptance: `docs/tasks/ARCH-001.md`; 40 engine tests passed, including 288 independent oracle queries. Separate real PostGIS integration test passed.
- Independent reference scope: `docs/REFERENCE_VALIDATION.md`; six distinct exact real transit paths, six explained access differences, zero unexplained cases. Raw exact agreement stays1/6 and6/7. Walking coverage remains incomplete.
- Final development workload: 100 sequential end-to-end journey HTTP queries on Apple M2 / 16 GB RAM, p95 0.06917s, median 0.04617s, maximum 0.09779s. ARCH-002 independently recomputed the p95. Recovery runtime is separate; this is not a final morning release benchmark.
- Frozen 100-request development comparisons use one archived afternoon snapshot and source-selected targets. Stop closure at budgets 0/2/4/8 yielded capped duration reductions 0/320/376/376 seconds across test queries, used 0/2/4/4 bus-hours and restored zero lost requests. Null cancellation/corridor cases and 0/300/600-second running-time sensitivity remain documented in `docs/DEVELOPMENT_FINDINGS.md`. ARCH-002 independently reconciled seven final runs.
- UI browser review confirmed 280 recorded positions and five source alerts for snapshot35f84816f6e208318ed8e49a. The map worker now loads and lossless geometry compression is 612 KB; the rebuilt private static preview now opens readable scenario/budget groups and reconciled four-hour results with the backend stopped.
- Publication request sent with explicit user authorization and verified in Sent on2026-10-02. Contact details remain in ignored local records. Translink approval is pending.
- Earlier local Python suite: 57 passed, with one optional live PostGIS check skipped; actual PostGIS was also checked separately. The final expanded suite is recorded below.
- Complete weekday morning windows: **0/5**. Three final public morning bundles: **0/3**. Future evidence must be collected; afternoon recordings cannot satisfy these gates.

### 2026-10-03 private milestone checks

- Expanded local Python suite: 75 passed including the live PostGIS checks; eight frontend checks passed. The expanded suite includes final export/verifier corruption and exact-file-set regressions; ARCH-004 records independent acceptance.
- Root independently verified the reviewed reproduction manifest digest, all 65 file hashes and the current frozen analytical engine/adapter identities. ARCH-004 records the separate recomputation and proxy review.
- Bounded scan of 125 proposed nonignored files found no known credential-pattern hits, files over 5 MB, raw/runtime archive paths or the account email address. The exact scan scope and file hashes remain private.
- Persistent Mac collector is running; planned first eligible mornings remain 5–9 October, 06:00–12:00 Brisbane time, subject to complete actual coverage.

### 2026-10-22 final morning evidence

- Frozen final dates/cutoff/requests/targets: Decision 27, `configs/morning-evaluation.v1.json`, ARCH-007 and INT-008. Development October 9/13 and reserve October 22 do not replace final cases.
- Strict final report is complete: 54/54; config SHA256 `1b52daf5a9a85b6c0110b18b1b376042cd57ffbbb03d20feff118d175b214c9a`. Final outcomes are in `FINDINGS.md`; the original development findings remain verbatim in `DEVELOPMENT_FINDINGS.md`.
- Independent final report: `data/processed/morning-evaluation-v1/independent-verification.json`, passed 54/54 with zero errors, checked 22 October at 02:46:33 UTC. Historical partial handoff counts do not override this completed evidence.
- No final case lost/restored a sixty-minute query. Nominal stop closure selected two bus-hours at every nonzero budget, reducing total capped query duration by 584/782/782 seconds. +300/+600-second paired stresses selected zero duty with no reduction. This is not passenger or operating benefit evidence.
- Exact offline reproduction matched all 54 full results from the 225-file private pack in 508.3545001249295 seconds. It did not fetch replacement live inputs.
- Actual journey API benchmark measured 100 calls/date (300 total); date p95 values 0.074713/0.172849/0.161413 seconds. Two date clients overlapped; first snapshot lookup was included. Original per-run recovery durations remain null.
- Morning independent OTP review and its unchanged original denominators are documented in `REFERENCE_VALIDATION.md` and ARCH-009. Walking costs remain uncalibrated; missing origin null equality is not credited as transit agreement.
- Focused UI-003 checks: 13 pure-helper/adapter tests passed; actual index exposes all 54 results through date/scenario/stress filters with a protocol-selected initial view. INT-009 records separate compact-manifest corruption and synthetic static-build checks. Final candidate CI/browser/deployment checks remain root-owned.
- Publisher reply handling is now supported by user-provided written correspondence rather than an unanswered request. Final package licence/credential/CI/artifact/publication bindings remain pending until recorded by root. Older pending counts/permission statements above are retained as dated history.
- Root additionally confirmed the opt-in live PostGIS/API integration checks: **2/2 passed**; current scope and commands are recorded in `VERIFICATION.md`. Earlier verification is preserved separately in `DEVELOPMENT_VERIFICATION.md`. This does not replace pending release-candidate CI or deployment checks.
- Current local regression evidence in `VERIFICATION.md`: **204 Python passed**, one optional infrastructure skip, and **28 frontend passed**. These replace older suite counts for current local verification while retaining their dated history above.
