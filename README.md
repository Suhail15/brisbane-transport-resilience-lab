# Brisbane Transport Resilience Lab

This project is planned as a way to replay real Brisbane bus and rail service around Fairfield and Annerley, South Bank, and the CBD, then explore hypothetical disruption and recovery scenarios. Any replacement-bus plan will need to respect documented assumptions about availability, capacity, access, and service constraints.

The intended stack is Python and pandas for data work, DuckDB and Parquet for local analysis, Postgres/PostGIS and Redpanda for spatial and event data, FastAPI for the service layer, and React, JavaScript, Vite, and MapLibre for the interface. Docker Compose and GitHub Actions are part of the planned development workflow. Architecture details and dependency versions have not yet been selected.

## Development status

This repository is the initial private development scaffold. A real source archive has been acquired for audit; it has not been ingested or validated. No analysis or demo result is available yet. Real observations and hypothetical scenario inputs will be identified separately as the project is built.

The project will remain private until its release gates are met. See the [implementation checklist](docs/IMPLEMENTATION_CHECKLIST.md) for the ordered work and evidence required before a demo can be shared.

## Project guidance

- [Working instructions](AGENTS.md)
- [Implementation checklist](docs/IMPLEMENTATION_CHECKLIST.md)
- [Task handoff template](docs/HANDOFF_TEMPLATE.md)
- [Initial scaffolding task](docs/tasks/SETUP-001.md)

## Repository layout

- `services/resilience/` — planned API and resilience-analysis service
- `frontend/src/` — planned interactive replay interface
- `tests/` — automated checks
- `data/` — local source and generated data locations; raw and runtime data stay out of Git
- `configs/` and `scripts/` — project configuration and reproducible workflows
- `docs/` — contracts, decisions, implementation stages, and task evidence
