# Final recorded-morning findings

Reviewed 22 October 2026. The final evaluation covers **19, 20 and 21 October**, using the fixed **07:30:05 Australia/Brisbane** decision cutoff, 100 equal-weight planned queries per date and 54 predeclared scenario/budget/stress cases. Every case completed; independent reconciliation and exact offline reproduction each passed 54/54.

The result is modest and conditional: no case lost or restored a query within sixty minutes. Closing stop 3713 increased capped journey duration; a hypothetical two-hour bus duty reduced that total by 584/782/782 seconds across the fixed queries. Budgets four and eight selected the same two-hour duty. With five or ten extra assumed bus running-time minutes, no relief duty was selected and there was no duration benefit.

These are modelled query outcomes, not measured passenger demand, passenger benefits, actual operating savings or demonstrated fleet availability. Source predictions are not measured arrivals. Bounded search does not prove global optimality.

## Recorded inputs and fixed protocol

Six complete weekday 06:00–12:00 receipt windows were audited: October 9/13/19/20/21/22, comprising 20,160 valid non-development feed captures. October 9/13 are development, 19/20/21 final, and 22 reserve. Completeness uses the unchanged 35/35/65-second maximum feed gaps including edges; it does not establish prediction freshness or walking coverage.

The final private replay contains 72 frames: twenty-four fifteen-minute samples per date, 06:00:05–11:45:05, without interpolation. The same twenty OD pairs and five departure offsets form every 100-query denominator. Missing stops remain unavailable. Source-only bus/rail targets and exact stop 3713 were frozen before policy runs. No date, target or result was replaced after outcomes.

Four scenarios × four budgets × three dates give 48 nominal cases. Stop closure at budget two adds +300/+600-second running-time stresses on each date, reusing the nominal zero level: 54 distinct cases. The [evaluation method](MORNING_EVALUATION.md) defines constraints and source selection; the [afternoon development findings](DEVELOPMENT_FINDINGS.md) remain separate.

## Stop closure and policy comparisons

B/D/R means baseline/disrupted/recovered queries within sixty minutes. Capped totals include all 100 requests and use a 5,400-second penalty for unavailable duration. Positive reductions are against disrupted no action, not against measured operations.

| Date | B/D/R | Baseline capped,s | No-action capped,s | Best capped,s | Simple-policy capped,s | Budgets 2/4/8 → used bus-hours | Reduction,s |
|---|---|---:|---:|---:|---:|---|---:|
|2026-10-19|90/90/90|196251|196822|196238|196822|2/4/8 → 2/2/2|584|
|2026-10-20|90/90/90|194289|195197|194415|195197|2/4/8 → 2/2/2|782|
|2026-10-21|100/100/100|146855|147597|146815|147597|2/4/8 → 2/2/2|782|

The simple busiest affected service-pattern policy spends two bus-hours without reducing these capped totals. The best evaluated duty has the same restoration count but a lower capped duration. Its benefit is therefore a duration comparison, not restored reachability. Zero-budget runs select no duty. Every restored fraction is null because every lost count is zero.

## Predeclared running-time sensitivity

| Date | Extra seconds | B/D/R | Best capped,s | Used bus-hours | Reduction vs no action,s | Rejected candidates |
|---|---:|---|---:|---:|---:|---:|
|2026-10-19|0|90/90/90|196238|2|584|0|
|2026-10-19|300|90/90/90|198750|0|0|1|
|2026-10-19|600|90/90/90|201665|0|0|4|
|2026-10-20|0|90/90/90|194415|2|782|0|
|2026-10-20|300|90/90/90|199122|0|0|1|
|2026-10-20|600|90/90/90|201251|0|0|4|
|2026-10-21|0|100/100/100|146815|2|782|0|
|2026-10-21|300|100/100/100|153702|0|0|1|
|2026-10-21|600|100/100/100|155689|0|0|4|

