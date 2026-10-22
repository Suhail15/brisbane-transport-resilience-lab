# Project working instructions

## Purpose and current state

Build the Brisbane Transport Resilience Lab: a replay and scenario tool for real bus and rail service around Fairfield and Annerley, South Bank, and Brisbane CBD. The replay will use sourced operating data. Disruptions and replacement-bus recovery plans are hypothetical scenarios constrained by documented service and network assumptions.

The core engine, source archive, local API and operational stores are implemented. Six complete morning collections support the frozen final evaluation on 19/20/21 October 2026: 72 recorded replay frames and 54 completed scenario/budget/stress cases over 100 fixed requests per date. Independent reconciliation and exact offline reproduction passed all 54 cases. Development afternoon findings are preserved separately. Release v1.0.0 is public, with candidate CI, all eleven local gates, Pages deployment and unauthenticated public access verified on 22 October 2026; see docs/releases/v1.0.0.md. Later documentation commits do not change the immutable released site or approve changed calculation code. Read current task handoffs and release evidence before claiming a release is complete. Keep planned work, source observations, derived measures, and hypothetical scenario assumptions clearly labeled.

The accepted stack is Python, pandas, DuckDB, Parquet, Postgres/PostGIS, Redpanda, FastAPI, React with JavaScript and Vite, MapLibre, Docker Compose, and GitHub Actions. Tested Python dependencies are pinned in `requirements.lock.txt`; frontend dependencies use a separate lock. Approved interfaces and analytical assumptions are in `docs/CONTRACTS.md`, `docs/METHODOLOGY.md` and `docs/DECISIONS.md`. The project uses one repository on macOS and Windows.

## Coordination and review

- Keep no more than three project agents active at once, including the root coordinator. The project configuration allows two concurrent subagent threads in addition to the root.
- The coordinator uses GPT-6.1-sol with max reasoning. It owns architecture direction and the shared `docs/CONTRACTS.md` and `docs/DECISIONS.md` files.
- Before implementation begins, the coordinator must review and approve the relevant data contracts, API/event boundaries, replay semantics, and analysis assumptions. A task must point to that approval or explicitly be limited to scaffolding/planning.
- OpenTripPlanner (OTP) is the independent routing engine used alongside CSA; OTP always means OpenTripPlanner here and only appears in independent route checks. Service performance indicators are outside this release until separately calibrated.
- Integration work uses GPT-6.1-sol with medium reasoning. Bounded implementation work uses GPT-6-luna with max reasoning. Keep each task within its assigned files and acceptance criteria.
- Do not edit another task's owned files or shared contracts/decisions without coordinator direction. Coordinate overlapping changes before editing.
- After two repeated failures on the same issue, stop retrying and escalate with the attempted steps, observed errors, and evidence needed to proceed.

## Task brief and handoff format

Every task brief under `docs/tasks/` must use these exact headings, with concrete paths and observable acceptance criteria:

1. **Model and reasoning**
2. **Approved specification and decisions**
3. **Required inputs and dependencies**
4. **Files owned** (exact paths or a narrow directory scope)
5. **Expected output**
6. **Acceptance checks** (observable, bounded, and evidence-backed)
7. **Escalation issues** (attempted steps, observed errors, and evidence needed to proceed)

Include the task ID, title, status, and owner above these sections. Record actual check outcomes under **Acceptance checks**; never copy an expected result into the evidence section as if it had happened.

Use `docs/HANDOFF_TEMPLATE.md` for final implementation handoffs. Mark a task complete only after its acceptance checks have been checked and evidence recorded.

## Data, analysis, and reporting rules

- Record source name, publisher, retrieval time, coverage period, licence/terms, and content hash for each real feed or dataset before relying on it.
- Keep original source files local and out of Git. Commit only reviewed code, schema/manifests, and deliberately small fixtures whose provenance and licence permit redistribution.
- Label each value as sourced observation, derived measure, scenario input, or scenario output. Scenario outputs are not observed service outcomes.
- Do not invent feed coverage, historical service behavior, passenger impacts, recovery feasibility, or independent OTP route-comparison results. Link each result to its input snapshot, method, and reproducible run.
- Keep local timestamps in `Australia/Brisbane` explicit at input and display boundaries; preserve source timestamps and timezone metadata through ingestion.
- Enforce the recorded-received-time cutoff for historical replay: only inputs received on or before the replay's recorded `as_of` cutoff may affect that run. Exclude later-arriving information to prevent hindsight leakage.
- Lock the approved pilot routing budgets before coding: maximum walk distance 600 m, walking speed 1.2 m/s, transfer slack 300 seconds, and at most three transfers. Record any later proposed change as a reviewed decision.
- Treat operational constraints for replacement buses as assumptions until supported by source data or a documented, reviewed rule. Record capacity, availability, route access, and transfer assumptions where applicable.
- Obtain and record licence review before bundling or publishing any data. Do not expose credentials, personal information, or unreviewed raw feeds.

## Cross-platform repository rules

- Use repository-relative paths and portable scripts. Do not hard-code a machine-specific home directory, drive letter, shell, or absolute data path.
- Keep committed text files in LF form. Do not normalize or reformat unrelated files during a task.
- Keep generated runtime state, raw data, local databases, caches, virtual environments, and credentials out of version control.
- Make reproducibility evidence usable on macOS and Windows where the toolchain permits; state any platform-specific limitation in the task handoff.

## Release discipline

Release v1.0.0 passed its gates and is public. Keep additional source archives, data exports and new release candidates unpublished until their applicable gates are complete and independently reviewable. The accepted project plan authorizes publication after those gates pass; do not add another visibility-approval step. Verify actual public bytes and access after deployment. Update the checklist only with evidence for work actually completed.
