# ARCH-002

- Title: final analytical integration review and next-packet approval
- Status: review complete; local analytical packet accepted at stated scope
- Owner: architecture agent
- Reviewer: root coordinator
- Task ID: ARCH-002

## Model and reasoning

GPT-6.1 Sol, max reasoning, using the existing explicitly dispatched settings.
No additional agents spawned. No implementation or recorded input was changed.

## Approved specification and decisions

Reviewed frozen v1.1 contracts and INT-002 against receipt-time snapshots, equal
primary requests, 60-minute reachability, all-request 90-minute capped duration,
source-relevant fixed candidates and complete two-hour bus duties. Current engine
and `analysis.py`, `sensitivity.py`, `journey_set.py` remain frozen. New integration
modules implement the next packet without relabelling historical code hashes.

### Accepted local scope

The real October 2 afternoon snapshot and seven final stop-closure/budget/sensitivity
runs are reproducible, correctly labelled development analysis. All seven retain the
same 100 expanded requests and nominal candidate set. Integer scaling, unaffected
past movements/rail/walking and stress-induced duty rejection match the approved
semantics. Modest reductions in planned-query durations and the null restored counts
are supported; no actual passenger or fleet result is inferred.

### Approved next packet: final-result integrity and reproduction

Before public export, use canonical immutable `run-results` as completed result
authority and check any mutable experiment copy against it. Verify immutable input,
metadata, nominal snapshot and every derived snapshot byte hash, source record/content
references and matching code. Reject missing/corrupt artifacts, inconsistent embedded
input or result copies, interrupted/failed/cancelled runs and legacy/unversioned runs.
Private previews may retain explicitly labelled legacy files.

Prepare a separate reviewed reproduction pack outside Git, containing selected full
normalized snapshots, derived stress inputs, immutable completed runs and canonical
inputs/metadata, source receipt/content references, configuration/mapping manifests
and matching engine/adapter version references. Browser bundles remain compact.
OSM-derived walking data is separately available under ODbL with attribution and
derivative-database obligations; relevant Translink content requires its licence/
approval evidence. Publish nothing before existing release gates pass.

`scripts/reproduce.py` verifies every required manifest/input hash, exact engine hash
and adapter hash. Use the matching repository revision; a mismatch fails instead of
substituting current upstream data. Recompute using saved requests, scenarios,
candidate ids, budget and search bounds, preserving unavailable outcomes. Verify
derived stress input hash before use. Compare exact primary metrics, plan/comparison
objectives, selected candidate ids and duty/rejection facts; exclude wall-clock timing
and mutable progress/store diagnostics. Timing is a separate machine-specific report.

Release checks must validate evidence existence, hashes, candidate revision and scope,
including the prepared public artifact manifest. Passed booleans plus arbitrary
reference strings are insufficient. Verify computed collection coverage, exactly the
three selected complete morning dates, linked real inputs, scoped OTP report, measured
performance, candidate CI, static walkthrough, licence/approval and final asset scan.
Root/Max may record concrete manual acceptance for a gate that cannot be automated;
unfulfilled source approval and future collection remain false. Verify published
bytes/state against the reviewed prepared artifacts after publication.

### Approved next packet: compact experiment index

Add a versioned summary DTO with `run_id,url,snapshot_id,created_at,status`, journey
set version/request count, scenario summaries (kind, source target ids, interval and
readable label), budget/used bus-hours, sensitivity seconds, hypothetical flag,
legacy/reproducible flags and completed aggregate metrics/objective summary. Derive
it from verified input/final artifacts. A menu must not load every itinerary to name
a run. Public summaries exclude legacy runs; private summaries label them.

### Approved next packet: secondary monthly ticketing proxy

Root accepted this specification; implementation may proceed without another
assumptions review. It does not change primary requests, equal weights, candidate
selection, recovery objective or primary result fields.

1. Use eligible monthly source receipts received <= snapshot T and bind their exact
   hashes/coverage. Rejoin raw source rows to the exact snapshot GTFS version, not
   the mutable latest-schedule normalized Parquet. Require exact operator/public
   route and OD stop ids plus a same-route ordered direct source-trip proof. Retain
   original OD direction text, the uniquely mapped GTFS direction and source trip/
   stop order. Do not assume `Inbound=0` globally, use fuzzy names or extrapolate
   transfer-leg demand to mixed journeys. Ambiguous/unmapped pairs are unknown,
   with exclusion reasons, rather than zero or invented weights.
2. Assign each fixed departure to its actual Brisbane wall-clock weekday/weekend
   source time bin, including service-day seconds beyond midnight. Weekday bins are
   [00:00,08:30), [08:30,15:00), [15:00,19:00), [19:00,24:00); Weekend is separate.
   These broad July ticketing bins are not October morning passenger demand.
3. For each eligible pair/bin, sum valid nonnegative source QUANTITY across disjoint
   ticket categories, preserving source row ids and rejecting invalid quantities.
   Divide that bin quantity Q equally among its n configured departures in that bin
   (`Q/n`). This conserves each represented bin's proxy once rather than five times.
   Use rational/decimal arithmetic with recorded serialization/rounding. Freeze the
   same weight table across all compared policies and stress levels.
4. Report mapped pair/request counts and coverage, total proxy weight and weighted
   reachable/lost/restored quantities/fractions on this mapped subset. Reachability
   is still <=3600s and capped durations still use 5400s for unreachable requests.
   Weighted mean capped duration is sum(weight*cap)/sum(weight). Lost/restored use
   the unchanged baseline/disrupted/recovered set definitions. Zero denominators
   yield null; unknown pairs stay outside this explicitly secondary denominator.
   Output is a monthly ticketing-weighted query proxy, not passengers or savings.
