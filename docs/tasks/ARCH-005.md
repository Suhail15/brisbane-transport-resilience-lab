# ARCH-005

- Title: October 7 collector failure and bounded reliability review
- Status: corrected collector accepted and live core independently verified; bounded installer retry follow-up pending
- Owner: architecture agent
- Reviewer: root coordinator
- Task ID: ARCH-005

## Model and reasoning

Requested and coordinator-confirmed dispatch setting: `gpt-6.1-sol`, `max`
reasoning, including the explicitly requested final ARCH-005 review. No subagents
spawned. This agent has no separate backend model-identity introspection; actual
dispatch verification is supplied by the coordinator.

## Approved specification and decisions

The coordinator owns approval and changes to `docs/CONTRACTS.md` and
`docs/DECISIONS.md`. On 2026-10-07 it approved decision25 and the operational
recording margin in `docs/CONTRACTS.md`, then dispatched `docs/tasks/INT-006.md`.
Those approved shared documents were independently read after the recommendation.
This task is a read-only implementation/data audit, not authority to change those
shared files.

Preserve immutable source bytes/receipts, actual UTC received times, matching GTFS
identities, received-time replay cutoffs, detected-time gap availability, existing
stale fallback and all analytical engine/schema policies. October 7 remains
incomplete. Do not fabricate catch-up receipts, rewrite existing recordings, or
widen the 35-second TripUpdates/VehiclePositions and 65-second Alerts limits.

Recommended bounded scope accepted by the coordinator:

- Dispatch TripUpdates/VehiclePositions nominally every 25 seconds and Alerts every
  55 seconds. Advance fixed phase deadlines from their previous slot rather than
  `dispatch + interval`; skip missed slots and keep at most one request per feed in
  flight. Reset phases for a new recording session/day. After the first independent
  review, the coordinator additionally approved minimum same-feed dispatch spacing
  of 20/20/50 seconds (`poll interval - 5`), consuming adjacent phase slots without
  dispatch when that spacing is unmet. Normal 500 ms loop lateness retains phase.
  Real delay remains visible.
- Activate idle-sleep protection and GTFS preparation on weekdays from 05:50 to
  12:00 Brisbane. Clip off-window waits to upcoming preparation/recording boundaries;
  acquire the relevant assertion before waiting across a boundary. Keep RT captures
  confined to the existing 06:00-12:00 window unless explicit development force is
  used. An assertion cannot wake an already sleeping machine.
- Move schedule downloading to one dedicated worker. Prepare one fresh schedule for
  each upcoming recording date, starting at/after 05:50, with bounded retry timing
  after failure. Continue RT polling with the last genuinely available GTFS receipt
  while preparation runs. Do not backdate source availability. The integrated
  coordinator-approved association
  is the latest valid archived schedule available at the real feed receipt time;
  a schedule received after that receipt cannot supply its digest. Missing/stale
  schedule quality stays explicit.
- Preserve the existing independent outbox worker. Record actual dispatch policy,
  attempt count and elapsed HTTP timing on new receipts and in runtime status;
  expose recent receipt gaps as operational diagnostics without altering coverage.
- Retain `AnalysisAssumptions` literal cadence values 30/30/60 if the coordinator
  explicitly documents them as nominal completeness-policy targets. The actual new
  collector 25/25/55 policy must be recorded separately; neither historical metadata
  nor frozen engine-code hashes are rewritten.

