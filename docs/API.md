# Local API and static replay contract v1

Base URL `http://127.0.0.1:8000/v1`. All timestamps are ISO8601 with timezone;
service-day seconds are integers in Australia/Brisbane and may exceed 86400.
JSON fields below are stable for frontend integration. Frozen engine payloads
are defined by `resilience.contracts`, with serialization `model_dump(mode="json")`.
Source quality and hypothetical labels must remain visible.

- `GET /v1/catalog` returns `{version:1, timezone, preview_only:true, pilot, snapshots:[{snapshot_id,snapshot_at,service_date,quality,url}], source_summary, release_gate}`.
- `GET /v1/network` returns GeoJSON FeatureCollection of Point stops and actual
  GTFS LineString shapes (properties `kind`, `stop_id`/`route_id`, `name`/`route_short_name`, `mode`).
  Pilot station parent features carry `platform_ids`; these parent ids must be
  resolved to actual platforms before routing. Network geometry is for display.
- `GET /v1/snapshots` returns `{snapshots:[...]}` as in catalog.
- `GET /v1/snapshots/{snapshot_id}` returns full `TimetableSnapshot`, including
  connections, directed OSM walking geometry, recovery pairs and source provenance.
- `POST /v1/snapshots` body `{as_of:"aware ISO8601"}` builds and records an immutable
  snapshot; responds 201 with full snapshot. No source received later can enter it.
- `POST /v1/journeys` body `{snapshot_id, request:JourneyRequest}` returns `RouteResult`.
- `POST /v1/experiments` body `{snapshot_id, requests:[JourneyRequest], scenarios:[Scenario], budget_bus_hours:0|2|4|8}` returns 202 `{run_id,status:"queued",progress:0,url}`.
  Requests are mandatory, fixed across comparisons, limited to 500. The UI may
  generate its selected OD requests at quarter-hour offsets for one hour.
- `GET /v1/experiments` returns `{runs:[{run_id,status,progress,url}]}`.
- `GET /v1/experiments/{run_id}` returns `{run_id,status,progress,created_at,snapshot_id,hypothetical:true,result:RecoveryResult|null,error:string|null}`.
  Status is queued, running, completed, failed, cancellation_requested or cancelled.
  Progress is a stage fraction [0,1], not a promised completion time.
- `POST /v1/experiments/{run_id}/cancel` requests cancellation. Current pure-engine
  evaluation can finish its atomic calculation before the result is discarded.
  Cancellation never publishes a partial result. Completed runs remain immutable.
- Unknown ids return 404; invalid contract inputs 422; unavailable schedule 409.

Static adapter: `python -m resilience.cli export --output data/derived/demo` emits
`catalog.json`, `network.geojson`, `snapshots/index.json`, each
`snapshots/{snapshot_id}.json`, `experiments/index.json`, and completed
`experiments/{run_id}.json`. Catalog URLs are relative to the bundle root and
`manifest.json` hashes every file. Frontend static mode lazily fetches these files;
it can select and inspect recorded runs with no backend. New calculations require
local API mode. Development afternoon bundles are labelled local preview and do
not satisfy morning/public gates. `--public` fails until every release gate passes.

Architecture approval ARCH-001 (2026-10-02): separate display DTO preserves the
frozen routing models. `GET /v1/snapshots/{snapshot_id}/display` returns
`{snapshot_id,snapshot_at,vehicles,alerts,gaps,quality,labels}`. Vehicle fields:
`entity_id,trip_id,trip_instance_id|null,route_id|null,mode|null,matched,event_at|null,
received_at,source_event_age_seconds|null,receipt_age_seconds,quality:fresh|stale|unmatched,
longitude,latitude,bearing|null,source_record_id,feed_sha256,gtfs_sha256`.
Alerts have `entity_id,header,description,active_periods:[{start:epoch|null,end:epoch|null}],
informed_entities:[{route_id|null,stop_id|null,trip_id|null}],cause,effect,received_at,
source_record_id,feed_sha256,gtfs_sha256,receipt_age_seconds`; source periods use
half-open semantics. Missing period endpoints are unbounded. All display receipts
share the snapshot cutoff and GTFS digest. Alert selectors identify source relevance;
alerts do not automatically become hypothetical engine scenarios.

Static catalog snapshot entries additionally contain `display_url` pointing to
`snapshots/{snapshot_id}.display.json`. Backend catalog entries use the same relative
bundle naming; live frontend builds the `/v1/snapshots/{id}/display` URL. Parent station
platforms with zero active service remain in snapshots and maps; do not invent service.

ARCH-001 approved compact choice/display DTOs: `GET /v1/snapshots/{id}/choices`
returns `{snapshot_id,snapshot_at,service_date,snapshot_s,quality,stops,trips,segments,
recovery_pair_ids}`. `stops` are Stop records plus `active_boardings` (future pickup
movement count; zero marks inactive service). Trips carry ordered complete `stop_ids`
and `trip_instance_id,route_id,mode,from_stop_id,to_stop_id,departure_s,arrival_s`.
Segments contain `from_stop_id,to_stop_id,route_ids` for actual adjacent movements.

Default static export is compact: snapshot `url` resolves to a display-only header
`{metadata,compact_display_only:true,display_url,choices_url}`. Lazy fetch `choices_url`
and `display_url` for controls and maps, and completed experiment files for results.
Full TimetableSnapshot is available only through local API. Public export always
excludes full engine snapshots, accepts only selected complete morning dates/windows,
checks realtime receipt provenance, and includes only runs tied to exported snapshots.

Missing entity timestamps stay null. Vehicles additionally expose `feed_header_at`
and `freshness_basis:entity_timestamp|unknown_entity_timestamp`; the feed header cannot
make an unknown-age vehicle fresh. Vehicle quality also admits `unknown`.
`GET /v1/health` checks archive, PostGIS and Redpanda, returning status ok/degraded.

Engine v1.1 integration: experiment status includes `progress_details` with
`stage,evaluated_plan_count,considered_candidate_count,feasible_candidate_count,
evaluation_upper_bound`. Candidate selection uses actual affected journey/corridor
anchors, existing paired topology, route diversity and deterministic coverage; up to
12 candidates. Recovery results expose `considered_candidate_ids` and
`infeasible_candidates:[{candidate_id,reason}]`. Cancel requests stop at a plan boundary
through the engine's `should_cancel` hook and publish no partial result.

Versioned display network: `GET /v1/network?snapshot_id={id}` selects the exact GTFS
source receipt referenced by that snapshot. With no parameter the default is the
latest acquired network. Static snapshot entries include `network_url` pointing to
`networks/{gtfs_sha256}.geojson`; frontend must use that selected snapshot URL.
`network.geojson` remains a latest-network convenience only. Each network source
manifest exposes its exact GTFS digest and receipt timestamp.
