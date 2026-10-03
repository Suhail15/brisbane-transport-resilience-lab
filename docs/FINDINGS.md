# Development findings, 2026-10-02

These are hypothetical disruptions and bus duties evaluated against a real recorded
Friday afternoon snapshot. They are not observed passenger outcomes, morning findings,
measured savings or proof of actual fleet availability. Snapshot
`35f84816f6e208318ed8e49a` was recorded at 2026-10-02 T 04:19:40.679451 Z
(14:19:40 Australia/Brisbane). Its exact content and source receipts are bound in every
run. OSM walking coverage remains incomplete; stale/missing real-time trips use labelled
scheduled fallback.

## Fixed workload and targets

`configs/journey-set.v1.json` freezes 20 actual source-active geography-selected OD
pairs, both directions, with bus/rail/mixed access. Five departures T+0/15/30/45/60
minutes give 100 equal-weight requests. No pair was selected for a winning intervention.
Inactive Fairfield rail platforms remain visible but are excluded from primary origin
selection because October 2 source service is absent. Future missing ids stay unreachable
in all denominators and incur the 5400-second capped duration.

Four targets were frozen before their versioned outputs: cancel the earliest future
corridor bus trip; close actual stop 3713; close actual retained rail movement
600010->600019 in both directions; add 1200 seconds to that bus trip. Cancellation and
rail-corridor examples had no impact on these requests:98 remained reachable,0 lost,
0 restored and no relevant recovery candidates. Those null findings are retained.

## Predefined stop closure and bus-hour budgets

Closing stop 3713 for two hours increased capped total duration from 179452 to 180077
seconds across 100 requests (+625 seconds), while 98 stayed reachable within one hour.
Four existing paired bus patterns were eligible. Extra buses remain hypothetical.
All budgets used the same inputs, requests, scenarios, candidates and 16 swap evaluation
limit. Each run records immutable method/code/input hashes; bounded search never claims
proved global optimality.

| Available bus-hours | Used bus-hours | Lost/restored | Recovery capped total,s | Reduction versus no action,s | End-to-end run,s | Evaluated plans |
|---:|---:|---:|---:|---:|---:|---:|
|0|0|0/0|180077|0|7.63|1|
|2|2|0/0|179757|320|13.28|5|
|4|4|0/0|179701|376|27.58|11|
|8|4|0/0|179701|376|48.47|16|

The simple busiest affected pattern policy yielded 179757 seconds with 2 bus-hours,
matching the bounded 2-hour plan. The 4-hour plan reduced a further 56 seconds; an 8-hour
budget selected the same 4-hour plan. With 0 lost requests, restored fraction isnull.
These duration reductions are across fixed planned queries, not passenger savings.
Runtime includes API preparation, queued calculation and polling; some experiments
shared the single worker and timings include that contention.

Final nominal run ids:0=`6a2a0d116d1c4257ba051e49a5cda92a`,
2=`3af3047a9a734b40aab380dde48244d4`,4=`f1c5880d9ac8462e995d43a6c28fc8f7`,
8=`152dc1fde6994c8287c145e1fc809b06`.

## One predefined running-time sensitivity

Stop closure/budget 2 was selected for the three-level sensitivity. Each complete
bus directional running time gains hypothetical 0/300/600 seconds proportionally, using
exact integer ceiling. Already departed movements, rail, actual OSM edges, activation
lead and terminal turn times remain fixed. The same four nominal candidate IDs are
held fixed; regenerated duties are rejected when a whole cycle cannot fit two hours.
All compared policies use identical stressed inputs.

| Additional bus directional seconds | Baseline reachable | Disrupted/recovered reachable | Lost/restored | Infeasible candidates | Used bus-hours | Recovery capped total,s |
|---:|---:|---:|---:|---:|---:|---:|
|0|98|98/98|0/0|0|2|179757|
|300|97|97/97|0/0|1|2|187071|
|600|95|94/94|1/0|3|0|198647|

At 600 seconds the remaining feasible addition did not improve the objective, so no bus
was selected. This exposes sensitivity to source-template running time and complete
cycle constraints. It is not an observed bus delay or available-fleet claim.
Run ids:0=`3a86af2d3b5748a280acae10b8dffe81`,
300=`eb7f946aedde4945a22e38cd1247ef37`,600=`768adcd3225d4785ad30b96c9bef28e7`.
Full local summaries include exact hashes, source references, rejected candidate ids
and reasons. These ignored data assets must accompany a reviewed reproduction pack;
current upstream sources cannot replace them.

## Performance scope

100 end-to-end journey HTTP calls on the fixed workload measured final p95 0.06917 seconds,
median 0.04617 seconds, maximum 0.09779 seconds, including the first lookup. Environment:
Macarm 64,8 logical CPUs, Python 3.11.8; coordinator hardware observation is AppleM 2/16 GB.
A three-entry cache holds immutable normalized snapshots; source/metadata bytes are
never replaced by newer downloads. This meets the 2-second journey query target for
this measured workload. Recovery is asynchronous and takes the separate times above;
the query target is not applied to the entire recovery optimization.

Public release remains blocked by five complete weekday mornings, three real morning
bundles, final release CI/performance review, source permission reply/licence handling,
and all other release gates. No development afternoon substitutes for those recordings.

## Fourth predefined bus-delay case

Run `914017cc67f541f6980eab47f27b92ff` used the same 100 requests and frozen
1,200-second additional-delay target, with a 2 bus-hour budget and 16 swap bound.
It completed in 5.99 seconds: baseline/disrupted/recovered reachable counts were
98/98/98, lost/restored were 0/0, and all capped totals were 179452 seconds.
No relevant candidate was generated and no extra bus duty was used. This is a null
result for the selected requests, not proof that the service delay affects nobody.

## Secondary monthly ticketing proxy

Exact source mapping supports 1/20 configured pairs and 5/100 requests: 3692→19,
route 196, original Inbound text, uniquely mapped GTFS direction 0 through 899
ordered source trips across the feed; 82 are eligible on October 2 after calendar,
exceptions and endpoint pickup/dropoff checks. Operator matching uses the reviewed official
route 196 crosswalk, rather than claiming the umbrella GTFS agency is an operator match.
This is a reviewed inference from [Council's route table](https://www.brisbane.qld.gov.au/transport-and-parking/public-transport/buses)
and [Translink's operator naming](https://translink.com.au/news-and-media/releases/667646);
reference retrieval was October 2 at 12:37 UTC, later than the routing cutoff.
OD and GTFS receipts themselves precede the cutoff. The references are method evidence.

July broad-bin quantities 123 and 37 are conserved once: three departures receive
41 each, two receive 37/2 each; total proxy weight is 160. Across nominal budgets
0/2/4/8 and the reviewed +300/+600-second stresses, the mapped subset has weighted
B/D/R of 160/160/160 and lost/restored of 0/0. Restored fractions are null.
Weighted mean capped duration is 65693/40 seconds nominal, 113249/64 at +300,
and 121349/64 at +600. These are monthly ticketing-weighted query proxies on the
sparse mapped subset, not October passenger counts or savings. Primary weights and
search results are unchanged; unknown pairs remain outside this secondary denominator.
