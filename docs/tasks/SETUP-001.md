# SETUP-001 — Establish project scaffolding and working rules

## Status and owner

- Status: Complete
- Owner: Implementation helper (GPT-6 Luna / max)
- Reviewer: Root coordinator

## Model and reasoning

- Requested model: GPT-6 Luna (`gpt-6-luna`)
- Reasoning effort: max

## Approved specification and decisions

- Establish the private, cross-platform Brisbane Transport Resilience Lab scaffold for real bus and rail replay around Fairfield/Annerley, South Bank, and CBD, with clearly hypothetical disruption and recovery scenarios.
- Use the accepted stack: Python, pandas, DuckDB, Parquet, Postgres/PostGIS, Redpanda, FastAPI, React/JavaScript/Vite, MapLibre, Docker Compose, and GitHub Actions.
- Preserve the user-approved 12-stage sequence and release gates in `docs/IMPLEMENTATION_CHECKLIST.md`.
- Keep `docs/CONTRACTS.md` and `docs/DECISIONS.md` coordinator-owned; do not add implementation source, dependency choices, or Compose in this task.
- The accepted plan authorizes public release after the technical/data gates pass. Do not add another visibility-authorization request.

## Required inputs and dependencies

- Inputs: accepted project purpose, stack, routing budgets, platform requirement, and release conditions supplied by the coordinator.
- Dependencies: no implementation dependencies; this task is setup and documentation only.
- Data status: a real source archive was acquired separately for audit. No feed was ingested or validated by this task.

## Files owned

- `.codex/config.toml`
- `.codex/agents/coordinator.toml`
- `.codex/agents/integration.toml`
- `.codex/agents/implementation.toml`
- `.gitignore`, `.gitattributes`, `AGENTS.md`, `README.md`
- `docs/IMPLEMENTATION_CHECKLIST.md`
- `docs/HANDOFF_TEMPLATE.md`
- `docs/tasks/SETUP-001.md`
- Empty directory markers under `services/resilience/`, `frontend/src/`, `tests/`, `data/`, `configs/`, `scripts/`, and `.github/workflows/`

## Expected output

- Codex project configuration and three role-specific custom-agent TOML files with explicit model and reasoning values.
- Working rules for ownership, approval before implementation, cross-platform changes, data/evidence truth, task schema, and escalation.
- An honest README, portable ignore and line-ending rules, exact 12-stage checklist, release gates, handoff template, and requested empty project folders.

## Acceptance checks

- [x] Python 3.11 `tomllib` parsed `.codex/config.toml` and all three agent TOML files; assertions confirmed the requested model and reasoning values, agent enablement, concurrency limit, required fields, and current documented defaults. This checks TOML syntax and values; it does not by itself verify that the running Codex app accepts the configuration schema.
- [x] Ignore-rule inspection passed for secrets, runtime, raw data, and the separately acquired `data/bootstrap/` archive; `.env.example` and `data/.gitkeep` remain unignored.
- [x] Checklist inspection confirmed exactly twelve ordered stages and nine release gates, all pending. Routing uses CSA versus OpenTripPlanner (OTP); uncalibrated service performance indicators remain outside this release.
- [x] README states that an archive was acquired for audit but not ingested or validated, and makes no analysis or demo claims.
- [x] Repository remains uncommitted; no implementation source, dependency manifest, or Compose file was added.

## Escalation issues

- Repeated failures and attempts: none.
- Observed limitation: no Codex app runtime/schema load was performed; only TOML parsing and value assertions were checked.
- Next owner: coordinator to review source audit and lock pilot details before implementation tasks proceed.
