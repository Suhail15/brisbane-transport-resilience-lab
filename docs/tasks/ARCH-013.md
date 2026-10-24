# ARCH-013

- Title: independent saved corridor-study arithmetic, source and duty verification
- Status: source, parity and all 12 v2 development cells passed; registered-date verification and actual export review pending
- Owner: ARCH-013 independent verification agent
- Reviewer: root coordinator

## Model and reasoning

- Dispatch model: `gpt-6.1-sol`; reasoning effort: `max`; original dispatch used `fork_turns=none`, as confirmed by the coordinator.
- No subagents.

## Approved specification and decisions

- Follow Decisions 29–31, `configs/corridor-impact.v2.json`, `docs/tasks/ARCH-012.md` and `docs/tasks/INT-012.md`. Initial `corridor-impact-v1` development/profiling artifacts remain preserved separately from the corrected v2 network.
- Independently inspect saved full cells, using separate arithmetic rather than importing the producer's calculation/summary helpers. Structural parsing through existing contracts is permitted; this does not authorize routing or recovery execution on confirmation inputs.
- Preserve original released results/replay bytes, numerical engine and source inputs. The 240-query census is the optimization denominator; 100 original queries are separately scored controls under identical plans. No pooled counts or passenger-demand/financial claims.
- This verifier reads saved results and does not execute policy runs. Root separately gates confirmation/replication policy execution after development review. ARCH-014 separately authorized source-adapter work by this author; that adapter's source derivation requires root review and is not an independent review by another author.

## Required inputs and dependencies

- The approved config and protocol, the producer's immutable per-date preparation manifests and full saved policy cells, snapshot/stress input references, and producer/code/config hash metadata.
- Existing independent morning verifier is a reference for scope, not a producer arithmetic authority: `scripts/verify_morning_results.py` and `tests/integration/test_morning_result_verifier.py`.
- Preservation baseline: `data/runtime/impact-study-2026-10-23/original-file-hashes.json`; root owns the baseline and independent final preservation acceptance.
- Coordinate schema with `/root/impact_integration`, which owns `services/resilience/pipeline/case_study.py`, `scripts/run_case_study.py`, `tests/integration/test_case_study.py` and development outputs. Do not modify those files.

## Files owned

- `scripts/verify_case_study.py`
- `tests/integration/test_case_study_verifier.py`
- `docs/tasks/ARCH-013.md`

## Expected output

- A portable read-only checker and machine-readable report that fail on altered metrics, input references/hashes, query identities/denominators, unsupported rail targets, invalid duties and over-budget resources.
- Independently derive primary platform census/control identities and all arithmetic: 60-minute B/D/R, lost/restored/null fractions, 90-minute capped totals, signed disruption/recovery changes, pairwise improved counts, impacted and unaffected cohort splits, separate controls, resource efficiency and post-closure-arrival decomposition.
- Reconstruct the source-defined rail segment set and conservative full-trip closure impact, validate receipt cutoff/provenance and check rail-only cancellation. Independently check prescribed bus-time stress, frozen candidate phases/identities, matching complete source bus patterns, two-hour resource cost and complete cycles with both five-minute turns.
- Validate saved path feasibility against the applicable baseline/disrupted/recovered connection sets and actual walking links where available. This checks reported paths and arithmetic; it does not prove earliest arrival or global plan optimality.
- Independently rebuild the Decision 30 scoring retention proof, including whole source trips before the 90-minute cutoff, complete candidate source witnesses and otherwise absent scenario-segment witnesses. Published route arrays are checked against full effective snapshots, not scoring-only copies.
- Bind v2 network config/pilot/source-audit bytes and code dependencies. Parse raw GTFS with a separate CSV implementation to reconcile every retained complete source trip and parse fresh recorded TripUpdates cancellations; import no producer/source-adapter arithmetic helper.
- Confirm every file bound by the 530-file preservation baseline remains identical. Clearly distinguish the baseline's scope from new additive output.
- Small hand-calculated fixtures plus targeted corruption tests, with bounded execution on available development artifacts. Escalate repeated failures or schema uncertainty after two unsuccessful attempts.

## Acceptance checks

