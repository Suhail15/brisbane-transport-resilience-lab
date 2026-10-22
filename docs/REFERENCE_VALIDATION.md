# Independent routing reference validation

The final morning reference review uses **20 October 2026, 07:30:05
Australia/Brisbane**, schedule-only snapshot `608a4a6406eda7bfcafabc64` and
OpenTripPlanner (OTP) 2.10.0. It is independent scheduled transit-path and
source-specific access review, not measured-arrival validation or proof of full
network equivalence.

Raw agreement remains **4/7 core cases** and **1/6 walking cases**; both raw
report pass fields remain false. The sole walking equality is a null arrival at
absent origin 600189, explicitly excluded from the transit-match count. No
original disagreement or denominator was removed.

## What was independently checked

ARCH-009 retained all thirteen original cases and found **four original exact
transit paths, eight source-specific explained path cases, one confirmed
unavailable-source case and zero unexplained cases**. Two direct-platform rail
checks were added **after the initial results** to diagnose the access differences.
They match exactly but remain outside the original denominators: four original
matches plus two later diagnostics must not be presented as six originally
preselected successes.

The review checked **53 distinct scheduled source movements** against archived
GTFS stop times and **twelve distinct OSM walking paths** against source nodes,
permitted directed edges, geometry, geodesic length and `ceil(length / 1.2)`.
Source receipts precede the cutoff; immutable receipt files, journal rows and
source payload hashes agree. No walking connector or timetable event was invented.

The reviewed pass applies to this documented source/transit/access scope. It does
not mean the raw suites agree completely, station accessibility is validated,
walking costs are calibrated, or real-time predictions became observed arrivals.

## Unchanged parameters and source identities

Both engines use the same extracted schedule/OSM sources, 1.2 m/s walking,
300-second transfer slack and at most three vehicle changes. Project walking
links use actual directed OSM edges with at most 600 m per link and a separate
30 m stop-association limit. OTP retains its frozen **500-second access/egress
limit**; its returned access durations can differ from source fixed-speed paths.

- GTFS SHA256: `c6b892ac9ffd3c8fdc4546cd88c2329727ae21bf6abb28d33e1496b98a5c85ac`.
- OSM SHA256: `0a64e9b981db6ffda53397bd01a11051688ac60a2fa79a51aa336cb138e09c4d`.
- OSM was acquired October 2 and is not a historical October 20 street observation.
- Detailed hashes of raw reports, the preserved initial core report, checker,
  source audits, OTP inputs/router configuration and diagnostic proofs are bound
  in `data/processed/morning-reference/2026-10-20/otp-reviewed-morning.json`.

## Original cases and retained differences

Delta means CSA arrival minus OTP arrival; times below are seconds unless stated.

| Suite | OD stop IDs | Raw delta | Source-specific finding |
|---|---|---:|---|
| Walking | 600006 → 600018 | +12 | Same train and arrival; source egress 38.156609 m/32 s versus OTP 23.70 m/20 s explains the difference. |
| Walking | 600188 → 600016 | −16 | Same train and arrival; source egress 30.279072 m/26 s versus OTP 18.98 m/42 s explains the difference. |
| Walking | 600189 → 600019 | unavailable | Original GTFS has no 600189. CSA retains an unavailable query; OTP returns LOCATION_NOT_FOUND. No transit match is credited. |
| Walking | 3713 → 18 | −116 | CSA access to 600194 is 455 s; OTP's returned 573.91 m/592 s exceeds both its 500 s access budget and 475 s before the 07:38 train. OTP takes a bus alternative; stop 18 also lies beyond the project's 30 m snap limit. |
| Walking | 3692 → 600006 | −19 | Same train and arrival; source egress 52.380981 m/44 s versus OTP 66.43 m/63 s explains the difference. |
| Walking | 600052 → 600018 | +835 | Both platforms associate to the same OSM node, with no positive-length mapped CSA connector. OTP uses a 7.38 m/7 s connector and catches 07:38 rail; CSA takes a validated bus path. 600052 is active in this timetable. |
| Core | 600188 → 600028 | 0 | Identical trip, boarding/alighting stops and scheduled event times. |
| Core | 600188 → 600016 | −16 | Same platform-egress evidence as the original walking case, retained in the core denominator. |
| Core | 3692 → 10795 | 0 | Identical trip, stops and scheduled event times. |
| Core | 3689 → 19 | 0 | Identical trip, stops and scheduled event times. |
| Core | 3716 → 25 | −542 | CSA access to 600194 is 403 s; OTP's returned 507.70 m/551 s exceeds 500 s and misses 07:38. Direct-platform OTP confirms the train. OTP final egress 200 s versus source 178 s remains separately disclosed. |
| Core | 19080 → 18 | −116 | CSA access to 600194 is 450 s; OTP's returned 574.44 m/614 s exceeds 500 s and misses 07:38. Source transfer walking is 271 s plus one 300 s allowance, making the later bus feasible. |
| Core | 3692 → 1180 | 0 | Identical trip, stops and scheduled event times. |

The two post-initial diagnostics are `600194 → 600016` (07:38–07:54) and
`600194 → 600186` (07:38–07:47). They show that OTP includes the implicated
scheduled train. They do not replace failed cases, change raw agreement, or
establish pre-result selection of those diagnostics.

Different access routes contain steps and different returned costs, but no exact
staircase/crossing-delay calibration was established. The review explains actual
source paths and event arithmetic while retaining that limitation. In particular,
October 2's inactive-Fairfield explanation is not reused for October 20: 600052
has source service in the new timetable.

## Evidence and reproducibility

The authoritative review is
`data/processed/morning-reference/2026-10-20/otp-reviewed-morning.json`.
Read-only query responses and executable proofs are retained under
`data/runtime/release-2026-10-22/otp-diagnostics/`; their original source artifacts
remain local and ignored. [ARCH-009](tasks/ARCH-009.md) records all checked cases,
acceptance outcomes and limitations. The source review can be repeated with its
archived inputs using the saved `review.py`; it does not require changing primary
morning runs or loosening parameters.

The preserved initial core and current core both report 4/7. Every previous case
field, including full raw OTP responses, is unchanged; the current report adds
explicit adapter-unavailable metadata. The walking/core current checker identities
match. [ARCH-008](tasks/ARCH-008.md) separately describes independent reconciliation
of all 54 primary morning cases; it is not an OTP agreement claim.

## Earlier development reference

The October 2 afternoon study remains historical development evidence:
`docs/tasks/ARCH-001.md`, `data/processed/otp-comparison.json`,
`otp-core-comparison.json` and `otp-reviewed-validation.json`. It had raw agreement
1/6 and 6/7, six distinct exact scheduled transit paths and six explained access
cases. Those results are not substituted for the current morning denominators.
The old snapshot retains its original walking derivation and is not silently
rewritten to match current code.

Official method references: [OTP 2.10.0 route request](https://docs.opentripplanner.org/en/v2.10.0/RouteRequest/)
and [configuration](https://docs.opentripplanner.org/en/v2.10.0/Configuration/).
