# Pilot source audit, 2026-10-02

Observed GTFS receipt: 2026-10-02T03:43:42.779005Z, SHA256
`2614954a251786aa312a434551fe7000cb10a9b928a9d8f412a69a98c1d1f8da`.
Feed coverage states 2026-10-01 through 2026-11-30. Archive contained 154,076 trips.
The versioned lock `configs/pilot.json` was resolved from source stop/route identifiers:
all bus lines serving the Fairfield/Annerley origin rectangle, and rail lines serving
Fairfield, South Bank, Central and Roma Street platform stops. This gives 73 public
line names and 539 GTFS version route ids. Retained 20,801 full feed trips and 617,584
stop-time rows; 2,201 trips active on 2026-10-02. No retained trip is clipped at a map
boundary or recording window. Weekly calendar rules apply first, then exceptions.

2026-10-02 source-derived bus patterns: 278 timing/topology patterns and 360 pairs
with exactly matching terminal stop ids. Recovery candidates are subsequently limited
to 12 actual affected journey/corridor patterns by the pure engine; templates are
existing service, while extra buses and duty outcomes are hypothetical.

Fairfield station ids `600052`/`600194` exist in the feed but have no active movements
on 2026-10-02. They remain visible, inactive, and usable only where actual OSM path
associations exist. This audit does not infer a reason for service absence. Fairfield
and Annerley bus stops provide actual alternatives. Parent station ids are display
identifiers; requests must identify actual platform/stop ids.

Recorded OSM highway extract: 2026-10-02T03:56:05.093406Z,
SHA256 `0a64e9b981db6ffda53397bd01a11051688ac60a2fa79a51aa336cb138e09c4d`.
Graph had 69,229 eligible nodes and 157,168 directed edges. First source-derived
walking build (before preserving inactive source platforms) found 3,776 directed
paths; after preserving all 1,236 retained stops, 4,172 directed paths were found.
Revised method v2 uses actual OSM edge lengths, with explicit <=30m endpoint snap
association diagnostics and a 600m guard including both snaps. Unknown entrance or
platform connector walks remain unresolved; geometry never invents them. Paths sharing
one snapped node without actual intervening edges do not create a walking link.
Walking status remains incomplete, including all stops outside the OSM extraction.

First development snapshot: 61,607 movements, built/persisted in 9.36s. Development
RT report had 197 matched and 1,547 unmatched entities: most unmatched records belong
outside the pilot; the total is not a claim that SEQ identifiers are invalid. Of the
matched set, 61 were stale and 25 had inconsistent/unsupported entity references.
Invalid predicted chronology falls back for the complete trip, with diagnostics.
Entity timestamp handling was subsequently tightened: absent entity timestamps are
unknown, not replaced by feed header freshness. These are predictions and collection
facts, never observed passenger outcomes. Per-snapshot quality JSON preserves entities
and route/mode group diagnostics; Parquet/DuckDB summaries count source provenance.

July 2026 monthly OD data are aggregated matched ticketing trips by operator/month/
route/direction/time grouping/ticket type/origin/destination. go card/EMV use touch-on
through touch-off, paper records issue time and may have destination n/a. Only matched
scheduled trips are included; Airtrain is excluded. Time bins are broad touch-on/issue
bins, not fare peak/offpeak or calibrated weekday morning demand. Missing/invalid
stop ids and quantities are excluded from mapped optional research proxies. October
GTFS identifiers can differ from July. Primary scenario request metrics stay equally
weighted and never label these quantities as calibrated passenger counts.

Actual OD audit: 1,123,161 source rows,989,467 valid stop/quantity rows,73,882
pilot-mapped rows,133,694 missing/invalid rows. Optional proxy remains excluded from
primary scenario metrics.

Reproduce: `resilience audit`, `resilience audit-od`, `resilience coverage`.
Raw source audits and full diagnostics remain ignored locally under data/processed;
these documented counts are dated observations and should be refreshed after source
or method changes. No complete morning, OTP comparison or public licence gate is claimed.
