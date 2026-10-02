# DATA-001 / INTEGRATE-001

Title: real source pipeline and local integration
Status: local integration packet ready; release and OTP verification pending
Owner: integration agent
Reviewer: root coordinator

## Model and reasoning

GPT-6.1 Sol, medium reasoning, explicitly dispatched. No other agents spawned.

## Approved specification and decisions

Frozen docs/CONTRACTS.md, docs/DECISIONS.md, resilience/contracts.py. ARCH-001 approved
separate display/choices DTOs, actual edge-only walking length with snap diagnostics,
affected-journey candidate helper, and progress/cancellation hooks. Public snapshots
must be compact and filtered to three selected complete real morning dates/windows.

## Required inputs and dependencies

Acquired real GTFS, development afternoon GTFS-RT, July OD CSV/Readme, OSM highway XML.
Python3.11 lock packages, Docker PostGIS/Redpanda. Official Java25/OTP2.10 independent
reference supplied by coordinator. Source originals ignored; receipt cutoff enforced.

## Files owned

pyproject.toml; requirements*.txt; Dockerfile; compose*.yaml; .env.example; configs/**;
services/resilience/{__init__.py,settings.py,cli.py,api.py,db.py,pipeline/**}; scripts/**;
.github/workflows/**; tests/integration/**;
docs/{DATA_AUDIT.md,SOURCES.md,SETUP.md,COLLECTION.md,API.md,INTEGRATION.md};
docs/tasks/DATA-001.md.

## Expected output

Operational recorder/archive/outbox, audited full-trip pilot normalization, calendar
replay, entity quality/join diagnostics, actual OSM walking paths, PostGIS spatial store,
DuckDB/Parquet queries, async FastAPI, portable startup/CI, compact static exports,
strict release gate and independent OTP evidence.

## Acceptance checks

- Actual GTFS audit: 73 line names,539 route versions,20801 full trips,617584 stop times;
  2201 active trips on2026-10-02;360 exact-terminal source pattern pairs.
- First development snapshot persisted61607 movements in9.36s; walking incomplete
  and inactiveFairfieldplatforms preserved, no invented services/connectors.
- Root verified Docker services and Redpanda deliveries with0 pending outbox initially.
- Integration10tests passed(latest rerun) including actual PostGIS spatialquery; sourcecutoff,
  exceptions, unknownentitytimestamps and concurrent immutable dedup independently tested.
- API contracts docs/API.md ready; root health/catalog200; compactchoices/display approved.
- Official OTP graphbuild succeeded; separatesave/load resolvedstartupbug;6routequeriescompleted1exactagreement, discrepancygatefailed.
- Windows/Linux clean install and full CI remainunverified until actual remoteruns.
- Five morning windows and public licence/OTP/performance/staticdemogates remainpending.

## Escalation issues

PostGISARM image manifest absent: coordinator-approved linux/amd64 image emulation fix,
then liveDockerstartup succeeded. OTPtwo routequery attempts failed identically
Index1127outofboundsforlength0; separatebuild/save/loadfixedit. SixactualOTPcomparisonsnow
needdiscrepancyreview (1/6exactagreement); see docs/INTEGRATION.md, ownerroot/ARCH-001.
Translinkterms contact/publicnetworkapproval handling requires user-supplied contact
and authorized sending; no externalmessage sent. No public release requested/performed.
