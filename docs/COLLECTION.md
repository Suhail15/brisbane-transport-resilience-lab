# Recording and replay

Run `python scripts/start.py collect` continuously. The recorder waits outside
weekdays 06:00–12:00 Australia/Brisbane, polls TripUpdates and VehiclePositions every
30 seconds, Alerts every 60 seconds, and refreshes GTFS at least every 24 hours.
`--force` permits development recording outside the window; each such receipt is
explicitly marked development_capture and cannot satisfy a morning collection.

The first acquired sources are Friday 2026-10-02 afternoon. The earliest prospective
five complete morning windows are Monday 2026-10-05 through Friday 2026-10-09.
These are future collection dates, not claimed evidence. Keep the laptop awake,
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
exists only weekdays06–12 and exits if the recorder dies. Windows uses a user Task
Scheduler task prepared by the same installer, restarting failures and ignoring new
instances. Its process sets the Windows sleep assertion only while the Brisbane
recording window is active. Windows installation is documented but not exercised on
this Mac. Neither mechanism can guarantee collection with a closed lid or power loss.

Poll clocks now anchor to dispatch rather than adding HTTP response latency every
cycle. Feeds have independent in-flight tasks, so one feed's retries cannot pause
healthy feeds. Archive-reference outbox delivery runs on its own worker. Receipt-time
coverage still exposes real latency/failure gaps; no catch-up records fill missed
intervals. Startup during a window journals missing preceding receipts; heartbeat,
PID/window/force status and failure logs persist under data/runtime. Replay gaps use
actual detection time. Failed broker/PostGIS delivery remains in the durable outbox.
