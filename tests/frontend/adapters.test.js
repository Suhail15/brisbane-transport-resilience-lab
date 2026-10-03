import test from 'node:test';
import assert from 'node:assert/strict';
import { gzipSync } from 'node:zlib';
import { AdapterError, createLocalAdapter, createStaticAdapter } from '../../frontend/src/api.js';
import {
  defaultSnapshotIndex,
  eligibleStops,
  isWeekdayMorningSnapshot,
  makeExperimentPayload,
  makeFixedRequests,
  makeScenario,
  prioritizeTripsForOrigin,
  routeNameById,
} from '../../frontend/src/domain.js';

function byteResponse(value, status = 200, headers = {}) {
  const bytes = Buffer.from(value);
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get(name) { return headers[name.toLowerCase()] ?? null; } },
    async arrayBuffer() { return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength); },
    async json() { return JSON.parse(bytes.toString('utf8')); },
  };
}

function jsonResponse(body, status = 200, headers = {}) {
  return byteResponse(JSON.stringify(body), status, headers);
}

test('local adapter maps approved paths and sends the immutable experiment shape', async () => {
  const calls = [];
  const adapter = createLocalAdapter({
    baseUrl: 'http://api.example/v1/',
    fetcher: async (url, options) => {
      calls.push({ url, options });
      if (url.endsWith('/catalog')) return jsonResponse({ version: 1, snapshots: [] });
      if (url.endsWith('/network?snapshot_id=snap%2Fone')) return jsonResponse({ type: 'FeatureCollection', features: [] });
      if (url.endsWith('/snapshots/snap%2Fone/display')) return jsonResponse({ snapshot_id: 'snap/one', vehicles: [] });
      if (url.endsWith('/snapshots/snap%2Fone/choices')) return jsonResponse({ snapshot_id: 'snap/one', stops: [], trips: [], segments: [] });
      if (url.endsWith('/experiments')) return jsonResponse({ run_id: 'run-1', status: 'queued' }, 202);
      return jsonResponse({ detail: 'unexpected path' }, 404);
    },
  });

  await adapter.getCatalog();
  await adapter.getNetwork('snap/one');
  await adapter.getDisplay('snap/one');
  await adapter.getChoices('snap/one');
  const payload = { snapshot_id: 'snap/one', requests: [{ request_id: 'journey-1' }], scenarios: [{ kind: 'trip_cancellation' }], budget_bus_hours: 0 };
  const queued = await adapter.createRun(payload);

  assert.equal(queued.run_id, 'run-1');
  assert.deepEqual(calls.map(({ url }) => url), [
    'http://api.example/v1/catalog',
    'http://api.example/v1/network?snapshot_id=snap%2Fone',
    'http://api.example/v1/snapshots/snap%2Fone/display',
    'http://api.example/v1/snapshots/snap%2Fone/choices',
    'http://api.example/v1/experiments',
  ]);
  assert.equal(calls[4].options.method, 'POST');
  assert.deepEqual(JSON.parse(calls[4].options.body), payload);
});

test('adapter failures retain the endpoint status and useful API detail', async () => {
  const adapter = createLocalAdapter({
    fetcher: async () => jsonResponse({ detail: 'Scenario stop is outside the recorded snapshot.' }, 422),
  });

  await assert.rejects(adapter.getCatalog(), (error) => {
    assert.ok(error instanceof AdapterError);
    assert.equal(error.status, 422);
    assert.match(error.message, /outside the recorded snapshot/);
    return true;
  });
});

