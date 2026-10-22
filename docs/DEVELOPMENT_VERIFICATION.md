# Verification record

This record distinguishes current development checks from the eventual public release.
The current recordings are from Friday, 2 October 2026, in the afternoon. They do not
satisfy the planned morning evaluation.

## Engine and independent reference

- Forty engine tests pass, including 288 queries checked against an independently
  implemented ride-edge oracle.
- Official OpenTripPlanner 2.10.0 produced six distinct exactly matching real transit
  paths. Six access-path differences were reviewed against source geometry, leaving
  zero unexplained cases at that stated scope.
- Raw exact agreement remains 1/6 in the original sample and 6/7 in the expanded core
  sample. Walking access is incomplete; this is not a claim of full-network agreement
  or measured-arrival accuracy.

See `REFERENCE_VALIDATION.md` and `docs/tasks/ARCH-001.md` for the source-specific
comparison and the unchanged walking tolerance.

## Pipeline and analysis

On 3 October 2026, the final local Python suite passed **75 tests**, including the live PostGIS checks
(`RESILIENCE_INTEGRATION_DB=1`). The frontend suite passed **8 tests**. One
upstream Starlette/httpx deprecation warning remains; no test failed.

Checks cover duplicate/out-of-order records, cutoff isolation, calendars, transfers,
immutable input metadata, unavailable-request denominators, running-time stress,
complete bus duties, cancelled jobs and compressed bundle geometry. ARCH-002
independently reconciled seven final stop-closure/budget/sensitivity results against
stored route arrays and verified their input/source hashes.

A clean Docker API image built and returned healthy archive, PostGIS and Redpanda
responses. Mac infrastructure and the persistent collector were exercised. Windows
collector installation remains unverified.

## Performance

The final development benchmark used the fixed 20-pair, five-departure workload:
100 sequential end-to-end journey HTTP calls, including the first lookup.

- p95: **0.06917 seconds**
- Median: **0.04617 seconds**
- Maximum: **0.09779 seconds**
- Hardware: Apple M2, 16 GB RAM; Python 3.11.8, arm64, eight logical CPUs.

This meets the two-second journey-query target for the measured pilot workload.
Recovery optimization is asynchronous and has separate runtime evidence in
`FINDINGS.md`; it is not included in the journey-query claim.

## Interface and static package

The local browser rendered the actual recorded vehicle positions and source-backed
map. The production static build opened saved results with the backend stopped at
its intended repository URL prefix. Its four-bus-hour result matched 98 of 100
requests arriving within 60 minutes, zero lost/restored requests and four bus-hours
used. The rebuilt private preview was reviewed again with the backend stopped: readable
stop/segment/trip labels, snapshot intervals, budgets and stress assumptions appear
in the index. The selected four-hour record displays exact capped totals of
180,077 / 179,757 / 179,701 seconds for no intervention, the simple policy and the
best evaluated plan. Its 376-second aggregate improvement is across fixed
test queries, not passengers. A local custom five-request, one-hour stop-closure
comparison completed all four budget jobs through the actual interface.

Eight frontend fixture tests pass without ignored-data dependencies. The static
preview remains a development artifact: four afternoon frames and historical
completed results, including explicitly labelled legacy entries. It is not an
eligible morning release. A private 17-second still-view walkthrough is saved under
`data/runtime/walkthrough/`; it holds actual browser screenshots on screen and does
not claim continuous vehicle playback.

## Continuous integration and release

The earlier backend commit `fec68f7b18c8ffe95352f6f547f74ed6a28ccf11` passed the
Linux, Windows and macOS Python matrix in [Actions run36965117356](https://github.com/Suhail15/brisbane-transport-resilience-lab/actions/runs/36965117356).
That run predates the final frontend and is not a release-candidate check.

Five complete morning windows, three prepared real morning bundles, source publication
conditions, final artifact integrity/credential review, final CI and public access
verification remain required. See `IMPLEMENTATION_CHECKLIST.md` for current gates.
