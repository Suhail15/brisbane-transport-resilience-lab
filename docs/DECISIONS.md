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
    Windows CI on 1335dae found seven error-report path assertions using native
    backslashes. Root approves POSIX serialization of the reported relative
    pending path, retaining every corruption/recovery assertion and validation.
    The OS-specific filesystem path remains a Path; only its report form changes.
27. **Final morning protocol, coordinator approved 2026-10-22 (ARCH-007).**
    Six complete mornings now satisfy the five-window receipt-coverage requirement.
    Freeze `configs/morning-evaluation.v1.json` before computing morning policy
    outcomes: 9/13 October development, 19/20/21 October evaluation and 22 October
    reserve. Use cutoff 07:30:05 Brisbane and the existing fixed 20 OD pairs expanded
    into 100 requests. Preserve all four existing source-selected scenario rules,
    budgets 0/2/4/8, 128 swap evaluations, and stop-closure budget-two 0/300/600-second
    running-time sensitivity. A missing target is an explicit unsupported case,
    never a different target chosen after observing outcomes. Record all nulls.
    Replay frames sample every 15 minutes at five seconds after the quarter hour;
    label this sampling and do not interpolate source positions. Full immutable
    routing snapshots remain local. Labels must identify recorded morning inputs
    without claiming measured arrivals or equating receipt coverage with live entity
    freshness. Cache identical versioned geometry within a single bundle export.
    Private morning projections may be prepared before publisher approval; public
    preparation and publication still enforce every existing source/release gate.
28. **Exact public-site deployment boundary, coordinator approved 2026-10-22.**
    Final source/analysis verification runs locally against the private raw archive.
    GitHub Pages receives only the reviewed compact data and static site. An outer
    deployment ZIP contains `attestation.json`, `site-manifest.json` and `site/*`.
    Its SHA256 is pinned at authenticated workflow dispatch. The attestation binds
    the frozen candidate Git revision, original public data manifest digest, exact
    full-site manifest digest and all eleven actually passed local release gates.
    Deployment verification uses only the standard library: validate the supplied
    archive digest/revision, reject unsafe/duplicate/symlink/oversized ZIP entries,
    require the exact regular-file set and every data/site hash, then extract to a
    new directory. It does not claim to rerun private analytical checks on GitHub.
    Both ZIP and data projection are immutable after review. A candidate-preparation
    flag records generation history; only the separate all-gates attestation permits
    deployment. No credentials or private correspondence belong in the public ZIP.
    Root controls the workflow, final release evidence, public visibility and upload.
29. **Separate corridor-impact protocol, coordinator approved 2026-10-23.**
    User approved improving the demonstrated decision story. Preserve the released
    v1 engine, 54 results and original evaluation; hash their files before work.
    Freeze `configs/corridor-impact.v1.json` before confirmation policy runs.
    Use 9/13 October for development, 19/20/21 as explicitly reused replication
    dates and unused reserve 22 October for separate confirmation. Use the real
    source rail section Fairfield–Central, a hypothetical two-hour closure and
    exact source platform IDs for a 240-query interstation census. Score the old
    100 queries as separate controls under the primary plans; do not pool weights.
    No missing stop/path is repaired or excluded to manufacture a benefit.
    Keep the existing 60/90-minute metrics, walking/transfer assumptions and pure
    routing/recovery engine unchanged. For this study only, expand at most three
    nominal relevant source bus pairs at fixed 10/25/40/55-minute activations,
    twelve candidates maximum. Each is a hypothetical full two-hour bus duty.
    Freeze identities across running-time stresses. Add a nominal frequency-ranked
    same-pattern dispatch policy because a rail-only closure affects no source bus
    trips and the old affected-bus heuristic is unavailable. This ranks service
    supply, not passenger demand. All policies use identical inputs and requests.
    Report full signed impacts, within-60-minute losses/restoration, unchanged
    baseline-defined impacted cohort, separate controls and resource efficiency
    in query-minutes per bus-hour, with null zero-cost ratios. No monetary or
    achieved passenger savings claim is authorized. Publish all predeclared cells,
    including nulls, stress failures and inefficient plans, as a separate case
    study after independent reconciliation, reproduction and applicable release
    gates. The fixed example is Fairfield p2→Central p1 at cutoff, regardless of
    its recovery result. Source-defined missing Park Road and Roma Street's lack
    of rail platforms 1/2 are respected; source IDs are never guessed by name.
