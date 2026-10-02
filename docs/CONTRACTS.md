# Frozen engine contracts, version 1.1

The source of truth is `services/resilience/contracts.py`, using Pydantic 2.
Version 1.1 adds compatible candidate-selection and progress/cancellation exports.
Models are immutable, reject unknown fields, and serialize with `model_dump(mode="json")`.
Import with `from resilience.contracts import ...` when `services` is on the Python path.
The engine performs no I/O. Pipeline and API adapters supply validated models.

## Time and provenance

`SnapshotMetadata.snapshot_at` is an aware timestamp. A source record may enter a
snapshot only when `received_at <= snapshot_at`; `event_at` is kept separately and
does not grant earlier availability. Raw records and recorded snapshots are immutable.
`service_date` and `Australia/Brisbane` determine midnight; `metadata.snapshot_s`
returns seconds since that midnight. Every routing, scenario and pattern time is an
integer service-day second, including values above 86,400. Pipeline calendar expansion
must apply `calendar_dates.txt` additions/removals after weekly calendar rules.
Trip instance ids include service date and GTFS trip id. Preserve every connection of
each relevant full trip; `sequence` is a zero-based contiguous connection ordinal.
Do not clip a retained trip at the pilot boundary or six-hour recording boundary.

Schedule and real-time adapters must resolve stop-time updates consistently before
constructing a snapshot. Scheduled fallback and stale/missing real-time data remain
explicit in `QualityMetadata`. Neither predicted arrivals nor downloaded files are
measured passenger outcomes or evidence of a complete morning collection.

## Timetable inputs

`TimetableSnapshot(metadata, stops, connections, walking_links, recovery_pairs)` is
the engine input. `Connection` is an adjacent stop-to-stop movement with route,
trip instance, mode, ordinal, departure and arrival; boarding/alighting restrictions
are independent. Connections may be supplied unsorted. Stop coordinates support map
rendering, but are never used to invent straight-line walking links.

Each directed `WalkingLink` carries its actual OSM node path and longitude/latitude
geometry, has length at most 600 metres and duration `ceil(length_m / 1.2)`.
Supply all relevant stop-pair paths meeting that limit. The engine permits one such
complete footpath per access, interchange or egress; it does not concatenate stop
footpaths into an unbounded walk. Reverse paths must be supplied separately.
Stop/platform association diagnostics `from_snap_distance_m` and
`to_snap_distance_m` are limited to 30m and do not create walkable connectors.
An offset platform requires an actual mapped entrance/platform path before walking
is marked verified. Unresolved/disconnected stops remain visibly incomplete in
quality warnings. The adapter must report snap coverage and cannot silently widen
the tolerance. OSM route geometry/length remains the factual path, not a straight
line from an unmatched stop coordinate.

After alighting, a subsequent boarding needs **300 seconds plus any walking time**.
The 300 seconds are charged once per vehicle change, including a change at the same
stop. Initial boarding, initial walking and same-vehicle continuation have no transfer
allowance. This is the chosen conservative interchange model, not a calibrated local
minimum connection time. Walking and interchange time must never be double counted.

## Engine signatures

All functions below are exported by `resilience.engine`.

```python
route(snapshot: TimetableSnapshot, request: JourneyRequest,
      *, max_boardings: int = 4) -> RouteResult
route_many(snapshot: TimetableSnapshot,
           requests: Sequence[JourneyRequest]) -> tuple[RouteResult, ...]
apply_scenarios(snapshot: TimetableSnapshot,
                scenarios: Sequence[Scenario]) -> ScenarioApplication
evaluate_scenarios(snapshot: TimetableSnapshot,
                   requests: Sequence[JourneyRequest],
                   scenarios: Sequence[Scenario],
                   *, recovered_snapshot: TimetableSnapshot | None = None
                   ) -> ScenarioEvaluation
generate_journey_requests(origin_stop_ids: Sequence[str],
                          destination_stop_ids: Sequence[str],
                          start_s: int, *, limit: int = 500
                          ) -> tuple[JourneyRequest, ...]
build_recovery_duty(snapshot: TimetableSnapshot,
                    candidate: RecoveryCandidate
                    ) -> tuple[RecoveryDuty, tuple[Connection, ...]]
plan_recovery(snapshot: TimetableSnapshot,
              requests: Sequence[JourneyRequest],
              scenarios: Sequence[Scenario],
              candidates: Sequence[RecoveryCandidate],
              budget_bus_hours: int,
              *, max_swap_evaluations: int = 128,
              on_progress: Callable[[RecoveryProgress], None] | None = None,
              should_cancel: Callable[[], bool] | None = None) -> RecoveryResult
exhaustive_recovery(snapshot: TimetableSnapshot,
                    requests: Sequence[JourneyRequest],
                    scenarios: Sequence[Scenario],
                    candidates: Sequence[RecoveryCandidate],
                    budget_bus_hours: int, *,
                    on_progress: Callable[[RecoveryProgress], None] | None = None,
                    should_cancel: Callable[[], bool] | None = None) -> RecoveryResult
```

