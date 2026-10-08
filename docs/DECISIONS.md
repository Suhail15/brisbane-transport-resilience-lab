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
17. Every new analysis run binds canonical complete input, request/scenario/candidate
    hashes, immutable snapshot/source references, implemented engine/code versions,
    search policy and literal assumptions. Legacy runs are recomputed rather than
    relabelled with present code. Metrics remain in the existing result structure.
18. The bounded experiment persists 20 source-selected pairs and 100 equal requests
    across dates. Missing service remains unreachable. Bus running-time sensitivity
    uses 0/300/600s proportional directional scaling, future incumbent suffixes,
    unchanged activation/turns and regenerated complete duties for every policy.
    Candidate ids are frozen from the nominal case; raw snapshots are not rewritten.
19. Independent reference acceptance requires exact matched transit paths and
    source-specific explanations for access differences, with raw disagreement
    retained. Six distinct exact bus/rail checks and zero unexplained cases meet
    the bounded schedule-core check; walking coverage remains incomplete.
20. Separate reviewed reproduction assets preserve selected full normalized inputs,
    immutable versioned runs, source hashes and exact objective/metric reproduction.
    Compact browser bundles remain lazy; OSM-derived walking data is separately
    available under ODbL. Publication remains subject to all existing release gates.
21. ARCH-002 accepts the seven final local 100-request budget/sensitivity results
    and measured journey latency at their documented afternoon scope. Public export
    must verify immutable finals, complete input/derived bytes and hashed evidence
    scope rather than trusting mutable result copies or boolean/reference strings.
22. Monthly ticketing is a separate sparse-coverage proxy with exact direct-route/
    stop-order/direction evidence, source time bins and conserved pair/bin weights.
    It never changes primary requests or search; unknown mappings remain unknown.
    Its complete approved rules and next-packet checks are in docs/tasks/ARCH-002.md.
23. Route196's OD operator is bound through a narrowly reviewed official-source
    crosswalk, preserving GTFS's umbrella Translink agency. Council's route196 listing
    plus Translink's Transport for Brisbane/Council identification support this
    combined-source inference. Opaque trip-id prefixes and agency-name equality are
    insufficient; other routes remain unproved. Evidence is in ARCH-003.
24. Local public-candidate preparation and final release acceptance are separate.
    Preparation enforces recorded-morning/source/licence eligibility and integrity;
    final acceptance verifies static/CI evidence and the exact candidate manifest.
    Full authorization remains false until all gates pass. Generation cannot depend
    on acceptance of bytes it has not yet produced, and no preparation step publishes.
25. **Collector reliability correction, coordinator approved 2026-10-07 (ARCH-005 / INT-006).**
    The nominal recording/coverage policy stays 30 seconds for TripUpdates and
    VehiclePositions, 60 seconds for Alerts, with the existing strict receipt-gap
    limits of 35/35/65 seconds. The operational collector dispatches every 25/25/55
    seconds to provide latency headroom. Frozen analysis assumption cadence fields
    describe the nominal coverage policy; each new source receipt and heartbeat
    records the actual dispatch policy separately. Receipt times remain the replay
    authority. This does not change source freshness rules or retrospectively
    qualify a failed window.
    Fixed-phase monotonic deadlines skip elapsed slots without burst catch-up and
    permit only one in-flight request per feed. Completed HTTP responses retain
    their real receipt times, including late/out-of-order responses. Record actual
    request attempts and elapsed time; do not fabricate success after retry failure.
    Weekday preparation begins at 05:50 Brisbane: obtain the idle-sleep assertion
    while awake and refresh GTFS on a separate worker. Schedule refreshes and the
    existing outbox worker cannot block other feeds' dispatch. A pending new
    schedule never supplies its digest to an earlier receipt. Warmup requests are
    not qualifying morning feed captures. The collector waits precisely for the
    06:00 boundary and drains already dispatched requests after 12:00 without
    creating new qualifying requests outside the recording window.
    Live heartbeat diagnostics and a post-window coverage report expose remaining
    failures; they cannot override the unchanged release gate. Idle protection
    cannot wake a sleeping machine or defeat closed-lid/manual sleep. Prepare
    bounded, owned weekday 05:50 wake events separately; installation requires
    macOS administrator authorization. Keep global power settings and existing
    user wake/sleep schedules intact. No paid/cloud deployment is authorized here.
    The collector's own LaunchAgent gets a 300-second exit timeout so its graceful
    SIGTERM handler can drain ordinary feed/schedule requests before restart. This
    is shutdown headroom, not a bound on all possible network/database stalls.
    Independent review found a restart/missed-slot dispatch immediately before the
    next fixed phase could otherwise yield a compressed request pair. Enforce
    minimum actual per-feed dispatch spacing of interval minus five seconds
    (20/20/50 seconds); consume too-close phase slots without submitting requests.
    Ordinary half-second scheduler jitter retains the fixed phase. Startup gap
    journaling measures only missing time inside the current morning, from the
    later of 06:00 and the prior valid receipt, and never records a zero-length
    missing-window claim at an exact 06:00 restart.
    Evidence: on 7 October a 30.190457-second dispatch interval plus HTTP/receipt
    latency growth from 0.274174 to 7.066556 seconds produced a 36.982839-second
    gap. All-day dispatch intervals averaged 30.301842 seconds. The first morning
    feed receipt followed a blocking timetable refresh at 06:00:27.500791.
    Translink's official open-data page and linked terms were reviewed on 7 October;
    neither specifies a client polling minimum/rate. GTFS best-practice 30-second
    refresh guidance concerns feed producers, and is not a consumer rate limit.
    The modest increase is bounded to the configured weekday window and preserves
    private archiving. Network/power/upstream failures can still prevent a pass.
