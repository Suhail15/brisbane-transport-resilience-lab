# ARCH-006

- Task ID: ARCH-006
- Title: independently design and review further recording resilience
- Status: independent design and implementation review complete; accepted for coordinator verification/deployment
- Owner: architecture reviewer
- Reviewer: root coordinator

## Model and reasoning

Explicitly assigned and coordinator-confirmed dispatch: GPT-6.1 Sol, max
reasoning, for the initial independent design and final review. No subagents were
spawned. Tools do not expose independent serving-model identity; this records the
requested assignment and coordinator confirmation, not backend introspection.

## Approved specification and decisions

The user authorizes strengthening collection after the October 8 failure. Initial
investigation/design was read-only. Root approved decision26 and the collector-v3
contract before dependent implementation, including narrow archive/outbox
ownership exceptions. Root then authorized independent final code/fault/history
review and changes to this handoff only.

Preserve strict 35/35/65 receipt-gap ceilings, frozen nominal 30/30/60 analysis
fields, all real payloads/timestamps, full six-hour windows, received/detected-time
replay cutoffs, source freshness labels and the five-window gate. No retrospective
pass, dropped slow successful response, raw-data filtering, paid hosting or public
release is authorized by this work.

Approved operating design: 15/15/45-second fixed phases, 10/10/40 minimum
submission spacing, one feed task through archive completion, existing 20-second
HTTP phase timeouts and at most three worker-owned attempts. The shared client
has 90-second keepalive expiry and three total/idle connections. One telemetry
worker coalesces status and retains log/gap events, preserving original gap
detection time. Persistence completion stays outside immutable receipt metadata.
Outbox-only timeouts/backoff and 25-reference batches retain durable unsent
references. Root approved pending-envelope recovery under the recorder lock and
Standard macOS service classification, preserving global power settings.

Root additionally approved the two reproduced corrections below: fresh actual
submission-time eligibility checks and validation of received-time GTFS linkage
during pending recovery. It then approved serialization of same-identity archive
publication, active/waiting lock-entry cleanup and authoritative committed metadata
for repeated append calls. Deployment, commit/push, CI and live service verification
remain coordinator-owned.

## Required inputs and dependencies

Read AGENTS.md, decisions25/26, contracts, ARCH-005/OPS-001, INT-007, QA-003,
collector/schedule/runtime/telemetry/archive/database implementation, installer
and existing timing/recovery tests. Source evidence is the ignored live journal,
raw receipt files and content-addressed payloads. Journal inspection uses SQLite
URI mode=ro and PRAGMA query_only=ON, without constructing a live Archive.

The ignored pre-change guard is
`data/runtime/reliability-2026-10-08/original-recording-hashes.json`. Fault
reproductions use temporary archives and fake clocks/pools/sinks, with no external
HTTP, production data mutation, service restart or OS power change.

## Files owned

- `docs/tasks/ARCH-006.md`

All production, tests, other handoffs and original data are read-only. Do not
spawn more agents; at most three project agents including root.

## Expected output

A bounded evidenced design, actionable independent implementation review and
final acceptance after required corrections and fault verification. Preserve
recording/replay correctness. Distinguish measured timing, causal inference,
counterfactual margins, test evidence and live deployment evidence.

## Acceptance checks

- **Passed independently: October 7 accounting.** Brisbane 06:00-12:00 is
  2026-10-06T20:00:00Z through 2026-10-07T02:00:00Z. Qualifying valid receipt counts
  are 712/712/358. TripUpdates alone has a 36.982839-second gap, exactly explained
  by 30.190457 seconds between request starts plus 6.792382 seconds of response
  latency growth, from 0.274174 to 7.066556 seconds. Simultaneous VehiclePositions
  remains within 35 seconds at 34.617362 seconds. Original receipts lacked attempt
  details, so network, transport, retry and OS causes cannot be separated fully.
- **Passed independently: October 8 accounting.** Brisbane window is
  2026-10-07T20:00:00Z through 2026-10-08T02:00:00Z. Qualifying counts are
  864/864/393. TripUpdates gap 35.952040 equals request-start interval 28.310826
  plus latency growth 7.641214 (0.300147 to 7.941361 seconds).
  VehiclePositions gap 35.852748 equals 28.397149 plus 7.455599
  (0.149617 to 7.605216 seconds). Both succeeding responses are first-attempt HTTP
  200. Task starts are 09:08:23.413410 and 09:08:23.502022 Brisbane, approximately
  3.4/3.5 seconds after the 09:08:20 phase. No gap-journal entry exists for either
  failed morning. Timestamp differences and attempt monotonic durations differ
  slightly; do not conflate their measurements.
