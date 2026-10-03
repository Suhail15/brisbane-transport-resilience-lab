# Routing and resilience methodology

This local pilot uses recorded Translink GTFS/GTFS-RT and OpenStreetMap inputs.
Disruptions, additional buses and their journey outcomes are hypothetical. The
analysis counts configured journey requests, not passengers. It does not estimate
actual savings, crowding, bus availability, capacity or observed service punctuality.

## Snapshot availability and quality

Every source object is preserved with a content hash and an aware receipt timestamp.
A replay at T may use only records received on or before T. Feed header/individual
entity event timestamps are separate source fields, not substitutes for receipt time.
Missing timestamps and unmatched identifiers remain unknown. A current feed header
does not prove that an entity without its own event timestamp is fresh.

GTFS weekly calendars select services for the Brisbane service date; dated additions
and removals override them. Times >=24:00 retain their seconds since service-day
midnight. Relevant trips keep every adjacent movement, including stops outside the
pilot geography. GTFS schedules and GTFS-RT predictions are not measured arrivals.
Stale/missing/unmatched/invalid trip updates fall back explicitly to complete
scheduled trips and are reported in quality diagnostics.

The weekday recording window is 06:00–12:00 Australia/Brisbane. Collection completeness
is a receipt-coverage fact, separate from per-entity freshness, schedule validity and
walking coverage. Development afternoon captures do not meet the morning gate.
No later receipt may repair an earlier snapshot without becoming a new snapshot.

## Pilot and walking boundary

The pilot covers Fairfield/Annerley, South Bank and Brisbane CBD. A GTFS platform can
exist without active service on the selected date. Such platforms stay visible with
their source absence; active primary OD stops are selected deterministically from
source services and exclusions are reported. No rail service is inferred for a
platform with no retained service. Corridor scenario targets are actual retained
adjacent movements.

Walking uses directed paths on actual retained OSM pedestrian edges. Each stop-pair
path is at most 600m at 1.2m/s, with integer duration rounded upward. Stop coordinates
are associated to OSM nodes only within a documented 30m tolerance. Actual OSM edge
length and geometry remain separate from endpoint association distances; a
conservative path-eligibility guard includes those distances. Those diagnostics do
not create a mapped platform/entrance connector. Unresolved connectors, disconnected
stops and geography outside the extract remain explicit incomplete coverage.

Routing takes one complete OSM link per access/interchange/egress and never chains
stop links to evade the distance limit. After alighting, a vehicle change requires
one 300s allowance plus actual walking duration. Initial boarding/walking and
continuation on the same trip require no interchange allowance. This allowance is a
conservative analysis assumption, not a calibrated station-specific minimum.

## Connection scan and audit

The engine sorts adjacent movements by departure. It retains independent stop labels
for each boarding count and walking eligibility, because an earlier arrival using
more buses cannot dominate a later arrival using fewer. Immutable predecessor
paths prevent later stop-label improvements from changing an earlier boarded trip.
Per-trip onboard state allows passengers to pass stops with no pickup/drop-off.
At most four boardings permit three vehicle changes, even when a journey traverses
many adjacent movements on the same vehicle.

The result minimizes arrival time, then boardings/changes, then a deterministic
itinerary key. Same-trip adjacent movements compress into one transit leg with all
connection ids retained; walking legs retain OSM node ids and geometry. Journey
duration includes initial waiting, interchange waiting, riding and walking.

## Scenarios

Scenario intervals are half open. A trip cancellation removes a named whole trip
that overlaps its interval. A stop closure disables boarding/alighting events in
the interval but permits passing. A corridor closure cancels the whole trip when
its adjacent movement crosses the selected segment during the interval.

Additional delays start at the first eligible future movement of a named trip and
propagate to that and all later arrival/departure events. Already departed movements
are unchanged. Multiple additional delays are additive against the original
snapshot, then restrictions use effective delayed times. This order is independent
of scenario list order. Journeys are rerouted on the changed timetable so missed
changes and alternatives use the same transfer rules.

## Fixed requests and definitions

An experiment fixes between one and 500 requests at quarter-hour departure offsets
0/15/30/45/60 minutes across the next hour including its endpoint. Stable hash
sampling preserves a reproducible bounded set when the OD product exceeds 500.
Every primary request has weight one. Supplied research OD weights are retained
without silently changing the primary count or objective.

For the same N requests, define B/D/R as the sets arriving within 3,600 seconds under
baseline/disruption/recovery. Lost is `|B minus D|`; restored is
`|(B minus D) intersect R|`. Restored fraction divides by lost, and is null when lost
is zero. All reachable-count percentages divide by N. Baseline-unreachable or late
requests are not silently omitted from the duration comparison.

For every request, capped duration is `min(raw_duration, 5400)` if a route exists and
5,400 seconds otherwise. Each total includes all N requests. A reachable route over
the cap retains its raw duration in the itinerary. This cap is a declared optimization
penalty, not a claim that an unreachable journey actually lasts 90 minutes.

A planned missed connection is a baseline vehicle change whose effective preceding
arrival plus its baseline OSM walk and one 300s allowance exceeds the effective next
departure, while both services and relevant pickup/drop-off events still exist.
Cancelled service and unavailable events are separate availability failures.
Report both missed changes and requests with at least one miss, with denominator N.
These are simulated planned connections, not observed passenger misses.

## Recovery candidates and duties

