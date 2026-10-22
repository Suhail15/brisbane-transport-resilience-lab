# ARCH-009

- Title: independent diagnosis and review of the 20 October OTP comparisons
- Status: independent review complete at the stated bounded scope; overall release acceptance remains coordinator-owned
- Owner: ARCH-009 independent analytical review agent
- Reviewer: root coordinator

## Model and reasoning

- Requested model: GPT-6.1 Sol.
- Requested reasoning: max, retained from ARCH-008.
- Actual exposed configuration: inherited parent-session configuration; serving identity and reasoning effort are not independently introspectable. No additional agent or model override was created.

## Approved specification and decisions

- Coordinator follow-up authorizes read-only local OTP GraphQL diagnostics and inspection of archived GTFS/OSM for schedule-only snapshot `608a4a6406eda7bfcafabc64`, 20 October 2026 at 07:30:05 Australia/Brisbane.
- Preserve every original case and disagreement. Explain actual source/path arithmetic; never pass by a general tolerance or erase a difficult query. New direct-platform checks must be labelled as post-initial diagnostics.
- Coordinator separately authorizes writing the exact derived review report `data/processed/morning-reference/2026-10-20/otp-reviewed-morning.json`, covering all thirteen original cases and binding the current raw reports and proofs.
- The approved review boundary remains scheduled transit-path correctness plus source-specific access-model discrepancy review. No claim of complete walking coverage, calibrated pedestrian speed or global route equivalence is authorized.

## Required inputs and dependencies

- Current walking/core reports and preserved initial core report in `data/processed/morning-reference/2026-10-20/`.
- Full immutable schedule-only snapshot and quality audit under `data/processed/snapshots/608a4a6406eda7bfcafabc64*`.
- Archived original GTFS digest `c6b892ac9ffd3c8fdc4546cd88c2329727ae21bf6abb28d33e1496b98a5c85ac` and OSM digest `0a64e9b981db6ffda53397bd01a11051688ac60a2fa79a51aa336cb138e09c4d`, their immutable receipt files, and the read-only receipt journal.
- Existing OTP 2.10.0 server at `http://127.0.0.1:8801/otp/gtfs/v1`, observed running against `data/derived/otp-morning-2026-10-20`. Its frozen router configuration retains the 500-second access/egress limit.
- Python and `httpx` from the repository environment. Official versioned method reference: <https://docs.opentripplanner.org/en/v2.10.0/RouteRequest/>.

## Files owned

- Diagnostic JSON and scripts only within ignored `data/runtime/release-2026-10-22/otp-diagnostics/`.
- Coordinator-approved derived report `data/processed/morning-reference/2026-10-20/otp-reviewed-morning.json`.
- `docs/tasks/ARCH-009.md`.

## Expected output

- `probe.py` and saved exact query/variable/response JSON document direct platform rail checks, three station-access walks, returned walking geometry/steps, and schema inspection.
- `review.py` independently validates source availability and hashes, the original cases, actual source transit events, and actual OSM walk edges/geometry/length/time. Run with `.venv/bin/python data/runtime/release-2026-10-22/otp-diagnostics/review.py` while the referenced raw artifacts remain unchanged.
- The resulting report binds its script, snapshot, quality audit, source hashes, current raw report hashes, preserved initial core report, current checker, OTP inputs/configuration and diagnostic files.
- Four original distinct transit paths match exactly. Two additional direct `600194` origins confirm the specific scheduled rail subpaths implicated in the original access differences; they remain outside the original denominators and are explicitly selected after the initial results.

## Acceptance checks

- PASS on 22 October 2026: executable source review completed with **13 original cases retained, 4 original exact transit paths, 8 source-specific explained path cases, 1 confirmed unavailable-source case, 2 separately labelled post-initial direct-platform matches, and 0 unexplained cases**. The JSON `passed` field applies only to the stated schedule/access review boundary.
- Raw results remain **walking 1/6 and core 4/7**, both raw `passed: false`. Walking's sole raw equality is null arrival at absent origin `600189`; it is explicitly excluded from the transit-match count.
- PASS: **53 distinct scheduled source movements** checked against the original archived GTFS stop-time rows. All retained transit-leg times, boarding/alighting events and transfer arithmetic used in the reviewed CSA outputs reconcile.
- PASS: **12 distinct OSM walk paths** checked against original source nodes, permitted directed way edges, exact geometry, geodesic length and `ceil(length / 1.2)` duration. No walking link or stop/platform connector was invented.
- PASS: current core and walking use the same current checker hash. The preserved initial core still reports 4/7. Every previous core case field, including full raw OTP responses, is identical in the rerun; its only added case field is explicit `adapter_unavailable: false`. Exact initial/current report and checker hashes remain in the derived report.
- PASS: source receipt files equal the read-only journal rows, source payloads match their hashes, and both sources were received by the historical cutoff. OTP subset/PBF hashes match its preparation manifest.

