# ARCH-004

- Title: final bounded private milestone review
- Status: review complete; private milestone accepted within the documented scope
- Owner: architecture agent
- Reviewer: root coordinator
- Task ID: ARCH-004

## Model and reasoning

GPT-6.1 Sol, max reasoning, using the explicitly requested ARCH-004 dispatch.
No subagents spawned. This review edits only its own task handoff.

## Approved specification and decisions

ARCH-002 and ARCH-003 approve immutable final authority, exact saved-input/source/
code identities, compact summaries, offline reproduction, scoped hashed release
evidence, two local preparation/acceptance phases and the sparse secondary monthly
ticketing proxy. The primary engine/contracts and analysis/sensitivity/journey-set
modules remain frozen. Review scope is required defects only.

Two bounded fixes were approved, implemented by INT-004 and independently accepted:

- Enumerate immutable final records before export/index eligibility filtering.
  Verify any same-ID mutable copy before filtering, include a completed final without
  a mutable copy, and distinguish legacy-only records with no immutable final.
- Verify the supplied public candidate's exact file set against its accepted
  manifest. Reject extra/missing files and paths escaping the bundle boundary.
  Root additionally approved the same narrow helper guard for reproduction packs.

These fixes do not broaden the analytical workload, change source inputs or
authorize publication.

## Required inputs and dependencies

Read AGENTS.md, ARCH-002, ARCH-003, INT-003, CONTRACTS, RELEASE, REPRODUCTION and the
implementation/tests for integrity, bundles, run summaries, reproduction, proxy and
evidence. Local snapshot is `35f84816f6e208318ed8e49a`; the reviewed ignored pack is
`data/derived/reproduction-int003-reviewed`. Root owns production UI checks, final
full-suite/build/scans, private commit/push and matching remote CI.

## Files owned

- `docs/tasks/ARCH-004.md`

No implementation, test, primary contract, source receipt or recorded artifact is
edited by this review.

## Expected output

Private milestone acceptance or concrete required blockers, with actual independent
check outcomes and the remaining public-release conditions stated separately.

## Acceptance checks

- **Passed independently:** focused versioned-analysis/release-integrity suite,
  12 passed in 0.67s before the final bounded fixes.
- **Passed independently:** externally reviewed pack manifest SHA-256
  `67160494c4307f5cae928e4ed52268beffd990a4779b90035461f78bdf3cdf92`, all 65
  listed file hashes and 138632495 content bytes. All eight selected immutable runs
  passed canonical input/component, metadata, snapshot/derived, receipt/object,
  cutoff and matching engine/adapter verification.
- **Passed independently:** offline exact recomputation of budget-zero run
  `6a2a0d116d1c4257ba051e49a5cda92a` using that externally anchored pack. All
  primary/comparison objectives, candidate/duty/rejection facts and metrics matched.
  Its 100-request B/D/R counts are 98/98/98, lost/restored 0/0 and baseline/disrupted/
  recovered capped totals 179452/180077/180077. Execution timing is excluded.
- **Passed independently:** recomputed all six secondary report comparisons from
  their returned routes using rational weights. Exact reachable/lost/restored proxy
  quantities, capped means and immutable result hashes match. Coverage remains
  1/20 pairs and 5/100 requests; three weights 41 plus two weights 37/2 conserve
  total 160. Preserved official crosswalk evidence bytes match their hashes.
- **Confirmed required defect in an isolated temporary fixture:** changing the
  mutable copy's status to failed silently yielded zero exported completed runs
  despite its completed immutable final. The exporter selected mutable records
  before consulting immutable authority. INT-004 resolves this using immutable
  records first and same-ID mutable comparison before eligibility filtering.
- **Confirmed required defect in an isolated temporary fixture:** final verification
  printed success with an additional unlisted file and an unchanged accepted public
  manifest. INT-004 resolves this using exact file-set/hash verification and safe
  portable paths; the approved helper also guards reproduction packs.
- **Final fixes passed independently:** 23 focused versioned-analysis/release-
  integrity tests passed in 1.01s. Regression fixtures reject changed mutable status,
  removed metadata and changed snapshot identities before export/index filtering;
  the API returns HTTP 409. A final without its mutable copy remains exported/indexed.
  Accepted-candidate and externally digest-anchored pack fixtures reject added files
  under the unchanged reviewed manifest. POSIX/Windows absolute paths, traversal,
  Windows separators and symlink escapes are rejected. API live progress overrides
  only records lacking an immutable final.
- **Final pack guard passed independently:** the new exact-file helper accepts the
  actual 65-file reviewed pack and all hashes; its externally anchored manifest
  identity above is unchanged. Recorded inputs and frozen primary modules were not
  changed by INT-004 or this review.
- **Coordinator-reported integration context:** root's final backend suite passed
  75 checks with live PostGIS; eight frontend checks passed with unchanged UI code.
  The earlier scan of 125 proposed files found zero known credential/large/raw/
  private-contact hits. Fresh guarded private export `data/derived/demo-int004`
  succeeded with four snapshots and 22 completed runs, including four custom UI
  runs with a separate five-request/one-hour configuration. Those do not replace
  the reviewed fixed 100-request workload. Root checked completed custom budgets
  and production static mode with the backend off. Production rebuild, final API/
  static checks, private commit/push and matching CI remain coordinator-owned;
  this review does not present those as independently rerun.
- **Verified current release refusal:** release-gate returned exit 1 with
  `public_release_authorized=false`, 0/5 complete weekday windows, 0/3 selected
  morning dates and pending scoped licence/publisher/candidate/evidence checks.
  Actual evidence belongs in ignored `data/runtime/release-evidence.json`, selected
  by `RESILIENCE_RELEASE_EVIDENCE` after the candidate commit is frozen; the tracked
  pending template must not be committed with a self-referential HEAD identity.

## Escalation issues

- The two required defects above are resolved and independently accepted. No
  required code blocker remains within this bounded private milestone review.
- Public release remains pending real five-window coverage, three eligible recorded
  morning bundles, publisher approval, final clean candidate/report identities,
  matching candidate CI, static walkthrough and final asset/credential scan.
- Windows live collection and fresh cold-cache/machine benchmarks remain outside
  the verified local scope. Earlier OTP/performance facts retain their documented
  workload and machine scope.
- Root rechecked online source terms on October 3. The user clarified that this was
  online information rather than a received publisher approval reply. Approval stays
  pending; neither the terms lookup nor this private acceptance satisfies that gate.
- No commit, push, upload, visibility change or publication performed by this review.
  Root owns final repository/CI/UI acceptance and future release preparation.