The candidate selector begins with baseline journeys made slower or unreachable.
It identifies their changed transit corridor stops and associates nearby bus stops
only through actual supplied one-hop walking links. Existing paired bus patterns
must touch at least two distinct corridor anchors. Identical physical/access
topologies are deduplicated across timing variants; the selected variant has source
departure nearest the activation time. Deterministic ranking favors coverage of
previously uncovered lost/affected requests, route diversity and corridor coverage.
This is a bounded selection heuristic, not a passenger demand model. If no relevant
existing pair is supported, it returns no recovery candidate.

Each of at most 12 candidates consumes one bus for two hours at a cost of exactly two
bus-hours. Both directional patterns have matching terminal stop ids and must be
anchored to actual full bus source trips. Timing offsets are sourced from the
recorded GTFS templates; the engine validates source route/stop topology while
real-time arrival shifts do not redefine the nominal relief pattern. No deadhead or
unobserved terminal connector is invented.

Activation is at least T+600s. A complete cycle is outward run, 300s terminal turn,
inward run, and 300s at the starting terminal. Only complete cycles finishing within
the 7,200s duty are added; any leftover idle time still costs the full duty. A closure
blocking any added trip makes that entire duty infeasible. Stop closure allows
passing under the event rules. Budgets 0/2/4/8 permit 0/1/2/4 buses.

## Search and comparison

The objective is lexicographic: maximize restored count; minimize total capped
90-minute duration across all N; minimize bus-hours; then sorted candidate ids.
Greedy reroutes all requests for each candidate marginal and evaluates every prefix,
then bounded one-/two-duty replacements explore alternatives. No intervention and
the eligible pattern with the most distinct disrupted source trips are included as
comparison policies. This service count is not passenger demand.

The reported plan is the best feasible plan actually evaluated; bounded search does
not claim global optimality. Exhaustive search proves the best subset only within
its small supplied candidate set. All considered ids and infeasible reasons remain
auditable. Progress callbacks expose stage/count metadata, never a partial plan.
Cancellation is acknowledged at preparation and plan boundaries through
`RecoveryCancelled`, with no partial result returned or published.

## Verification and independent comparison

`tests/engine/oracle.py` is structurally independent of CSA. It enumerates every
legal board/alight pair on a complete trip and searches those time-dependent ride
edges with a heap. It imports contracts only. Seeded tests compare 288 query results
across 24 synthetic networks. Separate fixtures hand-calculate transfer arithmetic,
scenario windows, all-request penalties, bus cycles and recovery subset optima.
Synthetic unit fixtures never substitute for recorded data or public bundles.

At the architecture handoff, 40 engine tests passed with Python 3.11/Pydantic 2.
Real-source route comparison uses **OpenTripPlanner (OTP)** with matched schedule,
time, walking speed and transfer assumptions; discrepancies must be explained,
especially station access, OTP street linking, generalized cost and existing through
service. An OTP server starting or schema introspection succeeding is not routing
verification. Actual queries and comparison outcomes are recorded in
`docs/REFERENCE_VALIDATION.md`: six distinct identical transit paths and six
source-specific access/path explanations, with zero unexplained cases. Raw exact
counts remain 1/6 and 6/7; reviewed acceptance is confined to schedule-core timing
and documented access differences. Walking coverage and GTFS-RT prediction accuracy
are not established by these checks.

OTP 2.10 combined build-and-serve was observed to fail with a populated graph and an
empty Raptor routing index. Primary source inspection shows application construction
maps Raptor before the combined graph build; use separate build/save and load/serve
processes and verify an actual query. Evidence and startup details belong to the
integrator's local runtime audit. Source: [OTPMain 2.10.0](https://github.com/opentripplanner/OpenTripPlanner/blob/v2.10.0/application/src/main/java/org/opentripplanner/standalone/OTPMain.java)
and [ConstructApplication 2.10.0](https://github.com/opentripplanner/OpenTripPlanner/blob/v2.10.0/application/src/main/java/org/opentripplanner/standalone/configure/ConstructApplication.java).

## UI, static export and release

New analysis runs bind exact canonical input, request/scenario/candidate sets,
immutable snapshot/source content, engine code/version and literal assumptions in
`RunMetadata`; see `docs/CONTRACTS.md` for hash rules. Legacy runs are recomputed.
The approved next experiment persists 20 source-selected OD pairs (100 requests)
across dates, retaining missing-service/unavailable requests in the denominator.
It predefines four disruption examples before seeing recovery results. A bounded
0/300/600s bus running-time sensitivity proportionally scales future incumbent trip
suffixes and hypothetical directional patterns, keeps activation/turns fixed and
regenerates duty feasibility for all policies. Candidate ids stay nominal/fixed;
derived input copies preserve raw snapshots. This is hypothetical sensitivity.

The approved local UI has Replay, Scenarios, Recovery and Evidence views. Replay
shows actual GTFS display shapes and eligible recorded vehicle positions with date,
time/speed controls, quality labels and gaps; it performs no invented interpolation.
Forms select actual trip/stop/adjacent segment ids and the frozen four scenario types.
Recovery explains the three comparison policies, equal-request denominator and
capped-duration objective. Evidence defines receipt/event times, source quality,
walking limitations, attribution and incomplete collection/release conditions.

Display and choices DTOs are separate from the engine. Static mode lazily fetches
compact frames/choices/shared geometry and completed experiment results; full
TimetableSnapshot inputs remain local. Public export must select three real complete
morning dates/windows with eligible provenance and only associated completed runs.
It requires five complete weekday morning collections plus independent routing,
performance, CI, secrets, static-demo, source attribution and licensing/contact/
approval evidence. Translink terms and OSM derivative-data obligations require
explicit review. Missing future recordings cannot be filled with synthetic data.