- **Passed independently: margin and load calculation.** Replacing the 25-second
  cadence with 15 while retaining the measured October 8 timing differences gives
  counterfactual gaps 25.952040/25.852748, leaving 9.047960/9.147252 seconds below
  the unchanged 35-second limits. This is engineering headroom, not a repaired or
  promised morning. Normal six-hour requests increase from approximately 2,121
  to 3,360, about 58.4%; retries add requests beyond that nominal count. Translink
  terms reviewed October 8 contain no listed client polling minimum, which does
  not establish unlimited capacity. Sources:
  https://translink.com.au/about-translink/open-data/terms-and-conditions and
  https://www.python-httpx.org/advanced/resource-limits/.
- **Passed independently: preventable-risk design review.** Installed HTTPX
  0.28.1 defaults to five-second idle expiry and explicitly supports sharing a
  Client between threads. Current polling routinely outlives that expiry; this is
  avoidable connection overhead, not proved as the Oct8 cause. Synchronous status
  fsync/logging/SQLite gaps formerly ran in tick. A feed future also includes full
  archive persistence. Outbox had unbounded initialization connections despite
  its separate worker. The local launchd manual establishes Background resource
  restrictions and lighter Standard limits, not a hard scheduling guarantee.
- **Passed independently: pre-change and first-review preservation.** Original
  baseline and the implementation review both contain 4,460 journal receipts and
  raw receipt files, plus 4,430 distinct payloads, with no missing objects or
  payload-hash mismatch. All aggregate hashes are unchanged: compact/sorted
  canonical row metadata c1b8e406544c42b1222fc7c1250489c92e43cf768609e61ee84ae7f94cfeccd3;
  sorted record-ID/receipt-file-hash pairs
  59d0b31f46245f218e772ab71bdff4f6f32ed1e908891fd170f6c0cc34293af5;
  sorted object-path/decompressed-hash pairs
  300a43a9d1c75eac7221afd5b88e83c6e5bc7b410793401dcc81b5eb46cdc10b.
- **Passed independently: direct original guard comparison.** Every one of the
  ignored guard's 4,460 canonical metadata hashes and 4,460 receipt-file hashes
  matches the live archive. All 4,430 compressed-object and 4,430 decompressed
  payload hashes also match. Zero changed/missing entries and zero additional
  real records were found. This was a read-only comparison.
- **Passed independently: unchanged historical coverage.** The real coverage
  function runs through a read-only adapter and still reports 0/5 mornings.
  October 7 retains only the 36.983-second TripUpdates failure; October 8 retains
  35.952/35.853-second failures. Strict limits remain 35/35/65 and nominal expected
  counts remain 720/720/360. No development capture repairs a morning.
- **Required correction reproduced independently: noon submission race.** A
  temporary normal tick observes 11:59:59, then its actual submission clock reads
  12:00:01. It submits all three feeds after noon because active was sampled
  before awake/drain work. Root approved fresh per-feed submitted_at and
  submitted_mono checks for window eligibility, spacing and Retry-After, using
  those same actual values for metadata and last_dispatch. Force development
  remains permitted; already submitted responses still drain. Do not mask the
  defect with a development label. QA independently reproduced the failure.
  **Correction accepted independently:** actual fresh wall/monotonic samples now
  govern each feed's due-slot advancement, window/force eligibility, spacing,
  provider deadline, metadata and last_dispatch, retaining the original phase
  anchor. Both ordinary-noon suppression and forced development regressions pass.
- **Required correction reproduced independently: pending future GTFS link.** A
  genuine FULL_DATASET receipt at 00:00Z with a corrupt pending envelope pointing
  to a valid GTFS received at 00:01Z was recovered and its envelope removed.
  Payload, identity and protobuf checks alone did not prevent future association.
  Root approved validating each non-null pending GTFS digest against a valid
  archived GTFS receipt received on/before the original feed receipt. None remains
  allowed for genuine missing-schedule cases. Invalid evidence must remain pending
  and produce a recovery error. **Correction accepted independently:** each
  non-null hash must be canonical 64-character lowercase hexadecimal and identify
  an existing valid GTFS receipt received no later than the original receipt.
  Missing/future references are rejected with evidence retained; None remains
  permitted. Both new linkage regressions pass.
- **Passed independently: narrow corrected regression run.** Sixteen targeted
  boundary, provider-deferral, executor/persistence timing, pending publication,
  corruption and recovery checks passed (14 deselected) in 0.24 seconds. The tests
  use temporary archives and fake clocks/network. Frozen contracts, engine,
  coverage, ingest/replay and release paths have no Git diff. No additional
  material blocker was found in the first corrected review. The later full-suite
  duplicate-publication failure below was separately corrected and accepted.
- **Read-only implementation review.** Current source separates
  heartbeat/log/gap writes from tick, captures HTTP receipt time before lookup and
  append, and returns persistence completion only in runtime health. One feed
  future remains occupied through archive completion. Pending recovery requires
  the process-held recorder lock, canonical UTC identity, safe contained object
  path, payload hash, source URL and valid protobuf metadata, with committed rows
  authoritative. Windows awake calls remain on the recorder thread. Outbox-only
  connection/statement/lock bounds, 25-reference batches and 5-to-300-second
  failure backoff preserve unsent references. All required implementation
  corrections in this review are accepted below; live operational evidence
  remains separate.