The [Translink open-data page](https://translink.com.au/about-translink/open-data)
and [linked terms](https://translink.com.au/about-translink/open-data/terms-and-conditions),
independently read on 2026-10-07, do not specify a client polling minimum or rate.
This observation is not a guarantee of future service availability or terms.
[GTFS Realtime best practices](https://gtfs.org/documentation/realtime/realtime-best-practices/)
recommend producer refresh at least every 30 seconds; that is not a consumer minimum
polling interval. Public-release/publisher-approval gates remain separate.

## Required inputs and dependencies

Read `AGENTS.md`, `docs/CONTRACTS.md`, `docs/DECISIONS.md`, `docs/COLLECTION.md`,
`docs/tasks/ARCH-004.md` and `docs/HANDOFF_TEMPLATE.md`; inspect
`services/resilience/pipeline/{collector,recorder_runtime,archive,coverage}.py`,
`services/resilience/db.py`, `scripts/install_collector.py`, and
`tests/integration/test_collector_runtime.py`.

Evidence is the ignored `data/runtime/archive.sqlite` receipt journal,
`data/runtime/scheduled-collector.log` and
`data/runtime/scheduled-collector-error.log`. SQL inspection used an explicitly
read-only connection. No personal contact/email files were read. The coordinator
owns implementation dispatch, review, live restart, OS wake configuration, final
tests, commit/push/CI and later recording-window acceptance.

## Files owned

- `docs/tasks/ARCH-005.md`

All implementation, tests, other documentation, recorded sources and runtime state
are read-only to this task.

## Expected output

An independently evidenced failure explanation, narrow recommended changes with
preserved contracts, bounded meaningful tests and deployment checks; a final
independent implementation review when the coordinator supplies the integrated
change. No guarantee against network outages, lid closure, power loss or upstream
failure is justified.

## Acceptance checks

- **Passed independently: full October 7 receipt accounting.** The Brisbane window
  is `2026-10-06T20:00:00Z` through `2026-10-07T02:00:00Z`. Read-only SQL found
  712 valid FULL_DATASET TripUpdates, 712 VehiclePositions and 358 Alerts, excluding
  development captures. With the unchanged 06:00/12:00 edge comparisons,
  TripUpdates has exactly one over-limit interval; other feeds have none.
- **Passed independently: anomalous timing decomposition.** TripUpdates receipt
  `2026-10-06T23:55:48.872818Z` followed by
  `2026-10-06T23:56:25.855657Z` gives exactly 36.982839 seconds (reported coverage
  rounds to 36.983). Their recorded request starts are
  `23:55:48.598644Z` and `23:56:18.789101Z`, 30.190457 seconds apart. Request-to-
  receipt elapsed time rises from 0.274174 to 7.066556 seconds: the 6.792382-second
  increase plus the request interval exactly explains the failed receipt gap.
- **Passed independently: simultaneous feed comparison.** VehiclePositions at the
  same dispatch rises from 0.118407 to 4.545469 seconds request-to-receipt time;
  its receipt interval is 34.617362 seconds and still passes 35 seconds. This shows
  delay after dispatch, rather than a missing 30-second poll, as the immediate
  TripUpdates failure trigger. Existing receipts lack attempt counts, DNS/TLS or
  transport-stage measurements, so provider latency, network delay, a short retry
  and OS scheduling within the HTTP task cannot be distinguished conclusively.
  The current worker retries up to three times with one- and two-second backoffs;
  its HTTP client has a 20-second timeout. A full timeout/retry sequence can exceed
  the receipt-gap budget, so shorter normal polling reduces risk without guaranteeing
  coverage during failures. Only ultimate failure is logged as a failed fetch.
- **Passed independently: cumulative scheduler drift.** For all 711 adjacent
  TripUpdates request starts, minimum/median/maximum dispatch intervals are
  30.001054/30.306329/30.692797 seconds. Elapsed time exceeds 711 nominal 30-second
  intervals by 214.609667 seconds. `collector.py` uses
  `max(previous_due + cadence, dispatch + cadence)`; an overdue dispatch selects
  the latter and compounds loop lateness. Fixed phase timing fixes that observed
  drift, but a nominal 30-second request with the observed roughly 6.8-second
  latency increase could still exceed 35 seconds. The proposed 25-second margin
  addresses this event without changing the acceptance threshold.
- **Passed independently: first/last edges and schedule boundary.** The October 7
  schedule receipt is `2026-10-06T20:00:24.858698Z`; first RT request starts near
  `20:00:27.34Z`. First TripUpdates/VehiclePositions/Alerts receipts are
  27.500791/27.448648/27.448456 seconds after 06:00. Their final edge gaps are
  26.725651/27.849082/40.126197 seconds. All edges pass, but the first RT edges have
  little remaining margin. Schedule refresh is synchronous before RT dispatch and
  uses a 120-second HTTP timeout, creating a verified startup design risk. It is not
  the cause of the later 09:56 anomaly: no schedule refresh occurred near it.
- **Passed independently: background/log diagnostics.** October 7 has no recorded
  gap-journal entries despite the failed coverage interval. The collector stdout
  contains all 1,782 RT receipts, no failed/traceback/outbox error markers, and the
  error log is empty. This does not prove no short HTTP retry occurred. Outbox
  delivery already runs in a distinct single-worker executor and does not directly
  block the polling loop. `archive.latest('GTFS')` is an indexed GTFS-only query
  with three current receipts, not an observed full RT archive scan or established
  performance bottleneck; caching it is an optional simplification.
- **Passed independently: sleep protection boundary review.** The existing
  `WindowAwake` is set only after entering the 06:00-12:00 loop state. Off-window
  sleep can cross 06:00 by up to 30 seconds, and there is no OS wake event in this
  implementation. Neither a pre-window assertion nor a LaunchAgent can guarantee
  waking an already sleeping Mac. This is a separate prospective reliability risk,
  not an observed explanation for October 7's 09:56 receipt interval.
- **Initial proposed deterministic checklist; completed scope recorded below.** Simulate a
  7.066556-second response delay following a 0.274174-second response with nominal
  25-second phase timing and verify actual receipt coverage remains within 35
  seconds. Inject repeated 0.5-second loop lateness and verify it does not accumulate
  across dispatches; skip missed slots without overlapping same-feed requests or
  manufacturing receipts. Hold schedule/outbox work and one feed's retries pending
  while verifying healthy feeds continue. Check weekday 05:50/06:00/12:00, weekend,
  force, startup/restart and clock discontinuity behavior. Verify bounded refresh
  retry timing, schedule digest availability at dispatch, actual attempt/elapsed/
  policy metadata, and unchanged strict coverage/replay filters.
- **Proposed deployment checks; coordinator-owned.** After tests pass, restart the
  real LaunchAgent outside the recording window; verify one collector PID and lock,
  fresh heartbeat with approved policy, no error output and proper prewarm status.
  A separate bounded development run may verify 25/55 dispatch intervals and
  truthful development labels; it cannot count as a morning window. Verify any
  approved wake events through the OS schedule, then independently inspect the next
  actual six-hour morning's receipts and coverage. Preserve failed history.
- **Passed independently: first integrated focused suite.** On 2026-10-07 the
  runtime/timing/wake suite passed 11 tests in 0.09 seconds. It covers the lock,
  timezone/weekdays, repeated phase jitter, pending-worker independence, warmup/noon
  drain, a new service date, true fetch metadata/latency example, failed/quarantined
  sources, and basic bounded wake planning/installation guards. Its initial restart
  case asserted an incorrect zero-length startup gap, and it did not catch rapid
  successful dispatches or the wake matching/timezone defects below. Passing this
  set is not final integrated acceptance.
- **Passed independently: existing recording preservation.** Compared every entry
  in `data/runtime/collector-before-reliability-fix.json` against the read-only live
  journal, raw receipt JSON files and decompressed content-addressed payloads.
  All 2,338 canonical compact/sorted metadata hashes, 2,338 receipt-file hashes
  and 2,338 payload hashes matched; 2,330 distinct payloads were verified, with
  zero missing/changed/new real records. The comparison does not require rewriting
  archived data. `contracts.py`, engine modules, `archive.py`, `coverage.py` and
  `docs/RELEASE.md` have no Git diff.
- **Passed independently: current release prerequisite remains failed.** The
  unchanged coverage function was run through a read-only archive adapter. It still
  reports 0/5 complete windows. October 7 retains 712/712/358 RT receipts and only
  the same 36.983-second TripUpdates failure; strict limits remain 35/35/65.
  `data/runtime/status-2026-10-07.json` also records zero complete windows. A missing
  weekday is not turned into a synthetic recorded window.
- **Passed independently: actual SIGTERM signal and worker drain in an isolated
  fixture.** A temporary archive, synthetic HTTP/schedule/outbox callbacks and real
  worker executors were used in a separate Python process. Its first scheduler tick
  dispatched three feeds, then an actual SIGTERM invoked the installed stop handler.
  All three valid feed responses and one schedule receipt finished; no second tick
  dispatched more work. Parsed aware receipt times followed request starts,
  `collector-v2` metadata was retained, the previous signal handler was restored,
  the awake assertion was released and the archive lock could be reacquired. No
  external HTTP or real archive mutation occurred. This validates collector signal
  handling, not the OS service's complete timeout behavior under long outages.
- **Confirmed required dispatch defect independently.** A temporary-archive loop
  initialized at 06:00:24.9 dispatched immediately; completing its request at
  06:00:24.95 and ticking at 06:00:25 dispatched the same feed again after 0.1
  seconds. One-in-flight protection alone does not prevent that compressed pair.
  Large delayed ticks near a phase have the same issue. The coordinator approved
  the 20/20/50 spacing guard above and assigned its implementation/regression.
- **Confirmed required startup-diagnostic correction by code review; coordinator
  also reproduced it.** Startup queries can select yesterday's receipt, compare its
  age with the current clock, and then journal `[06:00,06:00]` at exact 06:00. That
  is not a missing preceding window interval. Use the previous valid receipt,
  clamp the start to `max(window start, previous valid receipt)`, and record only
  when elapsed in-window time exceeds 35 seconds. Keep a real mid-window startup
  gap test; remove the fixture's requirement for a zero-length gap.
- **Accepted narrow service-timeout correction in source.** The coordinator
  reported the existing LaunchAgent exit timeout as five seconds, shorter than
  ordinary HTTP/retry/schedule drain budgets. It approved and wrote installer
  `ExitTimeOut=300`; that requested source value was read back independently.
  The deployment follow-up below observes a different effective reported value,
  so the requested 300 seconds cannot be claimed as an available shutdown budget.
  HTTP timeouts apply to network phases and existing outbox initialization lacks
  an explicit connection timeout; graceful completion under every stall is not
  guaranteed.
- **Required wake-helper corrections, coordinator-approved.** Existing-event
  detection combines an owner anywhere in the whole listing with a date anywhere
  in the listing; an unrelated event can suppress the proposed owned wake. Root
  also identified two- versus four-digit year matching. Match owner, wake kind and
  normalized date/time on the same event. The helper currently prefers process
  `TZ` to `/etc/localtime`, allowing a Brisbane process timezone to authorize
  installation while the actual Mac system timezone differs. Determine the actual
  OS timezone independently of `TZ` and fail closed if a rule-aware OS timezone
  cannot be obtained; a current fixed offset cannot prove future DST compatibility.
  Add bounded regression fixtures, preserving unrelated schedules and admin gating.
- **Final corrected implementation accepted independently, 2026-10-07.** Read the
  corrected collector/schedule helper, wake helper/tests, installer and current
  decision25/contracts and INT-006/QA-001 handoffs. The required defects identified
  in the first review above are resolved within the approved narrow scope. No
  required implementation blocker remains; live deployment is separate.
- **Passed independently: final focused suite.** Runtime/timing/wake tests passed
  **13/13 in 0.12 seconds**, with no skips. Ordinary 500 ms lateness retains phase;
  one pending feed, schedule or outbox does not pause healthy feeds. The new rapid-
  success restart regression suppresses the 06:00:25 request after a 06:00:24.9
  start and permits the next 06:00:50 phase. The corrected startup fixture asserts
  no exact-06:00 false gap and an actual 60-second gap for a 06:01 restart. Existing
  true-receipt, 7.066556-second latency, retry failure, malformed-feed, noon-drain,
  full-window and administrative guard checks remain green.
- **Passed independently: all-feed spacing supplement.** Isolated temporary-
  archive cases for TripUpdates, VehiclePositions and Alerts each completed a
  request just before the next fixed phase. All three suppressed the compressed
  adjacent phase, dispatched at the following original phase, and exposed the
  actual minimum spacing 20/20/50 seconds in heartbeat metadata. No catch-up or
  overlapping request was generated. Consuming a phase can leave a real gap after
  severe scheduler delay; the coverage gate continues to expose it honestly.
- **Passed independently: received-time GTFS association supplement.** A temporary
  archive contained an older schedule and a schedule whose receipt time followed
  the first feed response. Actual `fetch_feed` calls with a synthetic client selected
  the older digest for the earlier response, then the new already-available digest
  for the later response. The first receipt remained byte/record immutable. No
  future/pending timetable was attached to an earlier received cutoff.
- **Passed independently: corrected wake helper.** The final fixtures validate
  the five future weekday dates, `wake`-only commands, exact owner/kind/date/time
  matching on one event, two/four-digit year normalization, and preservation of
  unrelated or different-kind events without any repeat/cancel command. A Sydney
  OS timezone file with a Brisbane process `TZ` remains incompatible; a missing
  OS timezone file raises an error before installation. Source inspection confirms
  `/etc/localtime` is authoritative and there is no fixed-offset/process-`TZ`
  authorization fallback. No privileged command was executed by this review.
- **Passed independently: final archive/frozen-policy guard.** Repeated the full
  prechange audit comparison after the corrections: **2,338/2,338** canonical
  metadata, receipt-file and payload hashes match; 2,330 distinct payloads checked,
  zero changes/missing records/new real receipts. Frozen schema, engine, archive,
  coverage and release documentation still have no Git diff. `git diff --check`
  passed. The preserved data remains 0/5 complete windows; October 7's failure
  cannot become a pass through this collector change.
- **Coordinator-reported final context, not independently rerun:** full Python
  suite passed 85 checks with one optional live-PostGIS skip and one unrelated
  FastAPI deprecation warning. A 58-second real-network capture in a separate
  development archive observed the actual 25/55-second policy. Root reports the
  Mac's actual OS timezone as Australia/Brisbane and mains power present. These
  bounded checks do not constitute a new full six-hour morning. Collector reload,
  installed-definition read-back, administrator wake result, private commit/push
  and matching CI remain coordinator-owned.
- **Deployment follow-up, independently verified 2026-10-07.** The coordinator
  reported a successful bootout followed by immediate bootstrap exit 5 (I/O error),
  then one successful direct bootstrap of the same valid, user-owned plist.
  Read-only `launchctl print` and process inspection confirm exactly one collector,
  PID **38229**, running from the intended virtual environment and repository.
  Heartbeat `collector-v2` exposes 25/25/55-second targets and 20/20/50-second
  minimum spacing, force false and no in-flight work outside the morning window.
  At `2026-10-07T02:59:37.295346Z`, heartbeat age was 1.036609 seconds. The error
  log is empty. The newly saved `data/runtime/coverage-2026-10-07.json` retains
  0/5 complete windows and the same 36.983-second October 7 TripUpdates gap.
- **Deployment timeout discrepancy, independently verified.** Installed plist
  has requested `ExitTimeOut=300`, correct label/program and owner UID 501, while
  the running job's `launchctl print` reports **exit timeout = 60**. Treat 60 as
  the observed reported OS stop allowance, not 300. The native
  `/usr/share/man/man5/launchd.plist.5` describes the SIGTERM-to-SIGKILL setting and
  a system-defined default, with no stated upper limit. The reason for this
  requested/reported discrepancy has not been established; do not invent a
  documented cap or change HTTP timeouts merely to match it. Long active retries,
  schedule requests or database work may outlast that stop allowance. This is a
  shutdown limitation, not a present polling failure or a new next-morning blocker
  while the verified collector remains running.
- **Approved minimal reload-race follow-up recommendation.** The observed recovery
  is consistent with transient service teardown/registration timing, but exit 5
  alone does not prove its cause. Capture bootstrap's result; only for exit 5,
  wait 0.5 seconds and retry exactly once against the same user GUI domain and
  owned plist. Propagate any other or final error with captured diagnostics; two
  failures require escalation, not additional retries. No sudo, global power
  changes, unrelated labels or larger startup refactor. Verify one actual reload
  outside the recording window, exactly one PID, fresh policy heartbeat and empty
  error log. Installer implementation and that live verification are separately
  assigned/coordinator-owned. The currently healthy job does not need another
  reload merely to investigate the stop-timeout discrepancy.

## Escalation issues

- The first review's required dispatch-spacing, non-fictitious startup-gap and
  wake matching/timezone defects are resolved and independently accepted. This
  task edited only its handoff. No required code blocker remains within this
  bounded correction; root owns subsequent deployment and whole-project acceptance.
- The proposed shorter intervals increase nominal requests by 20% for TripUpdates/
  VehiclePositions and about 9.1% for Alerts. At most one in-flight request per feed
  bounds load; upstream HTTP failures or new rate restrictions require reconsideration.
- Warmup prepares a schedule before the window but cannot compensate for an
  already sleeping/offline machine, failed download, changed schedule content,
  power loss or closed lid. Schedule polling must remain bounded after failure.
- OS wake scheduling is coordinator-owned and may require administrative user
  action. Do not substitute global battery/idle settings or represent proposed wake
  events as installed without current OS evidence.
- Repeated implementation/test failure, required changes to replay/analysis
  semantics, or an upstream restriction must be escalated with observed evidence.
- Corrected implementation acceptance is complete. Live deployed-definition and
  core operation are now independently verified. The bounded installer retry fix
  and one corresponding reload check remain pending; administrator wake evidence,
  private commit/push and matching CI remain coordinator-owned. No wake
  installation, service reload, commit/push, visibility change or publication was
  performed by this review.
