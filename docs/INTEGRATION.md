# Integration evidence and outstanding gates

DATA-001 / INTEGRATE-001 uses approved frozen contracts and separate architect-approved
choices/display DTOs. Actual model: GPT-6.1 Sol, medium reasoning. No additional agents
were spawned. Collector, audit, schedule reconstruction, actual OSM graph paths,
PostGIS geometry/index storage, durable Redpanda outbox, DuckDB/Parquet analytics,
FastAPI async jobs and compact static export are implemented.

Mac live checks: PostGIS official linux/amd64 image runs under Apple Silicon emulation;
Redpanda runs native. Root verified valid receipt archive, successful broker delivery
and zero pending outbox after initial startup. First snapshot persisted 61,607 movements.
`RESILIENCE_INTEGRATION_DB=1 python -m pytest tests/integration -q`: 10 passed (latest rerun includes later-detected-gap cutoff regression),
including cutoff, schedule exceptions, atomic concurrent dedup, malformed/differential
quarantine, unknown entity timestamp exclusion, directed OSM access paths, API errors,
and actual PostGIS geography query. Full engine verification is ARCH-001's evidence.

Official OTP 2.10.0, Java25, Xmx2G graph build succeeded in 9.6s (root-operated),
32,700 vertices / 83,941 edges / 1,235 stops / 1,771 patterns. GTFS subset preserves
20,801 full trips and 617,584 stop-time rows. OSM PBF is a 995,536-byte conversion of
the recorded XML via official pyosmium 4.3.1. Sources outside the street extraction
remain in transit schedules; isolated outside stops are an explicit graph limitation.
Two independent routing attempts (exact stop ids and coordinates) failed with
`DataFetchingException: Index 1127 out of bounds for length 0`; responses are local
`data/runtime/otp-probe.json` and `otp-coordinate-probe.json`. Escalated after the two
repeated failures; ARCH-001 diagnosed eager Raptor initialization on the empty repository.
Separate `--build --save` then `--load --serve` resolved the error. Six real schedule-only
queries then completed: exact arrival agreement 1/6; other active cases differ by
-11,+309,+544,+528 seconds (CSA minus OTP), and inactive Fairfield origin has a CSA
walking-access route but no OTP stop-location itinerary. Full real outputs are local
`data/processed/otp-comparison.json`, reproduced by `scripts/check_otp.py`. Discrepancy
review belongs to ARCH-001/root. Independent routing gate remains false.

Remaining: five prospective complete weekday mornings, three eligible real morning
bundles, independent OTP comparisons, full approved workload timings, clean remote CI,
Translink contact/approval and OSM derivative review, public credential scan, completed
frontend walkthrough. `resilience release-gate` must fail now. This local packet is
ready for frontend integration; task remains partial until the unresolved gates and
remaining full end-to-end scenario checks are completed.

Default compact local export was exercised: `data/derived/demo`, four development
snapshot headers/choices/display frames, versioned GTFS networks and a hash manifest;
zero completed scenario runs at that export time. This is not a completed demo gate.
`python scripts/run_preview.py --snapshot <schedule-or-recorded-id> --budget 0`
creates six fixed actual-stop requests and a clearly hypothetical20-minute delay,
then polls the local async API; budget2/4/8 exercises relevant recovery candidates.
Future complete mornings cannot be replaced by this afternoon preview.