- **Duplicate-publication correction, coordinator full-suite evidence.**
  Root's full suite with live PostGIS reported 112 passing checks and one failure
  in the existing `test_dedup_and_atomic_content_archive`. Twenty calls using six
  workers append the same identity; one caller can clear pending before another
  caller's unlink, raising FileNotFoundError. Making unlink idempotent alone also
  leaves the immutable pending exists/read disappearance race. Independently
  reviewed and recommended a process-local keyed publication lock for only the
  canonical archive-root/record-ID pair, covering pending publication through
  clearing. Count active and waiting users under a short registry mutex before
  lock acquisition; decrement in finally after release and evict only at zero.
  Do no I/O under the global registry mutex; different identities/archives must
  remain parallel. Keep committed receipt metadata authoritative and clearing
  idempotent. The recorder lock/startup-only recovery supplies the separate
  collector process boundary. This review did not rerun the reported full suite;
  the corrected bounded regression outcome follows.
- **Passed independently: final keyed lock and metadata authority review.** The
  final source acquires a resolved-root/record-ID lock around the entire object,
  envelope, journal, receipt-file and pending-clear lifecycle. Active/waiting
  references are incremented before waiting; finally decrements after releasing
  the identity lock and evicts only at zero. No I/O occurs under the registry
  guard. Different identities remain parallel, including feeds that receive the
  same payload at different genuine times. Pending clearing is idempotent.
  Inside the identity lock, a committed row supplies the envelope and commit
  metadata, preventing changed duplicate annotations from staging a conflict.
  Original rows/files remain authoritative and are not rewritten. The lock is
  process-local; the separate recorder lock and startup-only recovery remain the
  collector's process/recovery boundary.
- **Passed independently: final publication regressions.** Five checks passed in
  0.92 seconds: unchanged 20-call same-identity concurrency regression, different-
  identity parallel progress/registry cleanup, interrupted duplicate with changed
  annotations, interrupted pre-journal publication and interrupted post-journal
  receipt publication. The fixtures preserve original receipt/object bytes,
  metadata, cutoff behavior and one outbox reference. `git diff --check` passed.
  Frozen analytical, coverage, ingest/replay and release paths still have no Git
  diff. The earlier full original-data guard is retained as the completed baseline;
  no unnecessary full payload scan was repeated after a source-only correction.
- **Verification coverage reviewed:** original failure fixtures
  and separate new-margin examples; recurring 0.5/3.5-second jitter and severe
  honest failures; actual task delay and minimum spacing; busy feed/GTFS/outbox/
  telemetry/storage isolation; three retries, provider cooldown and complete slow
  successes; retained gap detection cutoffs; startup/05:50/06:00/noon/restart/new
  day/weekend/clock cases; real process interruption before/after journal and
  receipt-file completion; recovery lock/path/hash/protobuf/GTFS-link corruption;
  assertion child restart and Windows ownership; bounded outbox-only waits and
  backlog health. QA-003 now records 45 passing checks across its four assigned
  files plus the unchanged archive-replay suite, and compilation/diff checks;
  that complete set was reviewed but not independently rerun here. This reviewer
  independently ran the 16 correction checks and five final publication checks
  above. Recovery tests inject
  interruption at durable stages; do not describe them as hardware/power-loss
  validation. Direct guard preservation passed above. Full suite, isolated real-
  source development capture, installed service read-back and CI remain root-owned.
- **Final independent implementation acceptance.** The required noon admission,
  pending GTFS availability and duplicate-publication issues are resolved within
  root-approved interfaces and verified as recorded above. No material blocker
  remains in this implementation review. Existing strict 35/35/65 completeness,
  nominal 30/30/60 fields, real source bytes/times, replay cutoffs and failed 0/5
  evidence remain required. This acceptance authorizes coordinator integration
  and operational verification; it does not establish deployment, a future
  complete morning or public release.

## Escalation issues

The noon and GTFS-link risks were promptly escalated, fixed and independently
accepted. Root's later duplicate-publication regression was corrected using the
reviewed per-identity serialization and original metadata authority; its bounded
checks passed independently. No required implementation blocker remains. No
production file was edited here; only this handoff is owned by this review.

Network phase timeouts are not total-response deadlines; a progressing slow body
or explicit provider delay can occupy a worker longer. Shared disk/SQLite stalls,
lid closure, manual sleep, power loss and upstream outages can still invalidate a
morning. Telemetry diagnostics remain in memory until written and are not crash
safe; a stalled diagnostics worker can leave a stale heartbeat. Pending envelopes
protect completed durable stages, not bytes or metadata never durably stored.
Twenty-five-reference batches and requested ExitTimeOut=300 do not guarantee
drain within the previously observed effective 60 seconds. OS service read-back,
Windows native behavior and future strict morning acceptance require their own
evidence. No added overlapping feed request or analytical/schema weakening is
approved. After two failures on one issue return the collected evidence.
