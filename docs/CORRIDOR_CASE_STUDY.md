# Rail closure: recovery benefit and resource cost

## The question

If rail services through Fairfield, South Bank and the city stop for two hours,
how do planned journeys change, and where can extra buses help? The comparison
counts the full bus duties needed to obtain each modeled improvement.

This is a separate study. The original release's 54 experiments and findings
remain available; a new workload or network cannot retroactively improve them.

## Fixing coverage before trusting the result

The first development run appeared to lose 120 of 240 within-60-minute queries.
Every lost query involved Roma Street. A source review found that the original
pilot selected buses serving the Fairfield/Annerley origin area and omitted
important busway connections at the other stations.

On both development dates, 40 of those 120 queries already had a direct scheduled
bus alternative within 60 minutes, using existing mapped walking paths. Those
are timetable checks, not observed passenger journeys. Treating the initial
losses as realistic disruption impact would have been misleading.

The corrected study includes the union of all development-source bus lines
serving the selected platforms' actual mapped walking catchments, together with
the original pilot. The frozen source rule uses 29 bus stops and 103 connecting
bus shortnames, adding 84 names to the original pilot. It keeps full active trips
and uses no frequency, favorable-outcome or recovery-benefit filter.

See the frozen [network specification](../configs/station-access-network.v1.json),
[study protocol](../configs/corridor-impact.v2.json) and
[source review](tasks/ARCH-014.md). The incomplete-network development proposal,
its interrupted runs and the exact computational parity checks are retained.
No confirmation recovery outcome informed this correction.

## Study design

- Development: 9 and 13 October 2026.
- Separate confirmation: the previously unused 22 October recording.
- Replication: 19, 20 and 21 October, already used in the original project.
- Decision cutoff: 07:30:05, Australia/Brisbane, using only source records received
  by that time. Provider predictions and scheduled fallback remain labeled.
- Primary workload: all ordered interstation combinations of eight fixed rail
  platforms at Fairfield, South Bank, Roma Street and Central, departing at
  0/15/30/45/60 minutes after the cutoff: 240 equally weighted queries per date.
- Separate controls: the original 100 requests, evaluated under the same selected
  plans. They do not add weight to the primary optimization.

The hypothetical closure lasts two hours and selects actual rail movements
along the Fairfield–Central section, including source express movements. The
model cancels complete trips crossing the section during the interval; it does
not model operational short-turns. Source buses remain available.

## Recovery choices and costs

Nominal affected-corridor relevance selects at most three existing paired bus
patterns. Four fixed activation phases per pair, 10/25/40/55 minutes after the
decision, give at most twelve candidate duties. Each uses one hypothetical bus
for two hours, includes complete service cycles and five-minute terminal turns,
and costs two bus-hours. No new street connection or route is invented.

Budgets are 0, 2, 4 and 8 bus-hours. Compare no extra service, a separately defined
frequency-ranked policy over the same source pairs, and the best evaluated plan.
The frequency policy measures scheduled service supply, not passenger demand.
The search retains the same greedy/bounded-swap limits and makes no global
optimality claim. A larger budget need not be fully spent.

At the two-bus-hour budget, repeat with 0/5/10 extra assumed bus running-time
minutes. Keep nominal candidate identities and frequency ranking fixed; recheck
full-duty feasibility at each stress. The four nominal plus two additional
stress cases make six distinct cells per date.

## What the numbers mean

Reachability uses 60 minutes. The duration objective caps every query at 90
minutes, including an unavailable query's penalty. Report lost/restored counts,
signed capped-duration changes, improved queries and actual bus-hours together.
Query-minutes per bus-hour describe this fixed workload; they are not financial
returns or passenger savings.

Identify the nominal impacted cohort before recovery and preserve it across
budgets and stresses. Separate gains among that cohort from gains among other
queries. Also identify savings for queries whose recovered arrival is after the
closure ends. Duties can end after the closure, and their full two-hour cost
remains counted.

The fixed example is Fairfield platform 2 to Central platform 1 at the cutoff.
It is retained even if that particular query gains nothing.

## Calculation and verification

The numerical routing/recovery engine remains unchanged. A reviewed scoring-only
projection retains all complete source trips needed for any arrival within the
90-minute objective, plus complete source witnesses for candidate patterns and
scenario segments. Nonnegative movement and walking times preserve all scored
paths. Selected policies are always rerouted on the full effective timetable
for published raw durations and legs.

Before confirmation, a small exhaustive boundary fixture and real development
zero/two-hour comparisons established identical objectives, selected duties,
query rows and full published routes. A separate checker recalculates metrics
and source/duty feasibility without using the producer's reporting helpers.
New public results require independent reconciliation, clean offline reproduction
and release checks before deployment.

## Interpretation limits

The source-fixed route set is broader than the original replay pilot and remains
a selected network. Walking access is incomplete and uncalibrated. Timetable
predictions are not measured arrivals. The model does not establish passenger
demand, crowding, spare vehicles, depot/driver positioning or financial viability.
Existing buses may provide good travel-time alternatives while having insufficient
real capacity; this model cannot settle that operational question.

Recorded dates are correlated examples, not independent passenger samples.
Realistic small or null recovery results will remain in the report.

## Results and reproduction

Corrected-network development and confirmation calculations are pending. This
method record is not evidence of a recovery benefit or completed publication.
