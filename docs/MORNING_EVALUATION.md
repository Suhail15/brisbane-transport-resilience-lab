# Final recorded-morning evaluation method

The final evaluation is fixed by Decision 27, `docs/tasks/ARCH-007.md` and
`configs/morning-evaluation.v1.json`. The three final dates are **19, 20 and
21 October 2026**, each using the recorded **07:30:05 Australia/Brisbane** decision
frame. October 9/13 are development dates; October 22 is reserved. Policy results
cannot change the dates, target rule or request denominator.

Recorded replay frames are sampled every fifteen minutes from 06:00:05 through
11:45:05. There is no invented position interpolation. Receipt completeness,
source freshness, matched predictions, scheduled fallback and walking-path coverage
remain separate properties. Predictions and schedule records are not measured arrivals.

## Frozen requests, scenarios and resources

Every date retains the same twenty fixed OD pairs with five departures at
T+0/15/30/45/60 minutes: **100 equal-weight planned requests**. Missing stops and
unreachable routes remain in all denominators. These requests do not estimate
passenger demand, passenger counts or passenger savings.

Source-only target manifests are frozen before policy runs. Stable future
`departure_s`/`connection_id` order chooses the first corridor bus at configured
origins, and the first retained rail movement whose origin **or** destination
matches the configured rail IDs. The stop closure always uses exact stop 3713.
Cancellation and +1,200-second bus delay target the frozen bus; the corridor
closure targets the frozen adjacent rail movement in both directions. Scenario
windows last two hours. Absent targets produce explicit unsupported evidence and
halt execution rather than selecting a replacement after results.

The nominal matrix is three dates × four scenarios × budgets 0/2/4/8 bus-hours:
**48 cells**. The predeclared stop-closure budget-two sensitivity adds +300/+600
seconds per date to the reused zero-stress nominal run: **54 distinct cells**.
Nominal candidate identities are held fixed across paired sensitivity levels.
Running-time stress is hypothetical; altered complete duties can become infeasible.
No additional sensitivity case is selected because its results look favorable.

The reviewed model retains 600 m maximum walk, 1.2 m/s walking speed, 300-second
transfer slack, at most three transfers, two bus-hours per complete candidate duty,
at most twelve candidates, and 128 bounded swap evaluations. Fleet availability
remains hypothetical/unverified. Bounded search does not prove global optimality.

## Measures and comparisons

B/D/R reachability counts indicate baseline, disrupted and recovered journeys within
**3,600 seconds**. Lost requests are baseline-within-horizon requests absent from
the disrupted horizon; restored requests are those lost requests recovered within
the horizon. Restored fraction is **null when no requests were lost**.

Capped duration totals sum `min(duration, 5,400 seconds)` over the full fixed
100 requests, using **5,400 seconds for an unavailable duration**. The 60-minute
reachability test and 90-minute duration cap serve distinct purposes; a recorded
route longer than sixty minutes can contribute its duration without being counted
as reachable within the horizon. Positive no-action minus recovery capped duration
is a reduction across these planned queries, not a measured passenger benefit.
Hypothetical timing changes can produce negative disrupted-minus-baseline deltas;
retain and explain such cells rather than removing them.

The objective first maximizes restored requests, then minimizes total capped
duration, then used bus-hours, then sorted candidate IDs. Reports preserve the
selected, no-action and simple busiest affected **service-pattern** objectives.
The simple policy counts affected source trips in a pattern; it is not a measured
passenger-demand ranking. Its null objective means unavailable/inapplicable.
Matching the first three objective components does not establish the final
candidate-ID tie-break, since simple-policy selected IDs are not separately saved.
Chosen bus-hours are shown alongside the budget; unused resource is allowed.

Missed connections are **simulated planned transfer failures under the model**.
They are not observed missed boardings. Candidate rejection IDs/reasons and runtime
evidence are reported separately from journey outcomes.

## Deterministic reporting and evidence

Run:

```text
.venv/bin/python scripts/summarize_mornings.py \
  --summary data/processed/morning-evaluation-v1/summary.json \
  --output-dir data/processed/morning-evaluation-v1/report
```

By default, the generator refuses output unless all 54 fixed cells are completed
and their immutable artifacts agree. `--allow-partial` explicitly produces an
incomplete report headed **PARTIAL**, listing every missing cell. A partial report
must never replace final findings.

The generator validates the prepared plan/config hashes, target request identities,
full result/input/metadata equality with authoritative immutable files, canonical
input SHA256 and request/scenario/candidate hashes, exact frozen target payloads,
resource limits and candidate identity pairing. It reconciles saved route arrays
against reachability, lost/restored and capped-duration arithmetic without routing
or rerunning optimization. Independent source/archive checks and release review
remain separate responsibilities; the generator does not certify the entire source
archive or an optimizer implementation.

Outputs are `report.md`, `report.json`, `metrics.csv`, `origin-impacts.csv`,
`candidate-rejections.csv` and `runtime.csv`. All 54 cells and null outcomes remain
in the JSON/CSV, with exact run IDs/input hashes and links to immutable morning
result copies. The Markdown contains the complete outcome matrix and policy
objective/provenance table. CSV nulls are written as the literal `null`.

Origin rankings use the twelve nominal zero-budget scenario/date cells once each,
ordered by lost requests and then signed capped-duration increase. Full origin
rows also retain every budget/sensitivity cell. Aggregated exposures recur across
dates/scenarios and must not be described as distinct passengers or people.

Historical result artifacts record creation timestamps but may lack valid elapsed,
start and completion times. Missing durations remain null. Neither creation times
nor file modification times establish API queue time or execution latency. The
coordinator's separately timed journey benchmark/offline recomputation evidence,
when available, must retain its own scope and cannot be relabeled as original
API run duration.

The original afternoon findings are preserved verbatim in
[DEVELOPMENT_FINDINGS.md](DEVELOPMENT_FINDINGS.md). All **54/54 final cells are now complete**, independently reconciled and exactly
reproduced offline. [FINDINGS.md](FINDINGS.md) records the final morning outcomes;
the original afternoon report remains separate. The 225-file private reproduction
pack matched every case in 508.35 seconds. This is reproduction elapsed time, not
original API queue or per-run timing. Three hundred journey HTTP measurements
gave a worst-date p95 of 0.17285 seconds; October 20/21 client batches overlapped.
See the findings for exact evidence paths and [REFERENCE_VALIDATION.md](REFERENCE_VALIDATION.md)
for the bounded independent OTP scope. Fleet availability, calibrated walking
access and final public-release approval are not established by these results.