26. **Further collection resilience, coordinator approved 2026-10-08 (ARCH-006 / INT-007 / QA-003).**
    Operating policy `collector-v3` uses fixed phases of 15/15/45 seconds with
    minimum submissions spaced 10/10/40 seconds apart. Keep one in-flight task per
    feed through archive completion, skip missed slots and preserve all successful
    responses, including slow ones and those received after noon. Keep existing
    20-second network phase timeouts and the single HTTP retry owner (at most three
    attempts); no quality-driven cancellation, invented receipts or overlapping
    duplicate requests. Nominal analysis fields remain 30/30/60, strict receipt-gap
    limits remain 35/35/65, and five complete six-hour mornings remain required.
    Independent review measured October 8 task-start intervals 28.310826/28.397149
    seconds and response-latency growth 7.641214/7.455599, giving the actual
    35.952040/35.852748 gaps. With the same measured differences, the shorter
    cadence gives approximately 25.952/25.853-second counterfactual gaps. This is
    engineering headroom, not a historical or prospective coverage pass.
    Configure the shared HTTP client with 90-second keepalive expiry, three total
    and three idle connections, and no extra transport retry layer. The installed
    client's default expiry was five seconds. Published Translink open-data terms
    reviewed on October 8 contain no client polling minimum; this is not unlimited
    capacity authorization. Normal request volume becomes 3,360 per six-hour
    window, approximately 58.4% above the previous 2,121. Respect explicit provider
    Retry-After signals if present; any resulting missing coverage remains visible.
    Sources: https://translink.com.au/about-translink/open-data/terms-and-conditions
    and https://www.python-httpx.org/advanced/resource-limits/.
    Move coalesced heartbeat writes and retained diagnostic logs/gaps to one
    separate telemetry worker. Capture a gap's detection time in the observer and
    pass it through optional `Archive.gap(..., detected_at=...)`; queue delay must
    not rewrite replay availability. Add actual phase/submission/task/HTTP timing;
    return persistence-completion durations in health/logs, never mutate a receipt.
    Bound outbox-only Postgres connection/statement/lock waits and back off failed
    delivery. Keep failed source references durable and feed archive writes intact.
    Root ratifies batches of at most 25 references, five-second success pacing,
    the existing within-batch remaining alias and total unsent backlog reporting.
    Smaller delivery turns allow health/backoff checkpoints; they do not cap the
    durable backlog or guarantee drain within the observed shutdown allowance.
    Explicit narrow archive ownership exception: before journal commit, save a
    pending-capture envelope beside the immutable content-addressed object. Clear
    it only after journal/outbox and receipt-file completion. Recover envelopes
    only on collector startup under the recorder lock, without upstream requests;
    validate identity, timestamp, safe relative object path and payload hash. An
    already committed journal row remains authoritative. Preserve corrupt pending
    evidence and report errors; never rewrite an original receipt or payload to
    hide corruption. This addresses process interruption between durable stages,
    not bytes never durably stored or every hardware/power failure.
    The collector's own macOS job uses Standard rather than Background process
    classification; this does not guarantee scheduling priority. Keep existing
    global power settings. Check the collector-owned sleep assertion's health and
    retry a dead assertion process without suppressing errors. Preserve the actual
    reported shutdown allowance and expose disk/worker/telemetry health. Extend
    only individually owned wake events needed for five future weekday mornings;
    native administrator authentication is still required for additional events.
    Final review approves two narrow correctness guards: recheck actual time
    immediately before each feed submission so a tick crossing noon cannot start
    new normal-window work; and validate any non-null pending timetable digest
    against a valid archived GTFS receipt available by the original receipt time.
    A missing digest remains unknown. Previously dispatched work still drains.
    Full-suite verification exposed concurrent publication of the same capture
    racing with pending-envelope removal. Serialize only identical archive-root /
    record-ID publications using bounded process-local keyed lock ownership and
    clear completed envelopes idempotently. Different captures remain parallel;
    object/journal/receipt durability and existing immutable rows remain intact.
    Freeze all 4,460 pre-change rows/receipt files and 4,430 payloads by hashes.
    Verify both recorded timing failures, jitter, blocked workers/storage/broker/
    telemetry, HTTP retries, slow successful bodies, process-crash recovery,
    original gap detection cutoffs, window/restart/calendar behaviour, live
    development captures, clean cross-platform CI and installed service settings.
    Public release remains gated. Network, shared-storage, lid and power outages
    can still invalidate a morning; no future pass is claimed.
