# ARCH-013

- Title: independent saved corridor-study arithmetic, source and duty verification
- Status: checker implemented/tested; source and development parity checks passed; v2 cell reconciliation pending saved results
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
- PASS (checkpoint): implementation and owned-file formatting checks are complete; no active code edits remain. Root may commit/start CI. Further evidence-only updates follow saved development/final cells.
- PENDING: v2 development cell arithmetic/duty reconciliation as outputs arrive; root's confirmation authorization; then final registered public-date matrix, offline reproduction and actual export/arithmetic review. No expected outcome is recorded as observed evidence.
- PENDING: coordinator authorization before any confirmation policy execution by its assigned owner. Verification itself does not create policy results.

## Escalation issues

- Initial v1 source coverage omitted known connecting buses. A read-only source audit demonstrated 40 of 120 modeled losses had direct omitted scheduled bus alternatives using existing paths on each development date. Root fixed source coverage under Decision 31 before any confirmation outcome; retain the initial evidence as development diagnostics.
- Separate arithmetic/source/duty validation cannot prove the routing optimizer's optimality or actual operational feasibility. An exhaustive small-fixture recovery comparison is available in the existing engine test suite if a concrete remaining search concern warrants it; it does not establish optimality for this bounded case-study candidate set.
- Next owner: integration provides schema/development outputs; this task reports verifier outcomes and concrete findings; root decides confirmation readiness and publication.