Nominal candidate identities stay fixed across stress levels. At +300 seconds a feasible simple policy can tie no action on restored count and capped duration while using more bus-hours; the search selects zero hours. At +600 seconds the stored simple-policy objective is null. Rejection reasons and IDs remain in the machine-readable report. These stresses affect assumed running times; they are not observed delays.

## All scenarios and null outcomes

Cancellation, rail corridor and bus delay on October 19 also select two bus-hours at nonzero budgets and reduce capped totals by 584 seconds. On October 20/21 these three scenarios select no extra bus and have zero recovery reduction. Those null cases are retained. A relief duty can improve a fixed query timetable without restoring a lost sixty-minute journey; this is not evidence that the targeted disruption affected passengers.

Some hypothetical altered timings reduce capped duration relative to the original baseline: for example, October 19 bus delay gives 196,251 baseline versus 194,607 disrupted seconds with 90/90 reachable queries. Changed timings can create different feasible planned connections. The signed difference remains in the results and is not interpreted as an operational benefit.

The complete matrix below retains every cell. All lost/restored counts are **0/0**; all restored fractions are **null**. Column R is recovered queries within sixty minutes, and reduction is disrupted-minus-recovered capped seconds.

| Date | Scenario | Budget | Stress,s | R/100 | Used hours | Reduction,s | Exact run ID |
|---|---|---:|---:|---:|---:|---:|---|
|2026-10-19|cancellation|0|0|90|0|0|`4d01bcf1655c439ca1310660e0dcbf7f`|
|2026-10-19|cancellation|2|0|90|2|584|`e7e142d3ff0f42f398a65f655684f051`|
|2026-10-19|cancellation|4|0|90|2|584|`60864a53894745e0926cdf2cfda5c047`|
|2026-10-19|cancellation|8|0|90|2|584|`3096bfc80f52493688722c32de5b7046`|
|2026-10-19|stop_closure|0|0|90|0|0|`48af669a61c1412c98321da575015195`|
|2026-10-19|stop_closure|2|0|90|2|584|`c458c82135ae435b949b23ac4ed3f658`|
|2026-10-19|stop_closure|4|0|90|2|584|`f5516d8e87ab4b7d912fe60c0f51fe7a`|
|2026-10-19|stop_closure|8|0|90|2|584|`68ca23f3f72c45b9a4e2dee0b7740642`|
|2026-10-19|stop_closure|2|300|90|0|0|`e16ead9f4ad1403e8fefc779e7a12da1`|
|2026-10-19|stop_closure|2|600|90|0|0|`e495f0c16360456985228c5363963eeb`|
|2026-10-19|rail_corridor|0|0|90|0|0|`077f6091d8f94cd5b5cfff221724734f`|
|2026-10-19|rail_corridor|2|0|90|2|584|`95eb9bbe4feb45a190ddf7fc5d6cf871`|
|2026-10-19|rail_corridor|4|0|90|2|584|`34ad783a2ee74aff9f37055315f2472d`|
|2026-10-19|rail_corridor|8|0|90|2|584|`8e7117052eef4872b43da18e898cbc36`|
|2026-10-19|bus_delay|0|0|90|0|0|`f058f54b9fa7474498c3f7e278e54138`|
|2026-10-19|bus_delay|2|0|90|2|584|`30c1af7092d042d98d03c0b909319931`|
|2026-10-19|bus_delay|4|0|90|2|584|`e5ff2d2f5ae1418a85655b19fee0ef7d`|
|2026-10-19|bus_delay|8|0|90|2|584|`d266e602ea09421db13a31c7d1e1e1c9`|
|2026-10-20|cancellation|0|0|90|0|0|`250e378ba7ca4bdc8bed453bfeedbbb2`|
|2026-10-20|cancellation|2|0|90|0|0|`3a0bea9eb2cb4a7abad8e2711fc0fde9`|
|2026-10-20|cancellation|4|0|90|0|0|`42fa8918c9c148929975481380b76acd`|
|2026-10-20|cancellation|8|0|90|0|0|`76a14a3e7927442c96b06546ba9ef2dc`|
|2026-10-20|stop_closure|0|0|90|0|0|`f631c5f4d6a241c2b95ed542f0f1486d`|
|2026-10-20|stop_closure|2|0|90|2|782|`3ef25c64202148acbbe277618bd6f69e`|
|2026-10-20|stop_closure|4|0|90|2|782|`72d5077c99784fd5b39c2beb7aae8e38`|
|2026-10-20|stop_closure|8|0|90|2|782|`38855bceddbc4423b008fcee74d7909c`|
|2026-10-20|stop_closure|2|300|90|0|0|`03e213542c69466fbcefb8a3ba37d0a0`|
|2026-10-20|stop_closure|2|600|90|0|0|`2834d6897c3344c19456d5b8505f6afb`|
|2026-10-20|rail_corridor|0|0|90|0|0|`06a98a94bcb54b809d7de7942687ee5f`|
|2026-10-20|rail_corridor|2|0|90|0|0|`ce962d6fd936468bade87cf05fc3624b`|
|2026-10-20|rail_corridor|4|0|90|0|0|`61e9bd15af4b4132acc54af2767d2dc1`|
|2026-10-20|rail_corridor|8|0|90|0|0|`d32807d86e734a1bb71b196ad594822f`|
|2026-10-20|bus_delay|0|0|90|0|0|`3999a1cbaf6949c083dcd72f471b5ebd`|
|2026-10-20|bus_delay|2|0|90|0|0|`abe984d35f4c4d59b5fe2f727bf97d15`|
|2026-10-20|bus_delay|4|0|90|0|0|`dd2627bd54fa4a8b90864451f7e93427`|
|2026-10-20|bus_delay|8|0|90|0|0|`63b35f565a434bffbe6bf75c033b9c3d`|
|2026-10-21|cancellation|0|0|100|0|0|`6928418bf90c40af811faec42527f943`|
|2026-10-21|cancellation|2|0|100|0|0|`2392250fcfa943979fee226bff1642a6`|
|2026-10-21|cancellation|4|0|100|0|0|`95da080391854610919a64d003aa7b60`|
|2026-10-21|cancellation|8|0|100|0|0|`a7c0dd4bdde94f128ae9fa0ab76b929b`|
|2026-10-21|stop_closure|0|0|100|0|0|`461f8b3dd9654958952d8b24cd86fc7c`|
|2026-10-21|stop_closure|2|0|100|2|782|`0e4deed1ad1e4c1bb9fff53b76147760`|
|2026-10-21|stop_closure|4|0|100|2|782|`01f32ccbe0c8437692c5f359ca4feb05`|
|2026-10-21|stop_closure|8|0|100|2|782|`0708a41a2b9b4798b104c36a06faa612`|
|2026-10-21|stop_closure|2|300|100|0|0|`5b3b7110225143a3a6011ab0644d0b18`|
|2026-10-21|stop_closure|2|600|100|0|0|`2611957179354a33838ef19df043a791`|
|2026-10-21|rail_corridor|0|0|100|0|0|`82b0fad47b864ac9bdfc61a1474560d9`|
|2026-10-21|rail_corridor|2|0|100|0|0|`cc208a0a3af0466c982aff17b0b1f29f`|
|2026-10-21|rail_corridor|4|0|100|0|0|`2c64b10f0e3d445698ce6f920ac28964`|
|2026-10-21|rail_corridor|8|0|100|0|0|`4f539e031bcf4bd4b9f33dddd6f556e2`|
|2026-10-21|bus_delay|0|0|100|0|0|`d35f091d300d4dbf8fae94aab23b6895`|
|2026-10-21|bus_delay|2|0|100|0|0|`9ec1869c8bd746b289ecc5006a4c1061`|
|2026-10-21|bus_delay|4|0|100|0|0|`dce03f0d15634f25949cf9f8251197d8`|
|2026-10-21|bus_delay|8|0|100|0|0|`a3c0a41156024e90aa89daf51603a75e`|

