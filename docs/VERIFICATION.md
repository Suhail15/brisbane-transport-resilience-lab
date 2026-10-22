# Verification record

The first release evaluates three recorded mornings, 19–21 October 2026. Source receipts meet the unchanged six-hour gap rules on six weekdays; the final protocol uses three later mornings after two development dates.

- Local Python: **206 passed, one optional infrastructure check skipped**, 22 October. The opt-in API/PostGIS test run also passed **2/2**, including spatial stops and walking geometry in the actual local database. One upstream Starlette/httpx deprecation warning remains.
- Frontend: **28 passed**, including full synthetic compact-bundle production builds, filters and preserved immutable manifests.
- Independent morning checker: **54/54** saved cases reconcile, including denominators, objectives, bus duties, cutoffs and stress inputs.
- Offline reproduction: **54/54** exact matches from the saved inputs, 508.35 seconds on the recorded Mac environment.
- Journey HTTP performance: **300 measurements** across three snapshots, worst date p95 **0.17285 seconds**. First lookup included; two date-specific clients overlapped. This measures journey queries, not recovery search.
- Independent OpenTripPlanner: original raw agreement **4/7** core and **1/6** walking cases (the walking equality is an absent-source null). Four original exact transit cases plus two explicitly post-initial direct-platform diagnostics; source-specific review explains eight access differences. Fifty-three timetable movements and twelve OSM paths checked. Walking models remain different; no calibrated access equivalence is claimed.

See [reference validation](REFERENCE_VALIDATION.md), [findings](FINDINGS.md), [protocol](MORNING_EVALUATION.md) and [release evidence](RELEASE.md). Candidate CI, exact site identity, licensing, browser walkthrough, credential inspection and final public access are bound separately to each release; these local numbers cannot approve a changed candidate.

[Earlier afternoon verification](DEVELOPMENT_VERIFICATION.md) is retained as development history, separate from final morning evidence. Windows collector installation and full operational bus availability remain outside the verified scope.

## Published result

The [v1.0.0 release record](releases/v1.0.0.md) links [successful candidate CI](https://github.com/Suhail15/brisbane-transport-resilience-lab/actions/runs/39717438183), [successful Pages deployment](https://github.com/Suhail15/brisbane-transport-resilience-lab/actions/runs/39718310864), all eleven accepted gates, exact manifests and the subsequent anonymous/public-browser verification. The static demo worked with the local backend stopped. The original tag dispatch failed the default main-branch environment rule; the identical commit deployed successfully from main.