5. Hash/persist source and GTFS receipts, mapping proofs, proxy method/version,
   weight table, source bins, included/excluded rows and result references separately
   from primary run inputs. Do not broaden the frozen pair list for proxy coverage.

Actual source inspection found rows for only **1/20** configured pairs: 3692→19,
route 196, Inbound. Ordered exact GTFS source patterns map to direction 0 toward
New Farm/Mountford Road (899 matching trips across that feed, not an active-day
service-count claim). This is a source-specific mapping, not a universal direction
rule. The original OD receipt precedes the development cutoff. Its relevant July
quantities are 123 for 08:30–14:59:59 and 37 for 15:00–18:59:59; three departures
receive 123/3 and two receive 37/2. Expected supported coverage is 5/100 requests,
subject to exact dated/source mapping checks; sparse coverage must stay visible.
GTFS direction values distinguish directions rather than defining universal inbound
labels: [official GTFS reference](https://gtfs.org/documentation/schedule/reference/#tripstxt).

## Required inputs and dependencies

Read `docs/tasks/INT-002.md`, `docs/FINDINGS.md`, frozen contracts/decisions, all six
reviewed integration modules and versioned-analysis tests. Local recorded evidence
is under `data/processed`, snapshot `35f84816f6e208318ed8e49a`. Root turned the API off
for static QA; review used files and tests and made no live requests or new runs.
The monthly source receipt/mapping audit is `data/processed/od-audit.json`.

## Files owned

- `docs/tasks/ARCH-002.md`
- Approved specification/decision additions in `docs/CONTRACTS.md` and
  `docs/DECISIONS.md`

No engine, contracts.py, API, pipeline, test or recorded artifact was edited.

## Expected output

Concrete local analytical acceptance, actual independent checks, remaining release
blockers and a complete authorized integration packet for reproduction, summary
index, evidence guards and secondary OD proxy.

## Acceptance checks

- **Passed:** `PYTHONPATH=services .venv/bin/python -m pytest
  tests/integration/test_versioned_analysis.py -q`: 6 passed in 0.70s.
- Independently checked the fixed pair count/uniqueness/reverse directions and 100
  unique expanded requests. Across seven final runs, canonical input/component
  hashes, snapshot bytes, source cutoffs/ids, immutable metadata and final-vs-mutable
  result copies match. Request and candidate hashes are identical across all seven.
- Independently rebuilt B/D/R, lost/restored fractions and every capped-duration
  total from the 100 returned routes in each run, preserving request order. Nominal
  totals 180077/179757/179701/179701 and used 0/2/4/4 bus-hours match FINDINGS. Stress
  totals 187071/198647, lost 0/1 and restored 0/0 match stored results.
- Independent quotient/remainder arithmetic checked 44,240 affected future bus
  events at each nonzero stress level, all scaled pattern events and unchanged
  past/rail/walking facts. Complete-cycle arithmetic independently reproduces one
  infeasible candidate at +300s and three at +600s, plus selected duty cycle counts.
- Recomputed the stored 100-call p95 as **0.06916947082791011s**, matching the report.
  This is journey HTTP latency on the documented machine/workload, not asynchronous
  recovery latency or a fresh cold-cache/Windows measurement.
- Verified immutable cancelled run `e910f8de6f154a3db1146a4b9e4db27e` has null result
  and preparing-stage metadata. INT-002 reports 9.19s submission-to-acknowledgement;
  no independent live cancellation timing was attempted with the API off.
- Verified final seven engine hash
  `bcbe5612aa816b76800f3e6516f60a140f639ee87f8670443a7b4f7f99e70240`
  and current adapter hash
  `de8128b5165862d5263fdeea88f33d273d99132f013ab67748661b185428c8ce`.
- Root independently reports full suite 57 passed/1 live PostGIS skipped; integration
  separately exercised live PostGIS. Root owns final CI/static/full-suite acceptance.

## Escalation issues

- **Before public packaging:** export currently reads mutable experiment files and
  checks input/metadata only. The immutable finals currently match, but corruption
  of a result/snapshot/derived file is not yet rejected by the export path. Implement
  the approved authority/integrity checks and meaningful corruption fixtures.
- **Before public release:** release_gate currently trusts booleans/evidence_ref
  strings for external gates. Implement hashed evidence/scope verification or record
  concrete root/Max manual acceptance; never flip pending flags without evidence.
- **Remaining demonstration:** completed versioned 100-request artifacts currently
  cover trip cancellation, stop closure and rail corridor closure. The fourth frozen
  additional-bus-delay target has no completed versioned 100-request run. Execute
  that predeclared target once before claiming four real-data demonstrations; retain
  a null effect honestly. A legacy six-request delay does not satisfy that claim.
- `docs/INTEGRATION.md` retains historical text that the independent routing gate
  remains false; qualify that as historical and link ARCH-001's bounded reviewed
  acceptance without rewriting raw OTP disagreement evidence.
- Future five complete mornings/three public morning bundles and Translink approval
  remain pending. Sparse OD coverage, Windows live collection, final benchmark/CI/
  static QA and final public-asset scan remain explicit scoped conditions.
- Next owner: integration, GPT-6.1 Sol with medium reasoning, dispatched by root.
  No additional assumptions review is required before implementing this specification;
  any proposed broadening or ambiguous source mapping is excluded/reported or escalated.