test('static adapter lazily loads compact bundle DTOs, exact network URL, and prepared run summaries', async () => {
  const requests = [];
  const network = {
    type: 'FeatureCollection',
    features: [{ type: 'Feature', geometry: { type: 'LineString', coordinates: [[153, -27], [153.01, -27.01]] }, properties: { kind: 'shape', route_id: '100-5146', route_ids: ['100-5146', '100-5065'], route_short_name: '100', mode: 'bus' } }],
  };
  const sourceSnapshot = {
    snapshot_id: 'snapshot-fixture',
    snapshot_at: '2026-10-02T04:19:40Z',
    service_date: '2026-10-02',
    quality: { realtime_status: 'verified' },
    network_url: 'networks/fixture.geojson.gz',
    display_url: 'snapshots/snapshot-fixture/display.json',
    choices_url: 'snapshots/snapshot-fixture/choices.json',
  };
  const preparedRunSummary = {
    run_id: 'run-fixture', status: 'completed', snapshot_id: sourceSnapshot.snapshot_id,
    source_snapshot_at: sourceSnapshot.snapshot_at, journey_set_version: 'fixture-journeys-v1',
    request_count: 2, scenario_summaries: [{ kind: 'trip_cancellation', target_ids: ['trip-fixture'], interval: { start_s: 50000, end_s: 53600 }, readable_label: 'Cancel fixture trip' }],
    budget_bus_hours: 2, used_bus_hours: 2, sensitivity_seconds: 300, hypothetical: true,
    legacy_unversioned: false, reproducible: true, url: 'experiments/run-fixture.json',
    request_set_sha256: 'request-hash', scenario_set_sha256: 'scenario-hash', candidate_set_sha256: 'candidate-hash',
    assumptions: { bus_running_time_sensitivity_seconds: 300 }, search_method: 'greedy_bounded_swap',
    max_swap_evaluations: 128, objective_version: 'fixture-objective-v1', candidate_selection_version: 'fixture-candidates-v1',
    aggregate_metrics: { request_count: 2, restored_count: 1 },
  };
  const bundleFiles = {
    'catalog.json': { version: 1, timezone: 'Australia/Brisbane', preview_only: true, pilot: { bus_seed_stop_ids: ['fairfield-stop'], platform_seed_stop_ids: ['south-bank-platform'] }, snapshots: [sourceSnapshot] },
    [sourceSnapshot.display_url]: { snapshot_id: sourceSnapshot.snapshot_id, vehicles: [{ entity_id: 'vehicle-fixture', longitude: 153, latitude: -27, quality: 'fresh' }] },
    [sourceSnapshot.choices_url]: {
      snapshot_id: sourceSnapshot.snapshot_id,
      stops: [
        { stop_id: 'fairfield-stop', name: 'Fairfield bus stop', active_boardings: 3 },
        { stop_id: 'south-bank-platform', name: 'South Bank platform 1', active_boardings: 4 },
        { stop_id: 'inactive-fairfield-platform', name: 'Fairfield platform 1', active_boardings: 0 },
      ],
      trips: [
        { trip_instance_id: 'trip-fixture', mode: 'bus', stop_ids: ['fairfield-stop'], departure_s: 52000 },
        { trip_instance_id: 'train-fixture', mode: 'rail', stop_ids: ['south-bank-platform'], departure_s: 52100 },
      ],
      segments: [],
    },
    'experiments/index.json': { runs: [preparedRunSummary] },
    'experiments/run-fixture.json': { run_id: 'run-fixture', status: 'completed', input: { scenarios: [{ kind: 'trip_cancellation', trip_instance_ids: ['trip-fixture'], start_s: 50000, end_s: 53600 }] }, result: { budget_bus_hours: 2 } },
  };
  const adapter = createStaticAdapter({
    bundleUrl: './bundle/',
    pageUrl: 'http://localhost/project/index.html',
    fetcher: async (url) => {
      requests.push(url);
      const relative = new URL(url).pathname.replace('/project/bundle/', '');
      if (relative === sourceSnapshot.network_url) return byteResponse(gzipSync(Buffer.from(JSON.stringify(network))));
      if (Object.hasOwn(bundleFiles, relative)) return jsonResponse(bundleFiles[relative]);
      return jsonResponse({ detail: 'missing bundle fixture file' }, 404);
    },
  });

  const catalog = await adapter.getCatalog();
  assert.deepEqual(requests, ['http://localhost/project/bundle/catalog.json']);
  const snapshot = catalog.snapshots[defaultSnapshotIndex(catalog.snapshots)];
  assert.equal(snapshot.snapshot_id, sourceSnapshot.snapshot_id);
  const display = await adapter.getDisplay(snapshot.snapshot_id);
  assert.equal(display.snapshot_id, snapshot.snapshot_id);
  assert.equal(display.vehicles[0].entity_id, 'vehicle-fixture');
  assert.equal(requests.includes(`http://localhost/project/bundle/${snapshot.display_url}`), true);
  assert.equal(requests.includes(`http://localhost/project/bundle/${snapshot.choices_url}`), false);
  const choices = await adapter.getChoices(snapshot.snapshot_id);
  const decodedNetwork = await adapter.getNetwork(snapshot.snapshot_id);
  assert.ok(choices.trips.length > 0);
  assert.ok(decodedNetwork.features.some((feature) => feature.properties.kind === 'shape'));
  const pilotStops = eligibleStops(choices, catalog);
  assert.equal(pilotStops.origins.some((stop) => stop.stop_id === 'south-bank-platform'), true);
  assert.equal(pilotStops.origins.some((stop) => stop.stop_id === 'inactive-fairfield-platform'), false);
  assert.equal(requests.includes(`http://localhost/project/bundle/${snapshot.network_url}`), true);
  const runs = await adapter.getRuns();
  assert.equal(runs.length, 1);
  assert.equal(runs[0].scenario_summaries[0].readable_label, 'Cancel fixture trip');
  assert.equal(runs[0].aggregate_metrics.restored_count, 1);
  assert.equal(requests.includes('http://localhost/project/bundle/experiments/run-fixture.json'), false);
  assert.equal((await adapter.getRun('run-fixture')).result.budget_bus_hours, 2);
  assert.equal(requests.includes('http://localhost/project/bundle/experiments/run-fixture.json'), true);
});