The request set is fixed once per evaluation and shared across all compared plans.
Generation uses departure times `start_s + {0, 900, 1800, 2700, 3600}` for the next
hour including its endpoint, stable sorted OD ids, excludes equal origin/destination,
and deterministically samples at most 500 requests. Primary evaluation always gives
each request weight one. Optional `od_weight` is supplied research evidence only;
the engine does not infer passenger demand or change the primary objective.

CSA chooses earliest arrival, then fewer transfers/boardings, then deterministic
itinerary order. Four boardings means at most three changes, regardless of the number
of adjacent movements on a vehicle. It keeps boarded-trip state even where alighting
is forbidden. `RouteResult` returns compressed same-vehicle legs, actual OSM walking
geometry, duration including waiting, and unchanged quality metadata. Unreachable
results have null arrival/duration, zero boardings, and no legs.

## Scenario semantics

All intervals are half open `[start_s, end_s)`. A movement crosses an interval when
its departure is before the interval end and its arrival is strictly after the interval
start; a zero-duration movement uses its departure event.

1. **Trip cancellation:** cancel each named full trip with at least one movement
   overlapping the interval. The trip is removed in full, not split at the window.
2. **Stop unavailable:** disallow pickup when departure at that stop is in the
   interval and drop-off when arrival is in the interval. A vehicle may pass and
   a previously boarded passenger may continue. OSM walking is still available.
3. **Corridor closure:** `CorridorSegment` identifies an adjacent transit movement
   (optionally both directions). Cancel a full trip when it crosses that segment
   during the interval. Geometry-to-segment selection belongs to the adapter;
   the engine makes no unobserved geographic inference.
4. **Additional delay:** add the specified delay at the first named-trip movement
   whose original snapshot departure lies in `[max(start_s, snapshot_s), end_s)`;
   propagate it to both departure/arrival of that movement and every following
   movement. Already departed movements are never rewritten. Multiple delays are
   additive against the original snapshot, independent of input ordering.

Delays are applied first. Cancellation/closure overlap and stop event restrictions
then use effective delayed times. Scenario order does not affect the result. Routing
is recomputed on the changed timetable so transfer failures and alternatives emerge
from the same rules. Unknown named trip/stop/segment references are rejected.

## Metrics and missed connections

Let N be the number of fixed requests, B the set with baseline duration <=3,600,
D the same set test after disruption, and R after recovery. Metrics use all N with
equal weight: lost=`|B \\ D|`; restored=`|(B \\ D) intersect R|`; restored fraction
is restored/lost, or null when lost=0. Reachable-count denominators are N. Reports
must not label this count as passenger reachability or passenger savings.

For each request, capped duration is `min(duration, 5,400)` for a reachable journey,
and 5,400 when unreachable. Totals include **all N**, including requests outside B.
These totals form the duration objective; null durations are not dropped. Raw route
duration remains available even above either horizon.

A missed connection is a baseline vehicle change where both adjoining effective
services and boarding/alighting events still exist, but the updated arrival plus
the actual baseline walk and one 300-second interchange allowance exceeds the
updated next departure. A cancellation or unavailable boarding event is recorded
as service unavailability, not a timing miss. Report both number of requests with
one or more misses (denominator N) and total missed changes. These are simulated
planned connections, not measured passenger misses.

## Recovery feasibility and objective

At most 12 supplied `RecoveryCandidate`s are considered. A candidate is one bus on
one existing paired `PatternPair`, activated no earlier than `snapshot_s + 600`,
committed for 7,200 seconds and costing exactly two bus-hours. Both directions use
actual existing GTFS pattern stops and timing offsets. A complete cycle comprises
outbound run, 300-second terminal turnaround, inbound run, then 300 seconds at the
starting terminal. Only cycles fully completed by duty end are generated. A pattern
with no fitting complete cycle is infeasible. Added trips are marked hypothetical.

