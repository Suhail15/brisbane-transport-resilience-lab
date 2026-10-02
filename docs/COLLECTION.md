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