## Origin impact and planned connections

Across the twelve nominal no-action scenario/date cells, the largest signed capped-duration increases are at origin 600188 (+2,788 seconds over 180 repeated query exposures), 3803 (+2,506 over 60) and 3802 (+1,020 over 60). Every origin has zero lost requests. Exposure counts differ by origin; these are raw query totals, not normalized risk estimates or distinct passengers. Negative origin deltas are retained. Full per-origin, per-budget and per-stress rows remain in `origin-impacts.csv`.

Missed-connection counts describe simulated planned transfer feasibility under changed timetable events, walking paths and transfer slack. They are not observed missed boardings. Missing platform paths and scheduled fallbacks remain visible limits.

## Verification, runtime and reproduction

- Independent artifact/source/route/duty reconciliation: **54/54 passed**, zero reported errors, binding fixed targets and exact input/result hashes. It does not prove global earliest-arrival routing or global recovery optimality.
- Exact offline recomputation: **54/54 matched** in **508.35 seconds**, from a 225-file private reproduction pack. This is total reproduction elapsed time, not original API execution or queue time.
- Journey API: **300 HTTP measurements**, 100 per date; p95 values **0.07471 / 0.17285 / 0.16141 seconds**. The worst date remained below the two-second pilot target. October 20/21 client batches overlapped; first lookups after the API restart were included. Hardware: Apple M2, 16 GB RAM, macOS native Python API with local PostGIS/Redpanda.
- Historical individual recovery durations were not recorded defensibly and remain null. Creation timestamps and file modification times are not treated as execution durations.
- [Independent OTP review](REFERENCE_VALIDATION.md): original raw core **4/7**, walking **1/6**; the walking equality is an unavailable-origin null, not a transit match. Four original exact transit paths plus two post-initial diagnostics remain separate. Source review checked 53 movements and twelve mapped paths, with zero unexplained cases at that bounded scope. Walking access costs remain uncalibrated.

