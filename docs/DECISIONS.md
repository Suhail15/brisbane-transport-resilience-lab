# Approved architecture decisions

Status: version 1.1 interfaces frozen for local implementation, 2026-10-02.
Owner: ARCH-001, GPT-6.1 Sol, reasoning max.

1. Python/Pydantic 2 interchange models live in `resilience.contracts`; engine code
   has no database, broker, network or web-framework dependency. FastAPI, PostGIS,
   Redpanda and recording adapters can evolve independently around these models.
2. Snapshot provenance is bounded by local receipt time. Feed event time is retained
   independently. Historical real-time playback never consumes a later download.
3. Service-day seconds retain GTFS values >=24h; full contiguous relevant trips are
   preserved, including stops outside the map pilot. Calendar exceptions override
   weekly calendar selection.
4. Routing uses an auditable connection scan with per-boarded-trip state and at most
   four boardings. Earliest arrival precedes fewer changes in tie resolution.
5. Interchange allowance is 300 seconds **in addition to** actual OSM walking time,
   once per vehicle change. Same-vehicle continuation is free of this allowance.
   Walking links are complete directed OSM paths <=600m at 1.2m/s; no straight-line
   substitutions or chained stop footpaths are inferred.
   Stop/platform snapping is limited to 30m and logged as a diagnostic, without
   fabricated connectors. Unresolved platform/entrance paths remain incomplete.
6. Scenarios are reproducible pure transformations; additional future delays apply
   first, then other restrictions use effective event times. Interval ends are
   exclusive. Stop closure permits passing; corridor closure cancels the full trip.
7. Primary OD requests are equally weighted, fixed across scenarios, <=500, at five
   quarter-hour departures covering the next hour including its endpoint. Demand
   weights are never fabricated and do not change primary reporting.
8. Reachability is <=60 minutes; lost and restored are relative to baseline
   reachability. The secondary objective includes all requests with duration capped
   at 90 minutes, substituting that cap for unreachable journeys.
9. One recovery candidate is one existing paired bus pattern and one two-hour bus
   duty costing two bus-hours. Activation lead time is 10 minutes; both terminal
   turns are five minutes; only complete cycles are useful. Up to 12 candidates,
   budgets 0/2/4/8, at most four buses. No inferred fleet inventory is claimed.
10. Bounded search reports the best evaluated plan and its comparison to no action
    and the busiest affected service pattern; it does not claim global optimality.
    Small fixtures use exhaustive search and a separate independently calculated
    oracle. Real source query checks against OpenTripPlanner (OTP) are a release gate.
11. Branding is independent. Real source facts, feed-quality limits, OSM derivative
    data and hypothetical intervention predictions are clearly labelled. Five
    complete real weekday morning recordings, three real bundle mornings and all
    validation/licensing/contact/approval gates are required before public release.
12. Recovery candidates are relevant to source-affected journey corridors, with
    actual one-hop footpath association, topology deduplication, near-query source
    timing templates and deterministic coverage/route diversity. Generic frequency
    ranking alone does not satisfy relevance. No supported pair yields zero candidates.
13. Optional pure-engine progress/cancellation hooks expose stages/counts only;
    cancellation at preparation/plan boundaries raises `RecoveryCancelled` and
    never returns a partial result.
14. Active source-supported primary OD stops are used within the unchanged pilot;
    inactive Fairfield platforms remain visible as a schedule limitation. No
    inferred train operation or fictitious disruption corridor is introduced.
15. Display/choices are separate compact DTOs. Replay geometry uses the exact
    snapshot GTFS version and recorded positions without interpolation. Static
    bundles use lazy frames/choices and completed runs; full timetable inputs are local.
16. OpenTripPlanner 2.10 independent checks use separate build/save and load/serve
    processes after source inspection found combined startup can map an empty
    routing layer before graph construction. Actual query verification is required.
