# ARCH-003

- Title: operator-mapping escalation and bounded final packet review
- Status: operator decision approved; stable integration handoff review pending
- Owner: architecture agent
- Reviewer: root coordinator
- Task ID: ARCH-003

## Model and reasoning

GPT-6.1 Sol, max reasoning, retaining the explicitly dispatched settings.
No additional agents spawned.

## Approved specification and decisions

ARCH-002 remains the approved next-packet specification. Engine/contracts and
versioned analysis/stress/journey-set implementation remain frozen. This clarification
resolves one real operator-schema mismatch without expanding the fixed pair list.

### Route 196 operator crosswalk

Observed source fields differ: July OD OPERATOR is `Transport for Brisbane`, while
GTFS agency is umbrella `Translink` and the relevant routes lack agency_id. Neither
an exact agency-name join nor inference from opaque GTFS trip ids is supported.

Two official primary sources support a narrow reviewed crosswalk:

- Brisbane City Council's [Buses page](https://www.brisbane.qld.gov.au/transport-and-parking/public-transport/buses)
  describes Council's BUZ services and lists route 196 between New Farm and Fairfield
  Gardens via the city.
- Translink's [24 January 2025 release](https://translink.com.au/news-and-media/releases/667646)
  explicitly associates the operator Transport for Brisbane with Brisbane City Council.

Combining those statements supports a **reviewed inference** binding the exact OD
operator `Transport for Brisbane` and public bus route `196` to Brisbane City Council.
GTFS agency remains `Translink`; the operator match basis is
`reviewed_official_route_crosswalk`, not agency-name equality. Approval is limited to
route 196 and the already bound GTFS digest. Exact OD stop ids, ordered direct source
trip, unique GTFS direction and dated/source eligibility still apply. Other routes,
operators, fuzzy names and ambiguous mappings remain unknown until separately evidenced.

Persist a versioned crosswalk with both URLs, actual verification/retrieval timestamps,
preserved evidence content hashes, original source labels, exact public route, bound
GTFS/source hashes, method version and reviewed-inference label. Official reference
retrieval must not be backdated to the replay cutoff. This is post-hoc method evidence;
primary replay and the OD/GTFS source receipts retain the <=T availability requirement.
It does not introduce later operational observations into the recorded snapshot.

### Local candidate preparation and final acceptance

Root approved two explicit phases to avoid an artifact-dependent release deadlock.
Local candidate preparation uses the public data projection, verified immutable
artifacts and legacy exclusions, but does not authorize publication. It requires
five complete weekday windows, exactly three selected complete morning dates,
eligible source provenance and source/licence/publisher permission evidence. It can
produce candidate bytes before the dependent static-walkthrough/public-manifest/CI
acceptance, while the full release gate remains false. It cannot substitute private
afternoon inputs or flip final gate flags. Keep this mode distinguishable from the
ordinary private development export and remote publication.

Final acceptance verifies the candidate's exact manifest SHA-256 against the accepted
public_artifacts report, every manifest file, all source/morning requirements and all
final evidence scopes/revisions. Record the prepared artifact identity before any
publication. Publication uses those accepted bytes under the existing authorization
only after every final gate passes; changing them requires new artifact acceptance.
Neither phase sends or publishes anything remotely by itself.

## Required inputs and dependencies

Stable INT-003 handoff, integrity/reproduction/evidence/index/proxy modules and their
bounded checks. Existing real afternoon inputs and frozen primary 20-pair workload.
Official sources above were checked on 2026-10-02; integration owns preserved source
evidence and mapping output. Actual morning coverage remains 0/5 and Translink source
approval remains pending.

## Files owned

- `docs/tasks/ARCH-003.md`
- Approved clarification additions to `docs/CONTRACTS.md` and `docs/DECISIONS.md`

No implementation, primary pair list or recorded source is edited by this task.

## Expected output

Immediate source-backed operator decision, then a bounded review of stable INT-003
integrity/reproduction/evidence/index outputs for required blockers only.

## Acceptance checks

- **Verified:** official Council route196 listing and official Translink operator/
  Council identification, with source URLs above. The exact timetable route page also
  shows route196's Fairfield Gardens–Merthyr service, but does not establish operator
  identity: [official route page](https://jp.translink.com.au/plan-your-journey/timetables/bus/T/196).
- **Approved:** narrow reviewed crosswalk sent to root and integration before proxy
  implementation completion. No operator inference from opaque trip identifiers.
- Stable module review and actual bounded check outcomes will be added at handoff.
- **Confirmed code-path blockers, sent to integration:** current full release gate
  requires static_demo/public_artifacts before public export can produce their
  required candidate bytes; current verify_release validates a supplied manifest's
  files but does not bind that manifest hash to accepted public_artifacts evidence.
  The approved two-phase design and exact manifest binding resolve those blockers.

## Escalation issues

The mismatch was explicitly escalated rather than silently equating a network brand
with its operator. The official source chain resolves route196 only. Missing evidence
or ambiguous source mapping must stay excluded; no widening of coverage is approved.
Public collection/permission/release gates remain false until actual evidence exists.