| Original suite | OD | Raw arrival delta, CSA minus OTP | Evidence-backed review |
| --- | --- | ---: | --- |
| Walking | 600006 → 600018 | +12s | Same rail trip and 27,660s arrival; source OSM egress 38.156609m/32s versus OTP 23.70m/20s accounts for all 12s. |
| Walking | 600188 → 600016 | -16s | Same rail trip and 27,660s arrival; source OSM egress 30.279072m/26s versus OTP 18.98m/42s accounts for all -16s. |
| Walking | 600189 → 600019 | unavailable | Original GTFS has no 600189; CSA retains an unavailable request and OTP returns `LOCATION_NOT_FOUND`. No transit match credited. |
| Walking | 3713 → 18 | -116s | CSA reaches 600194 in 455s. OTP's returned 573.91m/592s walk exceeds the 500s access budget and the 475s available before the 07:38 train. OTP instead uses bus/19→18 egress; source stop 18 is outside the 30m snap limit. |
| Walking | 3692 → 600006 | -19s | Same rail trip and 27,900s arrival; source OSM egress 52.380981m/44s versus OTP 66.43m/63s accounts for all -19s. Both access paths catch the same train. |
| Walking | 600052 → 600018 | +835s | Source 600052 and 600194 associate to the same OSM node, with no positive-length mapped CSA connector. OTP returns a 7.38m/7s connector and catches 07:38 rail; CSA uses the validated bus alternative. 600052 is active in this timetable; no historical inactive-stop explanation is reused. |
| Core | 600188 → 600028 | 0 | Identical trip, stops, departure and arrival. |
| Core | 600188 → 600016 | -16s | Same platform-egress proof as the original walking case; retained as its own original case. |
| Core | 3692 → 10795 | 0 | Identical trip, stops, departure and arrival. |
| Core | 3689 → 19 | 0 | Identical trip, stops, departure and arrival. |
| Core | 3716 → 25 | -542s | CSA reaches 600194 in 403s; OTP's returned 507.70m/551s walk exceeds 500s and misses 07:38. Direct platform-origin OTP confirms the train to Central. Its final OTP egress is 200s versus source OSM 178s; that difference is retained separately. |
| Core | 19080 → 18 | -116s | CSA reaches 600194 in 450s; OTP's returned 574.44m/614s walk exceeds 500s and misses 07:38. Source rail-to-bus transfer walk is 271s plus one 300s allowance, making the 28,680s bus feasible. |
| Core | 3692 → 1180 | 0 | Identical trip, stops, departure and arrival. |

- Post-initial diagnostic checks: `600194 → 600016` matches the 07:38–07:54 scheduled rail path, and `600194 → 600186` matches 07:38–07:47. They confirm that OTP includes the train and establish six distinct exact scheduled paths when explicitly combined with the four original matches. They do not change 1/6, 4/7 or the original thirteen-case denominator.

## Escalation issues

- Root preserved and reran the core report with the current missing-stop-aware checker during review. Refreshed artifact identities and explicitly verified unchanged original core case outputs before final handoff.
- Current source correction: 600052 has retained service. Its new discrepancy concerns the missing mapped connector to 600194, not an inactive station. Raised this distinction to the coordinator.
- One GraphQL request containing two simultaneous `__type` fields was rejected by OTP's introspection policy. Single-type queries succeeded. This was an introspection-only response, not a routing outcome; the saved JSON retains it. One initial diagnostic script path was corrected before querying. No repeated unresolved failure occurred.
- Remaining limits are explicit: returned OTP access paths contain steps and differ from source fixed-speed paths, but no exact decomposition of staircase/crossing delay was established. Real walking feasibility, station accessibility, full network earliest-arrival equivalence, real-time predictions and measured arrivals remain unvalidated. These limits do not erase the concrete access-time and source-path explanations.
- No server restart, router change, source rewrite, engine edit, primary-run modification, new pre-frozen-selection claim or commit occurred. Next owner is the root coordinator, which incorporates the exact final report hash and this bounded scope into the OTP release gate.
