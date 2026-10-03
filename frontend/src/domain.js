const REQUEST_OFFSETS = [0, 900, 1800, 2700, 3600];
const SCENARIO_KINDS = new Set([
  'trip_cancellation',
  'stop_unavailable',
  'corridor_closure',
  'additional_delay',
]);

export function makeFixedRequests({ snapshotId, originStopId, destinationStopId, snapshotS }) {
  if (!originStopId || !destinationStopId) throw new Error('Choose an origin and destination first.');
  if (originStopId === destinationStopId) throw new Error('Choose two different stops.');
  if (!Number.isInteger(snapshotS) || snapshotS < 0) throw new Error('This recording has no usable service time.');

  return REQUEST_OFFSETS.map((offset, index) => ({
    request_id: `journey-${String(snapshotId).slice(0, 8)}-${index + 1}`,
    origin_stop_id: String(originStopId),
    destination_stop_id: String(destinationStopId),
    departure_s: snapshotS + offset,
  }));
}

export function makeScenario({ kind, target, snapshotS, delaySeconds = 600, scenarioId }) {
  if (!SCENARIO_KINDS.has(kind)) throw new Error('Choose a supported disruption type.');
  if (!Number.isInteger(snapshotS) || snapshotS < 0) throw new Error('This recording has no usable service time.');
  const interval = { start_s: snapshotS, end_s: snapshotS + 3600 };
  const common = { scenario_id: scenarioId, ...interval };

  if (kind === 'trip_cancellation' || kind === 'additional_delay') {
    if (!target?.trip_instance_id || !Number.isInteger(target.departure_s) || target.departure_s < snapshotS) {
      throw new Error('Choose a real trip that has not departed in this recording.');
    }
    if (kind === 'trip_cancellation') {
      return { ...common, kind, trip_instance_ids: [target.trip_instance_id] };
    }
    if (!Number.isInteger(delaySeconds) || delaySeconds <= 0) throw new Error('Added delay must be a positive number of seconds.');
    return { ...common, kind, trip_instance_ids: [target.trip_instance_id], additional_seconds: delaySeconds };
  }

  if (kind === 'stop_unavailable') {
    if (!target?.stop_id || target.active_boardings <= 0) throw new Error('Choose a stop with recorded service.');
    return { ...common, kind, stop_ids: [target.stop_id] };
  }

  if (!target?.from_stop_id || !target?.to_stop_id) throw new Error('Choose an actual adjacent service segment.');
  return {
    ...common,
    kind,
    segments: [{
      from_stop_id: target.from_stop_id,
      to_stop_id: target.to_stop_id,
      bidirectional: true,
    }],
  };
}

export function makeExperimentPayload({ snapshotId, requests, scenario, budgetBusHours }) {
  if (!snapshotId) throw new Error('Choose a recording first.');
  if (!Array.isArray(requests) || requests.length === 0) throw new Error('At least one test journey is required.');
  if (![0, 2, 4, 8].includes(budgetBusHours)) throw new Error('Choose a supported bus-hour budget.');
  return {
    snapshot_id: snapshotId,
    requests,
    scenarios: [scenario],
    budget_bus_hours: budgetBusHours,
  };
}

export function makeVehicleCollection(display) {
  return {
    type: 'FeatureCollection',
    features: (display?.vehicles ?? []).filter((vehicle) =>
      Number.isFinite(vehicle.longitude) && Number.isFinite(vehicle.latitude),
    ).map((vehicle) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [vehicle.longitude, vehicle.latitude] },
      properties: { ...vehicle },
    })),
  };
}

export function countVehicleQuality(vehicles = []) {
  return vehicles.reduce((counts, vehicle) => {
    const quality = ['fresh', 'stale', 'unmatched', 'unknown'].includes(vehicle.quality)
      ? vehicle.quality
      : 'unknown';
    counts[quality] += 1;
    return counts;
  }, { fresh: 0, stale: 0, unmatched: 0, unknown: 0 });
}

