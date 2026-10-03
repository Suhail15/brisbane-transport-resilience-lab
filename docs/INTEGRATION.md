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
review was completed by ARCH-001/root: six exact transit matches and six explained
access differences, zero unexplained cases, accepted at that bounded scope. See
`REFERENCE_VALIDATION.md`; historical raw disagreement remains above. Release
acceptance still needs a candidate-bound hashed report.

Remaining: five prospective complete weekday mornings, three eligible real morning
bundles, final candidate-bound OTP/performance/CI evidence,
Translink publisher approval and OSM derivative review, public credential scan, completed
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

## INT-002 completed local packet

RunMetadata and canonical immutable inputs bind source/snapshot bytes, requests,
scenarios, nominal candidates, budget, search bounds, code and assumptions before
optimization. Legacy runs remain unversioned; restart-interrupted jobs fail visibly.
The 20 frozen source pairs generate 100 requests without dropping absent future ids.
Final nominal and 0/300/600-second stress results are in FINDINGS.md, including null
cancellation/rail examples and explicit complete-cycle infeasibility. Engine unchanged.

18 integration tests passed in 2.03 seconds, including hashes/defaults, unavailable
request denominators, integer stress chronology/duties, restart/legacy handling,
metadata export/corruption, gzip decoding and recorder uniqueness/window boundaries.
A running 100-request experiment acknowledged cancellation with no partial result.
Final 100-query journey p95 was 0.06917 seconds. Async optimization took 7.63–48.47
seconds for nominal budgets, and is never presented as a two-second optimization.

The coordinator installed and verified the Mac scheduled collector (PID 97810,
outside window, no awake assertion). Kernel lock, independent dispatch clocks,
background outbox and window-only sleep prevention are documented in COLLECTION.
Windows installation awaits a real Windows service check. Project Docker services
now declare restart unless stopped.

Final compact bundle data/derived/demo-int002-final is 20041384 bytes, with 17 completed
run files, immutable input/metadata and four development frames. Exact geometry dedup
preserves all 1825 source associations in 448 full shapes; gzip network is 612299 bytes.
Compressed manifest hash and decoding checked; duplicate network absent. Public gate
remains false: real complete mornings and permission/licence/release checks remain.

## INT-003 private preparation

Completed results now use immutable finals as authority. Export checks mutable-copy
agreement, canonical input/metadata identities, nominal/derived bytes, receipt cutoffs,
source content and historical code availability. Version 1 summary indexes keep menu
labels and aggregate metrics small; route legs remain lazy. The new frozen 100-request
bus-delay case completed with a null effect (see FINDINGS).

Private offline recomputation exactly matches the four approved stop-closure budgets.
The pack has external-manifest identity checking, source objects/receipts, software and
data licences, and separately attributed ODbL walking data. Secondary July ticketing
mapping is only 1/20 pairs and 5/100 queries; it never changes primary search or weights.

Publication checks now require hashed scoped reports and concrete manual acceptance,
with separate eligible candidate preparation and final manifest-bound verification.
Five mornings, three public morning dates and publisher approval still block release.
Frontend CI is mandatory; final candidate CI/static verification remains root-owned.