- PASS (focused tests): source-adapter and verifier suites → **41 passed in 17.71s**, comprising 8 source tests and 33 verifier tests. Cases include altered/re-signed metrics, query denominators, input identity, resource counts, fixed cohorts, source cutoffs, rail-only closure, missing cells, tampered snapshots/original files and v2 network/pilot evidence.
- PASS (small exhaustive gate): all 16 subsets of four fixture candidates preserve objective keys and complete duties under whole-trip scoring. Full/exhaustive/pruned/bounded best IDs agree at 0/2/4/8 bus-hours, including candidate-ID and zero-use ties. Exact 60/90-minute boundaries, over-cap raw routes, source witnesses after cutoff and complete trip suffixes are covered. This is fixture scope, not an optimality claim for real study results.
- PASS (real development parity): `data/runtime/impact-study-2026-10-23/independent-real-parity.json` verifies all 54 archived reference-file hashes and exact old-full versus optimized policy objects for 9 October budget 0 and 2. All shared metrics, raw primary/control route arrays, queries, selected IDs and duties agree. The full budget-two elapsed time was 581.912 seconds versus 292.871 optimized; this is calculation timing, not API latency.
- PASS (v1 bounded reconciliation): before the v2 correction, both saved optimized 9 October cells passed full route/arithmetic/resource/scoring-proof checks and the 530-file original preservation gate. These initial coverage-limited development results are not presented as confirmation findings.
- PASS (prepared v2 source gate): `v2-independent-source-review.json` binds protocol `dc47bd394e7e729d1d7f01a0105f8fbdf7eba0e56134d0e58259ffb144a28128`, code `924e7ef037080d282efb9407e9045b6090609ea43496022667e4f5939b4112a5` and network `c26aebd89ac143cf8e13e3171d6fcfa940873d54c212fa2b83b0b18e8ffc8f1a`. Both development inputs passed separate raw-GTFS full-topology/cancellation reconciliation and preserve all old walking links. No policy was executed by this task.
- PASS (complete v2 development gate): independent read-only verification without `--allow-partial` checked all **12/12** registered development cells on 9/13 October, with `status=complete`, no errors and no missing cells. All 530 preservation-baseline files remain identical. Report: `data/runtime/impact-study-2026-10-23/v2-development-independent-verification.json`, SHA-256 `701975a6d43719708d494c56d12a0d69077c862c9c396ed19d550128f3b7e3f6`. The protocol and preservation manifest were externally pinned for this invocation.
- PASS (development interpretation): separate arithmetic over saved query rows is recorded in `v2-development-independent-interpretation.json` (SHA-256 `fd7278f1ab186c6bd08d0975a7ce0f35c43b2f925b576b99f9d261966945b430`). Every primary request remains within 60 minutes across all 12 cells, so lost/restored counts are zero. Nominal 9 October delays 122/240 requests by 45,743 total query-seconds; best 2/4/8 bus-hour plans save 1,554/2,842/3,154 seconds entirely outside that delayed cohort. Nominal 13 October delays 205/240 by 112,347 seconds; best plans save 2,556/4,044/4,484 seconds entirely inside that cohort. The eight bus-hour plan offsets about 3.99% of the latter closure-added duration. These are modeled workload measures, not passenger or financial benefits.
- PASS (separate controls and comparator): 13 October retains all 100 controls, including 10 baseline-unavailable queries that remain unavailable; these are not outage-caused losses. No primary savings occur after closure end. The simple frequency comparator ties the best evaluated result in both +300-second stress cells and 13 October +600 seconds. Nominal simple frequency saves only 32 seconds on 9 October and zero on 13 October even at eight bus-hours. No delayed-cohort recovery claim is supported for nominal 9 October.
- PASS (exporter source/numeric review): the root-owned exporter binds all checked cell hashes through current manifest/selection/protocol/snapshot bytes before output copying, checks compact study/date/60/90 identities, and compares numeric date/budget/policy/fixed-example fields against full checked cells. Its six integrity fixtures passed in 0.24 seconds. This is code/fixture review; the actual final public projection does not yet exist and remains a separate acceptance gate.
- PASS (checkpoint): implementation and owned-file formatting checks are complete; no active code edits remain. Root may commit/start CI. Further evidence-only updates follow saved development/final cells.
- PENDING: root's confirmation authorization; then final registered public-date matrix, offline reproduction and actual export/arithmetic review. No registered-date policy outcome was inspected for this development gate. No expected outcome is recorded as observed evidence.
- PENDING: coordinator authorization before any confirmation policy execution by its assigned owner. Verification itself does not create policy results.

## Escalation issues

- Initial v1 source coverage omitted known connecting buses. A read-only source audit demonstrated 40 of 120 modeled losses had direct omitted scheduled bus alternatives using existing paths on each development date. Root fixed source coverage under Decision 31 before any confirmation outcome; retain the initial evidence as development diagnostics.
- Separate arithmetic/source/duty validation cannot prove the routing optimizer's optimality or actual operational feasibility. An exhaustive small-fixture recovery comparison is available in the existing engine test suite if a concrete remaining search concern warrants it; it does not establish optimality for this bounded case-study candidate set.
- Next owner: integration provides schema/development outputs; this task reports verifier outcomes and concrete findings; root decides confirmation readiness and publication.
