# Independent routing reference validation

Reviewed 2026-10-02 by ARCH-001, GPT-6.1 Sol with max reasoning. Root approved the
bounded matched-transit check and source-specific access review. These afternoon
development queries use real schedule/OSM inputs; they are not morning recordings,
measured arrivals or validation of GTFS-RT predictions.

## Reproducible inputs and scope

The official OpenTripPlanner (OTP) 2.10.0 reference runs on the same extracted GTFS
and OSM source material. Both engines use 1.2m/s walking, 300s transfer slack, at most
three vehicle changes and schedule-only service. Query time is 2026-10-02 15:00
Australia/Brisbane. OTP returns up to 12 alternatives over a one-hour search window;
the checker excludes alternatives with a walk leg above 600m. It records all returned
responses, routing errors and itineraries rather than assuming completeness of OTP's
Pareto results. Actual stop/platform linking differs between the engines.

Input snapshot is `94005388692bbc7af14487de`, cutoff
`2026-10-02T04:15:46.387933+00:00`. Eligible sources were received before that cutoff:

- Translink GTFS SHA-256: `2614954a251786aa312a434551fe7000cb10a9b928a9d8f412a69a98c1d1f8da`.
- OSM extract SHA-256: `0a64e9b981db6ffda53397bd01a11051688ac60a2fa79a51aa336cb138e09c4d`.
- Exact stored snapshot SHA-256: `2427321f0d017e05ae2517b06dffcafed6b9b1635d7af112671d5a8742c6bf4c`.

Raw and reviewed local evidence is `data/processed/otp-comparison.json`,
`otp-core-comparison.json` and `otp-reviewed-validation.json`. Reports bind engine
version/code hash, checker hash, snapshot bytes and source receipt/content records.
The immutable reference snapshot uses the earlier endpoint-distance-inclusive
walking derivation; current walking inputs use actual OSM edge length with separate
snap diagnostics. It is retained as recorded evidence. Exact transit-only checks do
not depend on that difference; old walking inputs are not silently rewritten.

## Exact matched transit paths

The extra query set was selected from actual scheduled paths before requesting OTP,
including bus and rail. Six distinct cases have identical boarding/alighting stops,
GTFS trip ids, departure/arrival times and zero transfers, with no walking in either
itinerary. All times below are Brisbane local time on October 2.

| Origin → destination stop id | Mode | Actual GTFS trip id | Both depart | Both arrive |
| --- | --- | --- | --- | --- |
| 600188 → 600028 | Rail | `38659520-QR 26_27-44010-1E57` | 15:00 | 15:07 |
| 600188 → 600016 | Rail | `38659520-QR 26_27-44010-1E57` | 15:00 | 15:09 |
| 3692 → 10795 | Bus | `38819248-BT 26_27-44106` | 15:08 | 15:14 |
| 3689 → 19 | Bus | `38816389-BT 26_27-44106` | 15:11 | 15:33 |
| 3716 → 25 | Bus | `38816389-BT 26_27-44106` | 15:10 | 15:35 |
| 3692 → 1180 | Bus | `38819248-BT 26_27-44106` | 15:08 | 15:10 |

This small real-source check covers scheduled same-vehicle bus/rail timing. Transfer
slack, boardings Pareto labels, passing closed stops and independent earliest-arrival
search are also checked by the independent fixture oracle in `tests/engine/oracle.py`.
It does not establish exhaustive network equivalence or every real interchange.

## Original six cases and actual access evidence

Delta is CSA arrival minus OTP arrival in seconds. Original raw exact agreement is
**1/6**. Each difference below retains its original disagreement.