export function eligibleStops(choices, catalog) {
  const stops = choices?.stops ?? [];
  const pilot = catalog?.pilot ?? {};
  const busSeeds = new Set(pilot.bus_seed_stop_ids ?? []);
  const platformSeeds = new Set(pilot.platform_seed_stop_ids ?? []);
  const modeStops = { bus: new Set(), rail: new Set() };

  for (const trip of choices?.trips ?? []) {
    const mode = String(trip.mode ?? '').toLowerCase();
    if (!modeStops[mode]) continue;
    for (const stopId of trip.stop_ids ?? [trip.from_stop_id, trip.to_stop_id]) {
      if (stopId) modeStops[mode].add(String(stopId));
    }
  }

  const active = stops.filter((stop) => stop.active_boardings > 0);
  const busOrigins = active.filter((stop) => modeStops.bus.has(String(stop.stop_id))
    && (!busSeeds.size || busSeeds.has(String(stop.stop_id))));
  const railOrigins = active.filter((stop) => modeStops.rail.has(String(stop.stop_id))
    && (!platformSeeds.size || platformSeeds.has(String(stop.stop_id))));
  const origins = [...new Map([...busOrigins, ...railOrigins]
    .map((stop) => [String(stop.stop_id), stop])).values()];
  const railDestinations = active.filter((stop) => modeStops.rail.has(String(stop.stop_id))
    && (!platformSeeds.size || platformSeeds.has(String(stop.stop_id))));
  const cityBusPattern = /\b(?:queen street|adelaide street|cultural centre|south bank busway|central station|roma street station|city hall|anzac square|king george square|albert street)\b/i;
  const cityBusDestinations = active.filter((stop) => modeStops.bus.has(String(stop.stop_id))
    && cityBusPattern.test(stop.name ?? ''));
  const destinations = [...new Map([...railDestinations, ...cityBusDestinations]
    .map((stop) => [String(stop.stop_id), stop])).values()];

  const originPriority = (stop) => /fairfield|annerley/i.test(stop.name ?? '') ? 0 : 1;
  const destinationPriority = (stop) => /south bank|cultural centre|queen street|central station|roma street station|city hall|anzac square|king george square|albert street/i.test(stop.name ?? '') ? 0 : 1;
  origins.sort((a, b) => originPriority(a) - originPriority(b) || a.name.localeCompare(b.name) || a.stop_id.localeCompare(b.stop_id));
  destinations.sort((a, b) => destinationPriority(a) - destinationPriority(b) || a.name.localeCompare(b.name) || a.stop_id.localeCompare(b.stop_id));
  return { origins, destinations, activeStops: active };
}

export function defaultSnapshotIndex(snapshots = []) {
  if (!snapshots.length) return -1;
  // A recording with no realtime receipt has no source vehicle positions.
  // Prefer the newest capture with a realtime feed, while keeping missing-feed
  // captures available on the replay timeline.
  for (let index = snapshots.length - 1; index >= 0; index -= 1) {
    if (snapshots[index]?.quality?.realtime_status !== 'missing') return index;
  }
  return snapshots.length - 1;
}

export function prioritizeTripsForOrigin(trips = [], originStopId) {
  const origin = String(originStopId ?? '');
  return [...trips].sort((left, right) => {
    const leftServesOrigin = (left.stop_ids ?? [left.from_stop_id, left.to_stop_id])
      .some((id) => String(id) === origin);
    const rightServesOrigin = (right.stop_ids ?? [right.from_stop_id, right.to_stop_id])
      .some((id) => String(id) === origin);
    return Number(rightServesOrigin) - Number(leftServesOrigin)
      || left.departure_s - right.departure_s
      || String(left.trip_instance_id).localeCompare(String(right.trip_instance_id));
  });
}

export function routeNameById(network) {
  const routes = new Map();
  for (const feature of network?.features ?? []) {
    const properties = feature.properties ?? {};
    if (properties.kind !== 'shape' || !properties.route_short_name) continue;
    const groupedRouteIds = Array.isArray(properties.route_ids) ? properties.route_ids : [properties.route_ids].filter(Boolean);
    const routeIds = [...new Set([properties.route_id, ...groupedRouteIds]
      .filter((routeId) => routeId != null && String(routeId).length > 0).map(String))];
    for (const routeId of routeIds) routes.set(routeId, {
      shortName: String(properties.route_short_name),
      name: String(properties.name ?? ''),
      mode: String(properties.mode ?? ''),
    });
  }
  return routes;
}

export function isWeekdayMorningSnapshot(snapshot) {
  if (!snapshot?.snapshot_at || !Number.isFinite(Date.parse(snapshot.snapshot_at))) return false;
  const parts = new Intl.DateTimeFormat('en-AU', {
    timeZone: 'Australia/Brisbane',
    weekday: 'short',
    hour: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date(snapshot.snapshot_at));
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  const hour = Number(values.hour);
  return ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'].includes(values.weekday) && hour >= 6 && hour < 12;
}

export function formatServiceTime(serviceDate, serviceSeconds) {
  const date = new Date(`${serviceDate}T00:00:00+10:00`);
  date.setTime(date.getTime() + serviceSeconds * 1000);
  return new Intl.DateTimeFormat('en-AU', {
    timeZone: 'Australia/Brisbane',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
}

export function formatBrisbaneTimestamp(value, { dateStyle = 'medium', timeStyle = 'short' } = {}) {
  if (!value) return 'Not recorded';
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return 'Not recorded';
  return new Intl.DateTimeFormat('en-AU', {
    dateStyle,
    timeStyle,
    timeZone: 'Australia/Brisbane',
  }).format(date);
}

export function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '—';
  const minutes = Math.round(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return hours ? `${hours}h ${String(remainder).padStart(2, '0')}m` : `${minutes} min`;
}

export function formatPercent(value) {
  return value == null || !Number.isFinite(value) ? '—' : `${Math.round(value * 100)}%`;
}

export function humanLabel(value) {
  return String(value ?? 'unknown').replaceAll('_', ' ');
}