30. **Objective-preserving case-study scoring window, approved 2026-10-23.**
    Development no-action cells took 120/232 seconds and the first twelve-option
    recovery comparison remained CPU active for several minutes. No confirmation
    policy outcome has been inspected. Keep the exact frozen workload, scenario,
    candidates, objective, budgets and 128-swap bound; do not reduce the study.
    ARCH-013 reviewed a scoring-only timetable derivation: retain complete source
    trips if any movement departs at or before the latest primary departure plus
    5,400 seconds, plus complete source trips witnessing each selected bus pattern
    and every otherwise absent scenario segment. All original movements before
    the cutoff remain, full source references remain valid and the unchanged pure
    engine performs the search. Nonnegative movement/walk times imply every path
    arriving within ninety minutes is retained, so the sixty-minute restoration
    and ninety-minute capped-duration objective are identical for every subset.
    All rail-cancellation crossings occur before the scoring cutoff. Source
    feasibility, nominal relevance/frequency/cohort selection and published raw
    journey arrays still use full effective snapshots. Record the scoring version,
    cutoff, retained/witness trip IDs and derived snapshot hash. This is an exact
    computational shortcut for the stated objective, not a new operating model.
    Preserve the first complete full-timetable development two-hour result and
    old code/workspace, then stop old workers before editing their frozen code.
    Refreeze the unchanged analytical config with revised wrapper code, and prove
    exact selected-ID/objective parity for real development zero/two-hour cells
    and all subsets on a small boundary/witness fixture before confirmation.
    Published outputs and independent checks must always reconcile full routes.
31. **Station-access bus coverage correction, approved 2026-10-23.**
    Development review found that all 120 lost queries involved Roma Street.
    The original pilot retains buses serving the Fairfield/Annerley rectangle;
    it omits working busway alternatives at other selected stations. ARCH-014
    verified forty of those 120 queries have direct scheduled bus alternatives
    within sixty minutes using existing real walking links on both development
    dates. Do not report the incomplete-network losses as realistic outage harm.
    Before any confirmation policy outcome, supersede this proposed study with
    `configs/corridor-impact.v2.json`. Keep the same primary/control requests,
    closure, candidates/phases, budgets, stress and objective. Expand only source
    coverage: freeze 29 actual mapped-walk bus catchment stops at the eight fixed
    platforms, and all 103 bus shortnames source-active at those stops on either
    9/13 October, union the original pilot. This adds 84 names (156 total including
    original rail names), without a time/frequency/outcome filter. Retain complete
    active trips on later dates; missing/newly unsupported services remain visible.
    Record raw development GTFS/OSM/input identities, exact source-selected stop/
    route lists, full-trip counts and preserved walking witnesses. Optional pilot
    selection in existing normalizers must bind actual pilot bytes and isolate
    filtered caches so base-pilot data cannot masquerade as expanded coverage.
    Preserve the full initial proposal, interrupted workers and exact scoring-
    parity evidence. Freeze/review the corrected inputs and development outcomes
    before opening confirmation. Accept realistic small/null recovery benefits
    if the existing bus network already provides alternatives; never omit those
    alternatives, alter the incident, or tune thresholds to manufacture savings.
32. **Corrected study confirmation execution, approved 2026-10-24.**
    Independent reconciliation passed all twelve corrected development cells,
    with no missing cases/errors and all 530 original hashes preserved. Source
    protocol SHA256 is `dc47bd394e7e729d1d7f01a0105f8fbdf7eba0e56134d0e58259ffb144a28128`;
    development verification SHA256 is
    `701975a6d43719708d494c56d12a0d69077c862c9c396ed19d550128f3b7e3f6`.
    Authorize all 24 registered cells: separate confirmation on 22 October and
    explicitly reused replication on 19/20/21. Their policy outcomes were absent
    at authorization. Keep the frozen source coverage and every analytical rule.
    Nominal development keeps all 240 primary requests within sixty minutes;
    9 October's aggregate gains are outside the closure-delayed cohort, while
    13 October's modeled recovery offsets only a small share of added duration.
    Report that distinction and all simple-policy ties; no favorable retuning.
    Two independent date workers may run locally on disjoint files. Complete
    independent reconciliation and exact fresh-process offline recomputation
    before public export/release. A packaging-only projection may add the exact
    two docstring-only package initializers before pinning its final manifest;
    this fixes package isolation without changing calculation code or results.