test('scenario and fixed-journey builders keep exact contract fields and interval rules', () => {
  const requests = makeFixedRequests({ snapshotId: '35f84816f6e2', originStopId: '10530', destinationStopId: '600008', snapshotS: 51580 });
  const scenario = makeScenario({
    kind: 'additional_delay',
    target: { trip_instance_id: '2026-10-02:route-trip', departure_s: 52000 },
    snapshotS: 51580,
    delaySeconds: 600,
    scenarioId: 'scenario-delay-1',
  });
  const payload = makeExperimentPayload({ snapshotId: '35f84816f6e2', requests, scenario, budgetBusHours: 4 });

  assert.deepEqual(requests.map((request) => request.departure_s), [51580, 52480, 53380, 54280, 55180]);
  assert.equal(requests.length, 5);
  assert.ok(requests.every((request) => !Object.hasOwn(request, 'od_weight')));
  assert.deepEqual(scenario, {
    scenario_id: 'scenario-delay-1', kind: 'additional_delay', start_s: 51580, end_s: 55180,
    trip_instance_ids: ['2026-10-02:route-trip'], additional_seconds: 600,
  });
  assert.equal(payload.budget_bus_hours, 4);
  assert.deepEqual(payload.scenarios, [scenario]);
  assert.equal(Object.hasOwn(payload, 'engine_snapshot'), false);
  assert.throws(() => makeScenario({ kind: 'trip_cancellation', target: { trip_instance_id: 'past', departure_s: 50000 }, snapshotS: 51580, scenarioId: 'bad' }), /not departed/);
});

