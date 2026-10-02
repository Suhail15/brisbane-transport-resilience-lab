# Implementation and release checklist

Every stage and gate starts as **pending**. Change a status only after recording evidence for work actually completed. Keep recorded observations, derived measures, and hypothetical scenario inputs and outputs distinct.

## Ordered implementation stages

1. [ ] **Establish project and instructions — PENDING**  
   Establish project conventions, ownership, cross-platform workflow, and evidence rules. Evidence: reviewed repository instructions and task handoff format.

2. [ ] **Audit data and lock the pilot — PENDING**  
   Audit the acquired real source archive and its provenance, coverage, identifiers, timestamps, and licence terms. Lock the pilot corridor around Fairfield/Annerley, South Bank, and CBD, the study period, and the historical `as_of` received-data cutoff. Inputs received after that cutoff must not affect the replay. Evidence: source audit, provenance manifest, pilot decision, and cutoff rule.

3. [ ] **Establish the development foundation — PENDING**  
   Create the approved, reproducible macOS and Windows development setup for the accepted stack. Evidence: clean setup notes and environment checks on supported systems.

4. [ ] **Collect and archive raw sources — PENDING**  
   Acquire the approved bus and rail source snapshots, preserve originals outside Git, and record retrieval time and hashes. Inspection downloads are part of the approved source audit; do not request repeated permission for each source file. Evidence: source register, archive manifest, hashes, and integrity check.

5. [ ] **Normalize and reconstruct service — PENDING**  
   Validate and normalize records, preserve source timestamps and identifiers, and reconstruct service events with traceable provenance. Evidence: schema and quality report plus a reproducible transformation.

6. [ ] **Implement CSA and independent OpenTripPlanner routing — PENDING**  
   Implement the approved connection-scan algorithm (CSA) and compare its routes independently with OpenTripPlanner (OTP). Lock pilot route parameters: maximum walk distance 600 m, walking speed 1.2 m/s, transfer slack 300 seconds, and at most three transfers. OTP means OpenTripPlanner throughout this project. Evidence: routing contract, fixtures, independent comparisons, and discrepancy review.

7. [ ] **Replay observed service — PENDING**  
   Replay recorded bus and rail service for the locked pilot using only data received on or before the recorded cutoff. Evidence: reproducible runs for the selected periods and input manifests.

8. [ ] **Model disruptions — PENDING**  
   Add clearly hypothetical disruption scenarios and replacement-bus service constraints; keep their inputs visible and distinct from recorded operations. Evidence: reviewed scenario definitions and traceable scenario outputs.

9. [ ] **Calculate impact metrics — PENDING**  
   Define and calculate rider-facing and service impact measures against the observed replay and scenario baseline. Evidence: metric definitions, independently checked examples, and documented limits. Service performance indicators that require separate calibration are outside this release.

10. [ ] **Search for recovery plans — PENDING**  
    Implement the bounded search for feasible replacement-bus recovery under the approved capacity, access, availability, and routing constraints. Evidence: reproducible cases showing feasible and infeasible plans and their assumptions.

11. [ ] **Report robustness findings — PENDING**  
    Assess how findings change across source gaps, timing assumptions, disruption choices, and recovery constraints. Evidence: documented sensitivity runs and limitations tied to recorded inputs.

12. [ ] **Build the product interface and package a static demo — PENDING**  
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

No stage or release evidence has been recorded in this checklist yet. Add dated links or repository paths as work completes. Do not mark an item complete on the basis of a plan.