| Origin → destination | CSA / OTP arrival | Delta | Source/path evidence |
| --- | --- | --- | --- |
| 600006 → 600018 | 15:14:26 / 15:14:37 | -11 | Same rail trip `38659769-QR 26_27-44010-DP65`, arriving 600016 at 15:14. CSA actual OSM egress takes 26s; OTP street egress takes 37s, accounting for the entire arrival difference. Both catch the same 15:05 departure despite different access walks. |
| 600188 → 600016 | 15:09 / 15:09 | 0 | Exact matched rail case above. |
| 600189 → 600019 | 15:20:26 / 15:15:17 | +309 | OTP walks from 600016 to 600019 after the same train. Both stop coordinates associate to OSM node 9551479283, but there is no actual mapped platform connector. CSA does not invent a zero-length link and instead uses a Roma Street interchange. |
| 3713 → 18 | 15:43 / 15:33:56 | +544 | OTP walks to 3689, boards `38816389-BT 26_27-44106` to 19 and walks to 18. CSA has the access path to 3689 but no 19→18 egress: stop 18's nearest retained OSM node is 34.751m away, above the unchanged 30m association limit. CSA takes later direct bus `38821311-BT 26_27-44106`. |
| 3692 → 600006 | 15:39:51 / 15:31:03 | +528 | OTP uses bus `38816237-BT 26_27-44106` to 10795, walks to 600191 and uses rail `38659596-QR 26_27-44010-1E61`. CSA lacks 10795→600191 because that platform's snap distance is 37.859m, above 30m, and takes a different bus path. |
| 600052 → 600018 | 15:37:32 / no itinerary | — | Fairfield platform 600052 has no active connections in this schedule. CSA uses actual OSM access `osm:600052:3716` (403s) to bus `38816389-BT 26_27-44106`, then egress. OTP's stop-location origin has no eligible transit access and reports `NO_TRANSIT_CONNECTION`. CSA claims no Fairfield rail service. |

The seventh extra query, 19080→18, also has delta +544s: OTP uses an access walk to
3689 followed by the same bus/19→18 egress as the fourth case. The excluded destination
association provides the same source-specific explanation. Thus raw extra-set exact
agreement is **6/7**, not 7/7. No walk tolerance, timetable time or routing objective
was changed to obtain an agreement.

## Acceptance rule and result

The reviewed gate requires at least five distinct exact transit-only cases with
identical trip ids, stops, schedule event times and transfer count. Each other case
must have a source-specific checked explanation identifying the differing access
link, stop availability or exact walk-duration arithmetic; otherwise it is
unexplained and the gate fails. A generic tolerance or assertion that engines differ
does not satisfy this rule. Repeated OD/time cases count once.

`otp-reviewed-validation.json` records **6 distinct exact transit cases, 6 explained
access/path cases, 0 unexplained cases**, and `passed=true` for this stated scope.
Both raw report pass fields remain false. Walking coverage remains incomplete;
unresolved station entrances, the conservative 30m limit and different OTP street
linking remain disclosed limitations. New engine/input/checker versions require
new comparisons. Public release still requires the five complete weekday mornings,
three real morning bundles and all other gates.

Reproduce with a loaded reference server at port 8801 and the local source snapshot:

```sh
python scripts/check_otp.py --snapshot 94005388692bbc7af14487de --suite walking
python scripts/check_otp.py --snapshot 94005388692bbc7af14487de --suite core
python scripts/check_otp.py --snapshot 94005388692bbc7af14487de --review-existing
```

## Reference startup diagnosis and primary sources

Combined OTP `--build --serve` produced real query failures (`Index 1127 out of
bounds for length 0`) despite a populated graph and successful schema introspection.
Source inspection supports the diagnosis that application/Raptor mapping can occur
before the combined graph build. Separate `--build --save`, then a fresh process
using `--load --serve`, resolved the actual queries. This is a source-supported
diagnosis plus observed recovery, not a claim that every OTP deployment is affected.
The official [OTPMain 2.10.0 source](https://github.com/opentripplanner/OpenTripPlanner/blob/v2.10.0/application/src/main/java/org/opentripplanner/standalone/OTPMain.java)
and [ConstructApplication source](https://github.com/opentripplanner/OpenTripPlanner/blob/v2.10.0/application/src/main/java/org/opentripplanner/standalone/configure/ConstructApplication.java)
show construction/mapping order. [Official configuration documentation](https://docs.opentripplanner.org/en/v2.10.0/Configuration/)
defines graph/router configuration boundaries. Local logs are
`data/runtime/otp.log` and `data/runtime/otp-loaded.log`; graph inputs/configuration
are under `data/derived/otp/`.
