# Recording and replay

Run `python scripts/start.py collect` continuously. The recorder waits outside
weekdays 06:00–12:00 Australia/Brisbane. Operational policy `collector-v2` dispatches
TripUpdates and VehiclePositions every 25 seconds and Alerts every 55 seconds.
Weekday preparation begins at 05:50: acquire the idle-sleep assertion while awake
and refresh GTFS on a separate worker. Feed dispatch waits for 06:00; timetable
refresh and archive-reference delivery cannot hold up another feed. A timetable
refresh failure records a gap and retries after five minutes. The latest already
archived timetable is the fallback; a pending download never supplies a digest.
`--force` permits development recording outside the window; each such receipt is
explicitly marked development_capture and cannot satisfy a morning collection.

The first acquired sources are Friday 2026-10-02 afternoon. The earliest prospective
five complete morning windows are Monday 2026-10-05 through Friday 2026-10-09.
These planned dates do not establish completed coverage. Keep the laptop awake,
connected and recorder running. A sleeping laptop creates an auditable gap; waking
up does not manufacture missing data.

Original bytes are compressed in immutable content-addressed objects under
`data/raw/objects`. Each receipt has receipt time, provider event time where supplied,
SHA256, URL, GTFS digest, HTTP/request metadata and protobuf validation status.
Repeated content deduplicates objects while distinct receipt times remain distinct.
The local SQLite WAL journal is a durable reference outbox; PostGIS mirrors receipt
metadata and Redpanda topic `resilience.source-references.v1` carries references.
Delivery is at least once; consumers deduplicate record_id. Broker/database outages
leave pending references; no feed bytes are discarded. Original archive is usable offline.

Invalid protobufs, unsupported differential feeds and invalid entity joins are
quarantined or excluded with diagnostics. Retried HTTP failures and scheduler clock
discontinuities record gaps. Receipt cutoff controls replay, never provider event time.
No newer GTFS download can reconstruct an earlier as_of. Schedule files older than
24 hours are unverified fallback and disable RT overlays; RT requires matching GTFS
digest. Missing/stale/unmatched entity data retains scheduled fallback labels.
Entity timestamp absence remains unknown; a fresh feed header cannot establish entity
freshness. Predicted times and vehicle positions are not measured arrivals.

`resilience coverage` reports each full six-hour window. Completeness requires all
three valid FULL_DATASET feeds with no interval above cadence+5 seconds, including
06:00/12:00 edges; development captures are excluded. `resilience release-gate`
returns failure until five complete windows, three selected real morning bundles,
OTP comparison, performance, licences, secrets, CI and static demo evidence pass.

Gap journal records `detected_at` separately from interval endpoints. Display replay
filters `detected_at <= as_of`, so a later-discovered sleep/fetch gap cannot alter an
earlier frame. Legacy rows without detection time are conservatively available only
at migration/import time; unknown past knowledge is never backdated.

## Persistent recording, verified2026-10-02

The coordinator installed the prepared user LaunchAgent using
`python scripts/install_collector.py --install`. It verified running PID97810,
repository working directory, virtual environment Python and empty error log.
No prior forced collector process remained. Outside the recording window the agent
was waiting and no sleep assertion was active. It runs independently of this chat
and restarts on failure; a logged-in user session, open lid/network and functioning
machine are still required. The installer generates local absolute paths at runtime,
not in committed configuration. Remove with `--remove`.

The collector holds an OS file lock for its entire lifetime; duplicate processes fail
visibly and dead processes release the lock automatically. Mac `caffeinate -i -w PID`
exists during weekday05:50–12 preparation/recording and while already dispatched
feed requests drain; it exits if the recorder dies. Windows uses a user Task
Scheduler task prepared by the same installer, restarting failures and ignoring new
instances. Its process sets the Windows sleep assertion during Brisbane
preparation/recording and draining of dispatched feed requests. Windows installation is documented but not exercised on
this Mac. Neither mechanism can guarantee collection with a closed lid or power loss.

Poll clocks retain the fixed 06:00 phase on monotonic deadlines. Elapsed slots
are skipped without burst catch-up; each feed permits one in-flight request.
After a late dispatch, a phase slot less than 20/20/50 seconds after the preceding
actual dispatch is consumed without a new request. This preserves the fixed phase
and avoids near-adjacent requests after late startup. The minimum spacing appears
in new receipt details and heartbeat separately from the 25/25/55 target policy. Feeds have independent in-flight tasks, so one feed's retries cannot pause
healthy feeds. Archive-reference outbox delivery runs on its own worker. Receipt-time
coverage still exposes real latency/failure gaps; no catch-up records fill missed
intervals. Startup during a window journals missing preceding receipts; heartbeat,
PID/window/preparation/force status, actual policy, pending refresh, bounded
request attempts and elapsed time, receipt health and failure logs persist under
`data/runtime`. Receipt health retains the last valid time/gap across failures, shows
nonnegative age and the unchanged per-feed limit, and warns when valid-receipt age
or an in-flight request exceeds that limit. SIGTERM requests stop new dispatch and
drain workers before releasing the archive lock and idle-sleep assertion.
After completed-window requests drain, a single coverage audit is
saved to `data/runtime/coverage-YYYY-MM-DD.json`; it is not run on every poll. Replay gaps use
actual detection time. Completed responses retain their true receipt time, including
responses after 12:00; feed dispatch ends at 12:00. Receipt digests identify the
GTFS already archived and available at that receipt time. Each new receipt records
actual `collector-v2` polling and attempt timing separately from frozen nominal
analysis fields. The strict coverage limits remain 35/35/65 seconds, including
window edges. Failed broker/PostGIS delivery remains in the durable outbox.

Idle protection does not wake a sleeping computer and cannot prevent manual sleep,
closed-lid sleep, power loss or network/upstream outages. A separate bounded weekday
05:50 wake helper is prepared separately; the collector installer does not install
privileged wake events or change global power settings. Reinstalling the macOS
LaunchAgent unloads its own existing label before loading the current definition.