## Exact evidence identities

The generated local report retains every full metric, objective, null, candidate rejection and runtime field. Evidence paths (ignored runtime data, not assumed publicly downloadable):

- `data/processed/morning-evaluation-v1/report/{report.json,report.md,metrics.csv,origin-impacts.csv,candidate-rejections.csv,runtime.csv}`
- `data/processed/morning-evaluation-v1/independent-verification.json`
- `data/runtime/release-2026-10-22/{journey-performance-summary.json,reproduction-report.json}`
- Immutable `data/processed/run-results/<run_id>.json` and `run-inputs/<run_id>.input.json`/`.metadata.json`.

Nominal budget-two stop-closure input SHA256 identities:

- 2026-10-19: run `c458c82135ae435b949b23ac4ed3f658`, input `87a6793fcd1ce0588097ccfb43b065c8ad418b982c34c63cae943605322d375c`.
- 2026-10-20: run `3ef25c64202148acbbe277618bd6f69e`, input `159e8c49f30c2364c24d1ffdd375e46b53565ec4cfd3271c9d4a0d9ea77d16a6`.
- 2026-10-21: run `0e4deed1ad1e4c1bb9fff53b76147760`, input `58705c43233430f7331c6f3a4b9104b1c701d56d12a92b973b3c2d40faca85cd`.

The frozen configuration hash is `1b52daf5a9a85b6c0110b18b1b376042cd57ffbbb03d20feff118d175b214c9a`. Public-source permission handling and attribution are documented in [SOURCES.md](SOURCES.md). Final bundle licence binding, credential review, release-candidate CI and actual public deployment/access checks remain pending in the [release checklist](IMPLEMENTATION_CHECKLIST.md). A completed private evaluation does not establish publication completion.
