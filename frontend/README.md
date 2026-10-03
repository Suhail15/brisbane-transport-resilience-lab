# Frontend

This is the local and static interface for the Brisbane Transport Resilience Lab.

## Local API preview

From this directory, install the pinned packages and start the interface:

```text
npm ci
npm run dev
```

Open `http://localhost:5173`. The default adapter reads `http://127.0.0.1:8000/v1`; start the API separately using the repository setup instructions. The interface shows a retry message and a switch to the static bundle when the API is unavailable.

## Prepared static bundle

```text
npm run dev:static
```

This serves the prepared `data/derived/demo` files as a view-only bundle. Existing display frames, choices, geometry, and completed runs are fetched on demand. A bundle with no saved experiment runs shows an empty state; it does not create example outcomes.

For the GitHub Pages project path, `npm run build:static` builds with static mode, packages only catalog metadata, source-matched network geometry, display frames, choices and completed runs, and defaults to `/brisbane-transport-resilience-lab/`. It omits full engine snapshots and the duplicate convenience network. Set `VITE_BASE_PATH` and `VITE_BUNDLE_URL` before running that script when the host path differs. Raw source files are not copied into the interface bundle.

## Checks

```text
npm test
npm run build
npm run build:static
```

The local replay uses one-hour scenarios from the selected snapshot, actual upcoming timetable entities, five equally weighted test journeys, and the four reviewed bus-hour budgets. Test journeys are not passenger demand.