Budgets are 0/2/4/8 bus-hours, allowing 0/1/2/4 buses. Each candidate can be used once.
A corridor closure that would cancel any added duty trip makes that duty infeasible;
a closed stop can still be passed under the boarding/alighting rule. Additional
delays and explicit trip cancellations target their named existing trips.

Plan comparison is lexicographic: maximize restored count; minimize total capped
90-minute duration across N; minimize bus-hours; then sorted candidate ids. Greedy
recomputes each marginal by rerouting the entire fixed request set, then explores
bounded one-/two-candidate swaps. The best evaluated feasible plan always includes
the no-intervention comparison and a simple policy selecting the eligible pair with
the most distinct disrupted source trips (this is service count, not demand).
`optimality_proven` is false for bounded search and true only for exhaustive search.
The exhaustive helper is limited to small fixtures; real query comparison to OTP
belongs to the integrator and is a later release gate.
OTP here means **OpenTripPlanner**, an independent routing engine.

## Data and release boundary

The preview is local. Public demo bundles must consist of three real recorded
mornings selected only after five complete weekday 06:00–12:00 Brisbane collections
and all release checks. No synthetic morning may substitute for a collection.
Collection completeness, source attribution, Translink contact/approval conditions,
OSM derivative-data licensing, OTP comparisons and credential scans are explicit
release gates owned by the integrator. No public release is authorized by these
engine contracts. Outputs are hypothetical predictions, not actual passenger savings.

## Version 1.1 approved extensions

```python
generate_recovery_candidates(snapshot: TimetableSnapshot,
                             requests: Sequence[JourneyRequest],
                             scenarios: Sequence[Scenario], *, limit: int = 12
                             ) -> tuple[RecoveryCandidate, ...]
```

This helper identifies journeys made slower or unreachable, uses their changed
corridor stops plus actual one-hop footpath associations, and retains existing bus
pairs touching at least two distinct anchors. It deduplicates physical/access
topology variants and prefers a template whose source departure is nearest T+600.
Ranking favors new lost-request coverage, new affected-request coverage, route
diversity and corridor coverage, with deterministic ties. It invents no OD weights
and returns no candidate when no existing relevant pair is supported. Both
directions require matching full bus source-trip topology in the original snapshot;
GTFS template timing provenance remains an adapter responsibility.

`RecoveryResult.considered_candidate_ids` and `infeasible_candidates` expose the
bounded candidate set and rejection reasons. Optional `on_progress` receives only
`RecoveryProgress(stage, evaluated_plan_count, considered_candidate_count,
feasible_candidate_count, evaluation_upper_bound)`. Stages are preparing, greedy,
swaps, exhaustive, completed. The upper bound is a calculation count, not an ETA.
`should_cancel` is checked at preparation/plan boundaries; exported
`RecoveryCancelled` acknowledges cancellation without returning a partial result.
The API handles that exception as cancelled and publishes no partial plan.

Evaluation/recovery requires at least one request. Routing departures cannot precede
snapshot_s. An optional `recovered_snapshot` is already transformed to its final
effective timetable and must retain the original metadata/provenance/quality.

OSM link eligibility uses actual path length plus both snap diagnostics <=600m,
while `length_m` and duration represent only actual OSM edges. Snap diagnostics must
be populated; they create no connector path. Unresolved station entrances/platforms
remain incomplete. Walking derivation/cache changes require a new method/version.

Primary OD selection uses source-active Fairfield/Annerley bus stops and source-active
South Bank/CBD bus/rail platforms with a deterministic auditable rule. Inactive
Fairfield platforms remain visible and their exclusion is a coverage limitation.
Requests retain equal primary weights. Scenario corridor targets are actual retained
adjacent movements, never a phantom unavailable service.

The approved local UI views are Replay, Scenarios, Recovery and Evidence, following
`docs/API.md`. Separate compact display/choices DTOs retain recorded vehicle/alert
receipt/event provenance, actual ids, gaps and quality without changing engine
inputs. Replay does not invent interpolation. Static mode uses lazy frames/choices,
versioned GTFS network geometry and precomputed completed runs; full timetables stay
local. `/v1/network?snapshot_id=id` selects the snapshot's exact GTFS digest;
`network/{gtfs_sha256}.geojson` and snapshot `network_url` preserve geometry versions.
No missing source is replaced by a current network under an older replay.