test('initial frame and journey controls favor source-backed service in the pilot', () => {
  const snapshots = [
    { snapshot_at: '2026-10-02T04:04:00Z', quality: { realtime_status: 'degraded' } },
    { snapshot_at: '2026-10-02T04:15:00Z', quality: { realtime_status: 'missing' } },
  ];
  assert.equal(defaultSnapshotIndex(snapshots), 0);

  const choices = {
    stops: [
      { stop_id: 'fairfield', name: 'Fairfield bus stop', active_boardings: 3 },
      { stop_id: 'city-bus', name: 'Adelaide Street Stop 18 at City Hall', active_boardings: 2 },
      { stop_id: 'city-rail', name: 'Central station, platform 1', active_boardings: 4 },
      { stop_id: 'inactive-rail', name: 'Fairfield station, platform 1', active_boardings: 0 },
    ],
    trips: [
      { trip_instance_id: 'other', mode: 'bus', stop_ids: ['elsewhere'], departure_s: 10 },
      { trip_instance_id: 'origin-trip', mode: 'bus', stop_ids: ['fairfield', 'city-bus'], departure_s: 20 },
      { trip_instance_id: 'rail-trip', mode: 'rail', stop_ids: ['city-rail', 'inactive-rail'], departure_s: 30 },
    ],
  };
  const eligible = eligibleStops(choices, { pilot: { bus_seed_stop_ids: ['fairfield'], platform_seed_stop_ids: ['city-rail'] } });
  assert.deepEqual(new Set(eligible.origins.map((stop) => stop.stop_id)), new Set(['fairfield', 'city-rail']));
  assert.equal(eligible.origins[0].stop_id, 'fairfield');
  assert.equal(eligible.origins.some((stop) => stop.stop_id === 'inactive-rail'), false);
  assert.deepEqual(new Set(eligible.destinations.map((stop) => stop.stop_id)), new Set(['city-bus', 'city-rail']));
  assert.equal(prioritizeTripsForOrigin(choices.trips, 'fairfield')[0].trip_instance_id, 'origin-trip');
  assert.equal(prioritizeTripsForOrigin(choices.trips, 'city-rail')[0].trip_instance_id, 'rail-trip');

  const routes = routeNameById({ features: [{ properties: { kind: 'shape', route_id: '100-5146', route_ids: ['100-5146', '100-5065'], route_short_name: '100', name: 'Forest Lake/Inala - City', mode: 'bus' } }] });
  assert.equal(routes.get('100-5065').shortName, '100');
});

test('weekday morning labels use Brisbane timestamp, separate from window completeness', () => {
  assert.equal(isWeekdayMorningSnapshot({ snapshot_at: '2026-10-02T01:59:00Z' }), true);
  assert.equal(isWeekdayMorningSnapshot({ snapshot_at: '2026-10-02T02:00:00Z' }), false);
  assert.equal(isWeekdayMorningSnapshot({ snapshot_at: '2026-10-03T01:00:00Z' }), false);
});

test('static JSON reader decompresses gzip by magic bytes and does not double-decode fetch output', async () => {
  const expected = { network: 'source geometry', features: [{ id: 'shape-1' }] };
  const compressed = gzipSync(Buffer.from(JSON.stringify(expected)));
  const compressedAdapter = createStaticAdapter({ fetcher: async () => byteResponse(compressed) });
  assert.deepEqual(await compressedAdapter.getCatalog(), expected);

  const originalDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'DecompressionStream');
  Object.defineProperty(globalThis, 'DecompressionStream', {
    configurable: true,
    writable: true,
    value: class UnexpectedDecompression { constructor() { throw new Error('should not decode twice'); } },
  });
  try {
    const alreadyDecodedAdapter = createStaticAdapter({
      fetcher: async () => jsonResponse(expected, 200, { 'content-encoding': 'gzip' }),
    });
    assert.deepEqual(await alreadyDecodedAdapter.getCatalog(), expected);
  } finally {
    Object.defineProperty(globalThis, 'DecompressionStream', originalDescriptor);
  }
});

test('static JSON reader explains when gzip support is unavailable', async () => {
  const compressed = gzipSync(Buffer.from(JSON.stringify({ version: 1 })));
  const originalDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'DecompressionStream');
  Object.defineProperty(globalThis, 'DecompressionStream', { configurable: true, writable: true, value: undefined });
  try {
    const adapter = createStaticAdapter({ fetcher: async () => byteResponse(compressed) });
    await assert.rejects(adapter.getCatalog(), (error) => {
      assert.ok(error instanceof AdapterError);
      assert.match(error.message, /cannot open the compressed map geometry/);
      return true;
    });
  } finally {
    Object.defineProperty(globalThis, 'DecompressionStream', originalDescriptor);
  }
});
