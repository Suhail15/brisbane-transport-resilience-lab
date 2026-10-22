import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReplayMap from './ReplayMap.jsx';
import { AdapterError, createAdapter } from './api.js';
import {
  countVehicleQuality,
  DEFAULT_RECOVERY_FILTERS,
  filterRecoveryRuns,
  recoveryFilterOptions,
  defaultSnapshotIndex,
  eligibleStops,
  formatBrisbaneTimestamp,
  formatDuration,
  formatPercent,
  formatServiceTime,
  humanLabel,
  isWeekdayMorningSnapshot,
  makeExperimentPayload,
  makeFixedRequests,
  makeScenario,
  prioritizeTripsForOrigin,
  routeNameById,
} from './domain.js';

const INITIAL_MODE = import.meta.env.VITE_DATA_MODE === 'static' ? 'static' : 'local';
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/v1';
const BUNDLE_URL = import.meta.env.VITE_BUNDLE_URL || './';
const BUDGETS = [0, 2, 4, 8];
const TRANSLINK_ATTRIBUTION = 'Contains public transport data provided by Translink (Department of Transport and Main Roads, Queensland) under CC BY 4.0. Translink does not endorse and is not affiliated with this independent project or its simulation outcomes.';
const NAV_ITEMS = [
  { id: 'replay', label: 'Network & replay', icon: 'map' },
  { id: 'impact', label: 'Disruption impact', icon: 'pulse' },
  { id: 'recovery', label: 'Recovery comparison', icon: 'arrows' },
  { id: 'evidence', label: 'Evidence', icon: 'document' },
];

function Icon({ name, size = 19 }) {
  const paths = {
    map: <><path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3z" /><path d="M9 3v15M15 6v15" /></>,
    pulse: <><path d="M3 12h4l3-8 4 16 3-8h4" /></>,
    arrows: <><path d="M4 8h13l-3-3m6 11H7l3 3" /></>,
    document: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6M8 13h8M8 17h8" /></>,
    play: <><path d="m7 4 13 8-13 8z" /></>,
    pause: <><path d="M8 5v14M16 5v14" /></>,
    left: <><path d="m15 18-6-6 6-6" /></>,
    right: <><path d="m9 18 6-6-6-6" /></>,
    refresh: <><path d="M20 7v5h-5" /><path d="M4 17v-5h5" /><path d="M5.6 9A7 7 0 0 1 18 6l2 6M4 12l2 6a7 7 0 0 0 12.4-3" /></>,
    close: <><path d="m6 6 12 12M18 6 6 18" /></>,
    check: <><path d="m5 12 4 4L19 6" /></>,
    alert: <><path d="M12 9v4m0 4h.01" /><path d="M10.3 3.9 2.8 17a2 2 0 0 0 1.7 3h15a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function ErrorNotice({ error, onRetry, onSwitch }) {
  if (!error) return null;
  return (
    <section className="notice notice-error" role="alert">
      <div className="notice-icon"><Icon name="alert" /></div>
      <div className="notice-copy">
        <strong>{error instanceof AdapterError ? error.message : error.message || 'The recording could not be loaded.'}</strong>
        <span>{error.mode === 'static'
          ? 'Check that this bundle includes the selected recording, then try again.'
          : 'Check that the local replay service is running at 127.0.0.1:8000, or open the prepared static bundle.'}</span>
        <div className="notice-actions">
          {onRetry && <button className="button button-small" onClick={onRetry}><Icon name="refresh" size={15} /> Try again</button>}
          {onSwitch && <button className="text-button" onClick={onSwitch}>Open static bundle</button>}
        </div>
      </div>
    </section>
  );
}

function Badge({ tone = 'neutral', children }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

function StatusPill({ value, label }) {
  const tones = { verified: 'good', fresh: 'good', complete: 'good', degraded: 'warning', stale: 'warning', incomplete: 'warning', missing: 'muted', unknown: 'muted', unmatched: 'muted' };
  return <span className={`status-pill status-${tones[value] || 'muted'}`}><span className="status-dot" />{label || humanLabel(value)}</span>;
}

function SectionHeading({ eyebrow, title, children, action }) {
  return (
    <div className="section-heading">
      <div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1>{children && <p>{children}</p>}</div>
      {action && <div className="section-action">{action}</div>}
    </div>
  );
}

function formatCount(value) {
  return Number.isFinite(value) ? new Intl.NumberFormat('en-AU').format(value) : '—';
}

function runScenarios(run) {
  const values = run.scenario_summaries ?? run.scenarios ?? run.input?.scenarios ?? [];
  return Array.isArray(values) ? values : values ? [values] : [];
}

function runScenarioLabel(scenario) {
  const kindLabels = {
    trip_cancellation: 'Trip cancellation',
    stop_unavailable: 'Stop unavailable',
    corridor_closure: 'Corridor closure',
    additional_delay: 'Added trip delay',
  };
  const kind = scenario.kind ?? scenario.type;
  const label = scenario.readable_label ?? scenario.label ?? kindLabels[kind] ?? (kind ? humanLabel(kind) : 'Scenario details unavailable');
  const targets = scenario.target_ids ?? scenario.trip_instance_ids ?? scenario.trip_ids ?? scenario.stop_ids
    ?? (scenario.target_id ? [scenario.target_id] : []);
  const targetList = Array.isArray(targets) ? targets : [targets];
  return targetList.length ? `${label} · ${targetList.join(', ')}` : label;
}

function runSummary(run, snapshots) {
  const snapshotId = run.snapshot_id ?? run.source_snapshot_id ?? run.metadata?.snapshot_id ?? run.input?.snapshot_id;
  const snapshot = snapshots.find((item) => item.snapshot_id === snapshotId);
  const sourceTime = run.source_snapshot_at ?? run.snapshot_at ?? run.metadata?.snapshot_at ?? run.input?.snapshot_at ?? snapshot?.snapshot_at;
  const scenarios = runScenarios(run);
  const scenarioLabels = scenarios.map(runScenarioLabel);
  const scenarioWindow = scenarios.map((scenario) => {
    const interval = scenario.interval ?? scenario;
    const start = interval.start_s;
    const end = interval.end_s;
    return Number.isInteger(start) && Number.isInteger(end) && snapshot?.service_date
      ? `${formatServiceTime(snapshot.service_date, start)}–${formatServiceTime(snapshot.service_date, end)}`
      : null;
  }).filter(Boolean).join(' · ');
  const metadata = run.metadata ?? {};
  const input = run.input ?? {};
  const sensitivity = run.sensitivity_seconds ?? run.bus_running_time_sensitivity_seconds
    ?? metadata.assumptions?.bus_running_time_sensitivity_seconds
    ?? input.assumptions?.bus_running_time_sensitivity_seconds;
  const budget = run.budget_bus_hours ?? run.budget ?? metadata.budget_bus_hours ?? input.budget_bus_hours;
  const usedBusHours = run.used_bus_hours ?? run.aggregate_metrics?.used_bus_hours;
  const metrics = run.aggregate_metrics ?? run.metrics ?? run.result?.plan?.evaluation?.metrics;
  const legacy = run.legacy_unversioned === true || run.reproducible === false;
  const hasSummary = scenarios.length > 0 || Number.isFinite(budget) || Number.isFinite(sensitivity)
    || run.journey_set_version || metrics;
  const requestCount = run.request_count ?? metrics?.request_count ?? input.requests?.length;
  const journeySetVersion = run.journey_set_version ?? metadata.journey_set_version ?? input.journey_set_version;
  const requestSetHash = run.request_set_sha256 ?? metadata.request_set_sha256;
  const scenarioSetHash = run.scenario_set_sha256 ?? metadata.scenario_set_sha256;
  const candidateSetHash = run.candidate_set_sha256 ?? metadata.candidate_set_sha256;
  const assumptions = run.assumptions ?? metadata.assumptions ?? input.assumptions;
  const searchLimits = {
    search_method: run.search_method ?? metadata.search_method ?? input.search_method,
    max_swap_evaluations: run.max_swap_evaluations ?? metadata.max_swap_evaluations ?? input.max_swap_evaluations,
    objective_version: run.objective_version ?? metadata.objective_version ?? input.objective_version,
    candidate_selection_version: run.candidate_selection_version ?? metadata.candidate_selection_version ?? input.candidate_selection_version,
  };
  const scenarioIdentity = scenarios.map((scenario) => ({
    kind: scenario.kind ?? scenario.type,
    target_ids: scenario.target_ids ?? scenario.trip_instance_ids ?? scenario.trip_ids ?? scenario.stop_ids ?? scenario.target_id,
    interval: scenario.interval ?? { start_s: scenario.start_s, end_s: scenario.end_s },
  }));
  const hasSearchLimits = Object.values(searchLimits).every((value) => value !== undefined && value !== null);
  const canGroup = Boolean(snapshotId && requestSetHash && scenarioSetHash && candidateSetHash
    && assumptions && hasSearchLimits && scenarios.length);
  const groupKey = canGroup ? JSON.stringify([
    snapshotId,
    requestSetHash,
    scenarioSetHash,
    candidateSetHash,
    assumptions,
    searchLimits,
    scenarioIdentity,
  ]) : null;
  return {
    snapshotId,
    sourceTime,
    serviceDate: snapshot?.service_date,
    scenarioKinds: scenarios.map((scenario) => scenario.kind ?? scenario.type).filter(Boolean),
    scenarioLabel: scenarioLabels.join(' · ') || (legacy ? 'Legacy recorded result' : 'Scenario summary not included'),
    scenarioWindow,
    budget,
    usedBusHours,
    sensitivity,
    requestCount,
    journeySetVersion,
    metrics,
    legacy,
    hasSummary,
    groupKey,
  };
}

function sensitivityLabel(seconds) {
  if (!Number.isFinite(seconds)) return 'Sensitivity not included';
  if (seconds === 0) return 'Base running time';
  return `Hypothetical bus running-time sensitivity +${Math.round(seconds / 60)} min`;
}

function serviceLabel(stop) {
  return `${stop.name} · ${stop.stop_id}`;
}

function arrivalGap(current, previous) {
  if (!current || !previous) return null;
  const seconds = Math.max(0, Math.round((Date.parse(current.snapshot_at) - Date.parse(previous.snapshot_at)) / 1000));
  if (!Number.isFinite(seconds)) return null;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return minutes ? `${minutes}m ${String(remainder).padStart(2, '0')}s` : `${seconds}s`;
}

function Header({ mode, catalog, snapshot, onModeChange }) {
  const current = snapshot?.snapshot_at ? formatBrisbaneTimestamp(snapshot.snapshot_at) : 'No recording selected';
  const isMorningWindow = isWeekdayMorningSnapshot(snapshot);
  const allowModeSwitch = !(import.meta.env.PROD && import.meta.env.VITE_DATA_MODE === 'static');
  return (
    <header className="topbar">
      <div className="brand-row">
        <div className="brand-mark"><span /></div>
        <div className="brand-name">Brisbane Transport<br /><strong>Resilience Lab</strong></div>
      </div>
      <div className="header-center">
        <span className="header-purpose">Explore service changes across Fairfield, Annerley, South Bank and the city.</span>
        <div className="header-meta">
          <Badge tone="coral">{catalog?.preview_only ? 'Local preview' : isMorningWindow ? 'Weekday morning timestamp' : 'Recorded preview'}</Badge>
          <span className="header-current">{current}{snapshot?.service_date ? ` · ${snapshot.service_date}` : ''}</span>
          {snapshot && <span className="afternoon-note">{isMorningWindow ? 'Weekday 06:00–12:00 timestamp · completeness is tracked separately' : 'Outside the weekday 06:00–12:00 collection window'}</span>}
        </div>
      </div>
      {allowModeSwitch && <div className="mode-picker" role="group" aria-label="Data source">
        <button className={mode === 'local' ? 'mode-option active' : 'mode-option'} onClick={() => onModeChange('local')}>Local API</button>
        <button className={mode === 'static' ? 'mode-option active' : 'mode-option'} onClick={() => onModeChange('static')}>Static bundle</button>
      </div>}
    </header>
  );
}

function Sidebar({ page, onPageChange }) {
  return (
    <aside className="sidebar">
      <span className="nav-label">Workspace</span>
      <nav aria-label="Project views">
        {NAV_ITEMS.map((item) => (
          <button key={item.id} className={`nav-item ${page === item.id ? 'selected' : ''}`} onClick={() => onPageChange(item.id)} aria-current={page === item.id ? 'page' : undefined}>
            <Icon name={item.icon} size={18} /><span>{item.label}</span>{page === item.id && <span className="nav-indicator" />}
          </button>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <span className="sidebar-kicker">Pilot corridor</span>
        <p>Fairfield &amp; Annerley<br /><span>South Bank · Brisbane CBD</span></p>
        <div className="sidebar-note"><span className="small-dot" />Recorded service, with hypothetical disruptions clearly marked.</div>
      </div>
    </aside>
  );
}

function SnapshotControl({ snapshots, snapshot, selectedIndex, onSelectIndex, playing, onPlayToggle, speed, onSpeedChange }) {
  const dates = [...new Set(snapshots.map((item) => item.service_date))];
  const previous = snapshots[selectedIndex - 1];
  const next = snapshots[selectedIndex + 1];
  const interval = arrivalGap(snapshot, previous);
  return (
    <div className="snapshot-control">
      <div className="snapshot-line">
        <label className="control-group date-select"><span>Service date</span>
          <select value={snapshot?.service_date ?? ''} onChange={(event) => {
            const matching = snapshots.map((item, index) => ({ item, index })).filter(({ item }) => item.service_date === event.target.value);
            if (matching.length) onSelectIndex(matching.at(-1).index);
          }}>
            {dates.map((date) => <option key={date} value={date}>{new Intl.DateTimeFormat('en-AU', { dateStyle: 'full', timeZone: 'Australia/Brisbane' }).format(new Date(`${date}T12:00:00+10:00`))}</option>)}
          </select>
        </label>
        <div className="snapshot-time">
          <span className="control-caption">Recorded at</span>
          <strong>{snapshot ? formatBrisbaneTimestamp(snapshot.snapshot_at, { dateStyle: 'short', timeStyle: 'medium' }) : '—'}</strong>
          {interval && <span className="time-gap">{interval} after the previous recording</span>}
        </div>
        <div className="playback-buttons">
          <button className="icon-button" aria-label="Previous recording" disabled={selectedIndex <= 0} onClick={() => onSelectIndex(selectedIndex - 1)}><Icon name="left" /></button>
          <button className="play-button" aria-label={playing ? 'Pause playback' : 'Play recordings'} onClick={onPlayToggle}><Icon name={playing ? 'pause' : 'play'} size={17} /></button>
          <button className="icon-button" aria-label="Next recording" disabled={selectedIndex >= snapshots.length - 1} onClick={() => onSelectIndex(selectedIndex + 1)}><Icon name="right" /></button>
        </div>
        <label className="control-group speed-select"><span>Playback</span>
          <select value={speed} onChange={(event) => onSpeedChange(Number(event.target.value))}>
            <option value={1}>1×</option><option value={2}>2×</option><option value={4}>4×</option>
          </select>
        </label>
      </div>
      <input className="timeline-range" type="range" min="0" max={Math.max(0, snapshots.length - 1)} step="1" value={selectedIndex} onChange={(event) => onSelectIndex(Number(event.target.value))} aria-label="Recording time" />
      <div className="timeline-labels"><span>{snapshots[0] ? formatBrisbaneTimestamp(snapshots[0].snapshot_at, { dateStyle: 'short', timeStyle: 'short' }) : ''}</span><span>Recording {selectedIndex + 1} of {snapshots.length}</span><span>{snapshots.at(-1) ? formatBrisbaneTimestamp(snapshots.at(-1).snapshot_at, { dateStyle: 'short', timeStyle: 'short' }) : ''}</span></div>
      {next && <div className="next-gap-note">Next recording arrives {arrivalGap(next, snapshot)} later · the timeline keeps actual capture times.</div>}
    </div>
  );
}

function VehicleCounts({ vehicles }) {
  const counts = countVehicleQuality(vehicles);
  return (
    <div className="vehicle-counts" aria-label="Recorded vehicle positions by source quality">
      <span><i className="dot fresh" />Fresh <strong>{formatCount(counts.fresh)}</strong></span>
      <span><i className="dot stale" />Stale <strong>{formatCount(counts.stale)}</strong></span>
      <span><i className="dot unmatched" />Unmatched <strong>{formatCount(counts.unmatched)}</strong></span>
      {counts.unknown > 0 && <span><i className="dot unknown" />Unknown age <strong>{formatCount(counts.unknown)}</strong></span>}
    </div>
  );
}

function ReplayView({
  catalog, snapshot, snapshots, selectedIndex, onSelectIndex, playing, onPlayToggle,
  speed, onSpeedChange, display, choices, network, loading, loadError, onRetry,
}) {
  const [visibleLayers, setVisibleLayers] = useState({ bus: true, rail: true, stops: true, vehicles: true });
  const [selectedStop, setSelectedStop] = useState(null);
  const [selectedVehicle, setSelectedVehicle] = useState(null);
  const quality = display?.quality ?? snapshot?.quality ?? {};
  const vehicles = display?.vehicles ?? [];
  const frameGaps = display?.gaps ?? [];

  useEffect(() => { setSelectedStop(null); setSelectedVehicle(null); }, [snapshot?.snapshot_id]);

  const selectedStopDetails = useMemo(() => {
    if (!selectedStop) return null;
    const stop = (choices?.stops ?? []).find((item) => String(item.stop_id) === String(selectedStop.stop_id));
    const platformIds = Array.isArray(selectedStop.platform_ids) ? selectedStop.platform_ids : [];
    const platforms = platformIds.map((id) => (choices?.stops ?? []).find((item) => String(item.stop_id) === String(id))).filter(Boolean);
    return { stop, platforms };
  }, [selectedStop, choices]);

  return (
    <>
      <SectionHeading eyebrow="Recorded network" title="Network & replay">
        Follow recorded positions at their source timestamps. Gaps stay visible; nothing is interpolated between captures.
      </SectionHeading>
      <ErrorNotice error={loadError} onRetry={onRetry} />
      <div className="summary-strip">
          <div className="summary-tile"><span>Recorded positions</span><strong>{loading && !display ? 'Loading…' : formatCount(vehicles.length)}</strong><small>From this exact frame</small></div>
        <div className="summary-tile"><span>Realtime source</span><StatusPill value={quality.realtime_status} /><small>Schedule: {humanLabel(quality.schedule_status)}</small></div>
        <div className="summary-tile"><span>Walking coverage</span><StatusPill value={quality.walking_status} /><small>Only sourced paths are eligible</small></div>
        <div className="summary-tile"><span>Service alerts</span><strong>{display ? formatCount(display.alerts?.length ?? 0) : loading ? 'Loading…' : '—'}</strong><small>Reported by the source feed</small></div>
      </div>

      <section className="panel replay-panel">
        <div className="panel-heading replay-panel-heading">
          <div><span className="eyebrow">Recorded service</span><h2>{snapshot?.service_date ? 'Brisbane network' : 'Choose a recording'}</h2></div>
          {catalog?.preview_only && <Badge tone="coral">Private preview</Badge>}
        </div>
        {catalog?.source_summary?.replay_label && <p className="next-gap-note">{catalog.source_summary.replay_label}</p>}
        <SnapshotControl snapshots={snapshots} snapshot={snapshot} selectedIndex={selectedIndex} onSelectIndex={onSelectIndex} playing={playing} onPlayToggle={onPlayToggle} speed={speed} onSpeedChange={onSpeedChange} />
        <div className="map-grid">
          <div className="map-wrap">
            {loading && <div className="map-loading">Loading the selected recording…</div>}
            <ReplayMap network={network} display={display} visibleLayers={visibleLayers} onStopSelect={(properties) => { setSelectedStop(properties); setSelectedVehicle(null); }} onVehicleSelect={(properties) => { setSelectedVehicle(properties); setSelectedStop(null); }} />
          </div>
          <aside className="map-side-panel">
            <div className="side-panel-top"><span className="eyebrow">Map layers</span><button className="clear-selection" onClick={() => { setSelectedStop(null); setSelectedVehicle(null); }} disabled={!selectedStop && !selectedVehicle}>Clear selection</button></div>
            <div className="layer-list">
              <LayerToggle label="Bus routes" tone="bus" checked={visibleLayers.bus} onChange={() => setVisibleLayers((value) => ({ ...value, bus: !value.bus }))} />
              <LayerToggle label="Rail routes" tone="rail" checked={visibleLayers.rail} onChange={() => setVisibleLayers((value) => ({ ...value, rail: !value.rail }))} />
              <LayerToggle label="Stops & stations" tone="stop" checked={visibleLayers.stops} onChange={() => setVisibleLayers((value) => ({ ...value, stops: !value.stops }))} />
              <LayerToggle label="Recorded vehicles" tone="vehicle" checked={visibleLayers.vehicles} onChange={() => setVisibleLayers((value) => ({ ...value, vehicles: !value.vehicles }))} />
              <div className="layer-conditional"><span className="legend-line walk" />Walking paths appear only when source geometry is included in a result.</div>
            </div>
            {loading && !display ? <div className="vehicle-counts" aria-live="polite">Loading source positions…</div> : <VehicleCounts vehicles={vehicles} />}
            <div className="selection-detail">
              {selectedVehicle && <VehicleDetail vehicle={selectedVehicle} />}
              {selectedStop && <StopDetail properties={selectedStop} details={selectedStopDetails} />}
              {!selectedVehicle && !selectedStop && <div className="selection-empty"><span className="selection-pin">⌖</span><strong>Select a stop or vehicle</strong><span>Details use the selected frame and its recorded source quality.</span></div>}
            </div>
            <div className="map-credits">Map tiles © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a></div>
          </aside>
        </div>
        <div className="recording-footnote">
          <div><strong>Snapshot time</strong><span>{snapshot ? formatBrisbaneTimestamp(snapshot.snapshot_at) : '—'} · Brisbane</span></div>
          <div><strong>Source cutoff</strong><span>Only records received by this snapshot are shown.</span></div>
          <div><strong>Frame gaps</strong><span>{!display && loading ? 'Loading frame details…' : !display ? 'Not available' : frameGaps.length ? `${frameGaps.length} source gap${frameGaps.length === 1 ? '' : 's'} reported` : 'No feed gap is listed inside this frame.'}</span></div>
          <div><strong>Route patterns</strong><span>Lines show patterns in the matching timetable, not proof of service at this instant. Active trips determine service choices.</span></div>
        </div>
        {!!frameGaps.length && <div className="gap-list">{frameGaps.map((gap, index) => <div key={`${gap.start ?? index}`}><span className="gap-marker" />{gap.label || `${gap.start ?? 'Unknown start'} – ${gap.end ?? 'Unknown end'}`}</div>)}</div>}
      </section>
    </>
  );
}

function LayerToggle({ label, tone, checked, onChange }) {
  const legend = tone === 'bus' ? 'legend-line bus' : tone === 'rail' ? 'legend-line rail' : tone === 'stop' ? 'legend-stop' : 'dot fresh';
  return <label className="layer-toggle"><input type="checkbox" checked={checked} onChange={onChange} /><span className={legend} /><span>{label}</span></label>;
}

function VehicleDetail({ vehicle }) {
  return (
    <div className="detail-card">
      <div className="detail-title"><strong>Recorded vehicle</strong><StatusPill value={vehicle.quality} /></div>
      <p className="detail-name">{vehicle.route_id || 'Route not matched'}</p>
      <dl>
        <DetailRow label="Vehicle record" value={vehicle.entity_id} />
        <DetailRow label="Trip" value={vehicle.trip_id || 'Not matched to a trip'} />
        <DetailRow label="Source event" value={formatBrisbaneTimestamp(vehicle.event_at)} />
        <DetailRow label="Received" value={formatBrisbaneTimestamp(vehicle.received_at)} />
        <DetailRow label="Source event age" value={vehicle.source_event_age_seconds == null ? 'Unknown' : `${Math.round(vehicle.source_event_age_seconds)} sec`} />
        <DetailRow label="Receipt age" value={vehicle.receipt_age_seconds == null ? 'Unknown' : `${Math.round(vehicle.receipt_age_seconds)} sec`} />
        <DetailRow label="Freshness basis" value={humanLabel(vehicle.freshness_basis || 'unknown')} />
      </dl>
      <small className="detail-caption">The marker is a recorded source position, not an estimated movement.</small>
    </div>
  );
}

function StopDetail({ properties, details }) {
  const stop = details?.stop;
  return (
    <div className="detail-card">
      <div className="detail-title"><strong>{properties.kind === 'station' ? 'Station' : 'Stop'}</strong><Badge>{properties.kind || 'GTFS location'}</Badge></div>
      <p className="detail-name">{properties.name || stop?.name || 'Recorded location'}</p>
      {properties.stop_id && <dl><DetailRow label="GTFS stop ID" value={properties.stop_id} /><DetailRow label="Recorded service" value={stop?.active_boardings > 0 ? `${stop.active_boardings} future pickups` : 'No active pickups in this schedule'} /></dl>}
      {details?.platforms?.length > 0 && <div className="platform-list"><strong>Source platforms</strong>{details.platforms.map((platform) => <span key={platform.stop_id}>{platform.name} · {platform.active_boardings > 0 ? 'active service' : 'no active service'}</span>)}</div>}
      <small className="detail-caption">Station and platform labels follow the selected timetable snapshot.</small>
    </div>
  );
}

function DetailRow({ label, value }) {
  return <div className="detail-row"><dt>{label}</dt><dd title={String(value)}>{value}</dd></div>;
}

function ImpactView({
  mode, catalog, snapshot, choices, network, eligible, savedRunCount, kind, setKind, targetId, setTargetId,
  originId, setOriginId, destinationId, setDestinationId, delayMinutes, setDelayMinutes,
  jobs, onRun, onCancel, onNavigate,
}) {
  const previousOriginId = useRef(originId);
  const trips = useMemo(() => prioritizeTripsForOrigin(
    (choices?.trips ?? [])
      .filter((trip) => Number.isInteger(trip.departure_s) && trip.departure_s >= (choices?.snapshot_s ?? Infinity))
      .filter((trip) => trip.departure_s < (choices?.snapshot_s ?? 0) + 3600),
    originId,
  ), [choices, originId]);
  const relevantSegments = useMemo(() => {
    const futureTrips = trips.map((trip) => new Set(trip.stop_ids ?? []));
    const stopsById = new Map((choices?.stops ?? []).map((stop) => [String(stop.stop_id), stop]));
    return (choices?.segments ?? []).filter((segment) => futureTrips.some((ids) =>
      [...ids].some((id, index, list) => id === String(segment.from_stop_id) && list[index + 1] === String(segment.to_stop_id)),
    )).map((segment) => ({ ...segment, key: `${segment.from_stop_id}:${segment.to_stop_id}`, from: stopsById.get(String(segment.from_stop_id))?.name || segment.from_stop_id, to: stopsById.get(String(segment.to_stop_id))?.name || segment.to_stop_id }))
      .sort((a, b) => `${a.from} ${a.to}`.localeCompare(`${b.from} ${b.to}`)).slice(0, 180);
  }, [choices, trips]);
  const activeStops = eligible.activeStops;
  const targetOptions = kind === 'stop_unavailable' ? activeStops
    : kind === 'corridor_closure' ? relevantSegments : trips;
  const currentTarget = kind === 'stop_unavailable'
    ? activeStops.find((stop) => String(stop.stop_id) === targetId)
    : kind === 'corridor_closure'
      ? relevantSegments.find((segment) => segment.key === targetId)
      : trips.find((trip) => trip.trip_instance_id === targetId);
  const selectedOrigin = eligible.origins.find((stop) => String(stop.stop_id) === originId);
  const selectedDestination = eligible.destinations.find((stop) => String(stop.stop_id) === destinationId);
  const routeNames = useMemo(() => routeNameById(network), [network]);
  const stopNames = useMemo(() => new Map((choices?.stops ?? []).map((stop) => [String(stop.stop_id), stop.name])), [choices]);
  const canRun = mode === 'local' && snapshot && choices && currentTarget && selectedOrigin && selectedDestination && !jobs.some((job) => ['submitting', 'queued', 'running', 'cancellation_requested'].includes(job.status));

  useEffect(() => {
    const isTripScenario = kind === 'trip_cancellation' || kind === 'additional_delay';
    const exists = targetOptions.some((item) => (kind === 'stop_unavailable' ? String(item.stop_id) : kind === 'corridor_closure' ? item.key : item.trip_instance_id) === targetId);
    const originChanged = previousOriginId.current !== originId;
    previousOriginId.current = originId;
    if (targetOptions.length && (!exists || (isTripScenario && originChanged))) {
      setTargetId(kind === 'stop_unavailable' ? String(targetOptions[0].stop_id) : kind === 'corridor_closure' ? targetOptions[0].key : targetOptions[0].trip_instance_id);
    }
  }, [kind, targetOptions, targetId, setTargetId, originId]);

  const describeTarget = (item) => {
    if (kind === 'stop_unavailable') return serviceLabel(item);
    if (kind === 'corridor_closure') {
      const routeLabels = (item.route_ids ?? []).map((id) => routeNames.get(String(id))?.shortName ?? id).slice(0, 3);
      return `${item.from} → ${item.to} · ${routeLabels.join(', ') || 'recorded segment'}`;
    }
    const route = routeNames.get(String(item.route_id));
    const modeLabel = item.mode === 'rail' ? 'Train' : 'Bus';
    const routeLabel = route ? `${modeLabel} ${route.shortName}` : `${modeLabel} route`;
    return `${routeLabel} · ${stopNames.get(String(item.from_stop_id)) || item.from_stop_id} → ${stopNames.get(String(item.to_stop_id)) || item.to_stop_id} · ${formatServiceTime(choices?.service_date, item.departure_s)}`;
  };

  return (
    <>
      <SectionHeading eyebrow="Hypothetical scenario" title="Disruption impact">
        Build one clearly labelled scenario from actual stops, trips or adjacent service segments in the selected recording.
      </SectionHeading>
      <div className="scenario-layout">
        <section className="panel scenario-form-panel">
          <div className="panel-heading"><div><span className="eyebrow">Scenario builder</span><h2>Set up a disruption</h2></div><Badge tone="coral">Hypothetical</Badge></div>
          <ErrorNotice error={!choices && !snapshot ? new Error('Choose a recording on the Network & replay page first.') : null} />
          <div className="field-grid field-grid-two">
            <label className="field"><span>Starting stop · pilot corridor</span>
              <select value={originId} onChange={(event) => setOriginId(event.target.value)} disabled={!eligible.origins.length}>
                {eligible.origins.map((stop) => <option key={stop.stop_id} value={stop.stop_id}>{serviceLabel(stop)}</option>)}
              </select>
              {!eligible.origins.length && <small>No active pilot bus stop or rail platform is present in this recording.</small>}
            </label>
            <label className="field"><span>Destination · South Bank / city bus or rail</span>
              <select value={destinationId} onChange={(event) => setDestinationId(event.target.value)} disabled={!eligible.destinations.length}>
                {eligible.destinations.map((stop) => <option key={stop.stop_id} value={stop.stop_id}>{serviceLabel(stop)}</option>)}
              </select>
              {!eligible.destinations.length && <small>No active South Bank/city bus or rail stop is present in this recording.</small>}
            </label>
          </div>
          <div className="route-example"><span className="route-node start" /><div><strong>Five test journeys</strong><span>Departures at 0, 15, 30, 45 and 60 minutes after the selected recording.</span></div><span className="route-node end" /></div>
          <div className="field-grid field-grid-two scenario-type-row">
            <label className="field"><span>Disruption type</span>
              <select value={kind} onChange={(event) => { setKind(event.target.value); setTargetId(''); }}>
                <option value="trip_cancellation">Cancel one upcoming trip</option>
                <option value="stop_unavailable">Make one active stop unavailable</option>
                <option value="corridor_closure">Close one adjacent service segment</option>
                <option value="additional_delay">Add a delay to one upcoming trip</option>
              </select>
            </label>
            <label className="field"><span>{kind === 'stop_unavailable' ? 'Active stop' : kind === 'corridor_closure' ? 'Recorded adjacent segment' : 'Upcoming trip'}</span>
              <select value={targetId} onChange={(event) => setTargetId(event.target.value)} disabled={!targetOptions.length}>
                {targetOptions.map((item) => {
                  const value = kind === 'stop_unavailable' ? String(item.stop_id) : kind === 'corridor_closure' ? item.key : item.trip_instance_id;
                  return <option key={value} value={value}>{describeTarget(item)}</option>;
                })}
              </select>
              {!targetOptions.length && <small>No eligible upcoming item is available in this recording.</small>}
              {(kind === 'trip_cancellation' || kind === 'additional_delay') && currentTarget && <small>Source trip: {currentTarget.trip_instance_id} · route ID {currentTarget.route_id}</small>}
            </label>
          </div>
          {kind === 'additional_delay' && <label className="field delay-field"><span>Added delay</span><div className="inline-control"><input type="number" min="1" step="1" value={delayMinutes} onChange={(event) => setDelayMinutes(Number(event.target.value))} /><span>minutes</span></div></label>}
          <div className="scenario-interval"><div><span>Scenario window</span><strong>{snapshot && choices ? `${formatServiceTime(choices.service_date, choices.snapshot_s)} – ${formatServiceTime(choices.service_date, choices.snapshot_s + 3600)}` : '—'}</strong></div><span>1 hour from this recording · no earlier than the source cutoff</span></div>
          {mode === 'static' && <div className="inline-callout"><strong>Prepared comparisons are view-only.</strong><span>Custom scenarios need the local application. This bundle includes {formatCount(savedRunCount)} recorded run{savedRunCount === 1 ? '' : 's'}.</span><button className="text-button" onClick={() => onNavigate('recovery')}>View recorded comparisons</button></div>}
          {mode === 'local' && <div className="scenario-actions"><button className="button button-primary" disabled={!canRun} onClick={onRun}><span>Compare 0 · 2 · 4 · 8 bus-hours</span><Icon name="arrows" size={17} /></button><span>Same five journeys and scenario across all four budgets.</span></div>}
          <p className="form-disclaimer">These are fixed test journeys, not passenger counts or observed demand. Recovery plans are hypothetical.</p>
        </section>
        <aside className="scenario-aside">
          <div className="aside-card accent-card"><span className="eyebrow">What is being compared</span><h3>One scenario, four budgets</h3><div className="budget-pills">{BUDGETS.map((budget) => <span key={budget}>{budget}h</span>)}</div><p>Each run compares no intervention, a simple affected-pattern option and the best plan the search actually evaluated.</p></div>
          <div className="aside-card"><span className="eyebrow">Constraints</span><ul className="constraint-list"><li>Only trips, stops and adjacent segments in this source snapshot.</li><li>Only future trips are offered for cancellation or delay.</li><li>One-hour scenario window starts at the recorded service time.</li><li>Replacement service follows the reviewed timetable and resource limits.</li></ul></div>
          {snapshot?.quality?.walking_status === 'incomplete' && <div className="aside-card muted-card"><span className="eyebrow">Walking access</span><p>Some platform paths are unresolved in this snapshot. The comparison will use only recorded walking geometry; it will not draw straight-line shortcuts.</p></div>}
        </aside>
      </div>
      <section className="job-status-section"><div className="subsection-heading"><div><span className="eyebrow">Current comparison</span><h2>Run progress</h2></div>{jobs.some((job) => ['queued', 'running', 'cancellation_requested'].includes(job.status)) && <button className="button button-small button-soft" onClick={onCancel}><Icon name="close" size={15} /> Cancel active runs</button>}</div>
        {jobs.length ? <div className="job-grid">{jobs.map((job) => <JobTile key={job.run_id || job.budget_bus_hours} job={job} />)}</div> : <div className="empty-inline"><div className="empty-symbol"><Icon name="pulse" size={21} /></div><div><strong>No disruption run has been submitted.</strong><span>Choose a source-backed disruption above to create the four comparable runs.</span></div></div>}
      </section>
    </>
  );
}

function JobTile({ job }) {
  const completed = job.status === 'completed' && job.result;
  const metrics = completed ? job.result?.plan?.evaluation?.metrics : null;
  const failed = ['failed', 'cancelled'].includes(job.status);
  return <article className={`job-tile ${failed ? 'job-failed' : ''}`}><div className="job-top"><strong>{job.budget_bus_hours} bus-hour{job.budget_bus_hours === 1 ? '' : 's'}</strong><StatusPill value={job.status} /></div>{job.status === 'running' || job.status === 'queued' || job.status === 'submitting' || job.status === 'cancellation_requested' ? <><div className="progress-track"><span style={{ width: `${Math.max(4, (job.progress ?? 0) * 100)}%` }} /></div><small>{job.progress_details?.stage ? humanLabel(job.progress_details.stage) : humanLabel(job.status)}{Number.isFinite(job.progress_details?.evaluated_plan_count) ? ` · ${job.progress_details.evaluated_plan_count} plans checked` : ''}</small></> : completed ? <div className="job-outcome"><span><strong>{metrics?.restored_count ?? '—'}</strong> restored</span><span>{metrics?.lost_count ?? '—'} lost in test set</span></div> : <small>{job.error || 'No partial outcome was saved.'}</small>}</article>;
}

function RecoveryView({ jobs, savedRuns, snapshots, network, networkSnapshotId, adapter, onRefresh, mode }) {
  const [openedRun, setOpenedRun] = useState(null);
  const [openedError, setOpenedError] = useState('');
  const [opening, setOpening] = useState(false);
  const [filters, setFilters] = useState(() => ({ ...DEFAULT_RECOVERY_FILTERS }));
  const openingVersion = useRef(0);
  const changeFilter = (key, value) => {
    openingVersion.current += 1;
    setFilters((previous) => ({ ...previous, [key]: value }));
    setOpenedRun(null); setOpenedError(''); setOpening(false);
  };
  useEffect(() => () => { openingVersion.current += 1; }, []);
  const doneJobs = jobs.filter((job) => job.status === 'completed' && job.result);
  const savedOnly = savedRuns.filter((run) => !jobs.some((job) => job.run_id === (run.run_id ?? run.id)));
  const completedRuns = savedOnly.filter((run) => run.status === 'completed');
  const otherRuns = savedOnly.filter((run) => run.status !== 'completed');
  const completedEntries = completedRuns.map((run) => ({ run, summary: runSummary(run, snapshots) }));
  const filterOptions = recoveryFilterOptions(completedEntries);
  const shownEntries = filterRecoveryRuns(completedEntries, filters);
  const scenarioNames = { trip_cancellation: 'Trip cancellation', stop_unavailable: 'Stop closure', corridor_closure: 'Rail corridor closure', additional_delay: 'Bus delay', unknown: 'Scenario not included' };
  const runGroups = (() => {
    const groups = new Map();
    for (const { run, summary } of shownEntries) {
      const id = run.run_id ?? run.id ?? 'unknown';
      const key = summary.groupKey ?? `single:${id}`;
      const group = groups.get(key) ?? { key, summary, runs: [] };
      group.runs.push({ run, summary });
      groups.set(key, group);
    }
    return [...groups.values()].map((group) => ({
      ...group,
      runs: group.runs.sort((a, b) => (a.summary.budget ?? Number.MAX_SAFE_INTEGER) - (b.summary.budget ?? Number.MAX_SAFE_INTEGER)),
    })).sort((a, b) => a.summary.scenarioLabel.localeCompare(b.summary.scenarioLabel)
      || String(a.summary.sourceTime ?? '').localeCompare(String(b.summary.sourceTime ?? '')));
  })();

  const openRun = async (run) => {
    const id = run.run_id ?? run.id;
    if (!id) return;
    const version = ++openingVersion.current;
    setOpening(true); setOpenedError('');
    try {
      const payload = await adapter.getRun(id);
      if (version !== openingVersion.current) return;
      const summary = runSummary({ ...run, ...payload }, snapshots);
      setOpenedRun({ run, payload, summary });
    } catch (error) {
      if (version === openingVersion.current) setOpenedError(error.message);
    } finally {
      if (version === openingVersion.current) setOpening(false);
    }
  };

  return (
    <>
      <SectionHeading eyebrow="Recovery options" title="Recovery comparison">
        Read the returned plan beside simpler alternatives. Every result is tied to the same test journeys and scenario.
      </SectionHeading>
      <div className="comparison-intro"><div className="comparison-intro-mark"><Icon name="arrows" size={22} /></div><div><strong>Restoration comes first. Travel time breaks ties.</strong><span>Costs include two-hour bus duties. Bounded searches show the best plan they evaluated; they do not claim a global optimum.</span></div><button className="button button-small button-soft" onClick={onRefresh}><Icon name="refresh" size={15} /> Refresh runs</button></div>
      {doneJobs.length > 0 && <div className="comparison-results">{doneJobs.sort((a, b) => a.budget_bus_hours - b.budget_bus_hours).map((job) => <RecoveryCard key={job.run_id} job={job} network={job.snapshot_id === networkSnapshotId ? network : null} serviceDate={job.service_date || snapshots.find((item) => item.snapshot_id === job.snapshot_id)?.service_date} />)}</div>}
      {completedRuns.length > 0 && <section className="panel saved-runs-panel"><div className="panel-heading"><div><span className="eyebrow">Recorded comparisons</span><h2>Completed results</h2></div><Badge>{shownEntries.length} shown of {completedRuns.length} complete</Badge></div>
        <div className="snapshot-line" role="group" aria-label="Filter recorded comparisons">
          <label>Recording date<select value={filters.date} onChange={(event) => changeFilter('date', event.target.value)}>
            <option value="">All dates</option>
            {!filterOptions.dates.includes(filters.date) && filters.date && <option value={filters.date}>{filters.date} · no recorded runs</option>}
            {filterOptions.dates.map((date) => <option key={date} value={date}>{date === 'unknown' ? 'Date not included' : date}</option>)}
          </select></label>
          <label>Scenario type<select value={filters.scenario} onChange={(event) => changeFilter('scenario', event.target.value)}>
            <option value="">All scenarios</option>
            {!filterOptions.scenarios.includes(filters.scenario) && filters.scenario && <option value={filters.scenario}>{scenarioNames[filters.scenario] || humanLabel(filters.scenario)} · no recorded runs</option>}
            {filterOptions.scenarios.map((kind) => <option key={kind} value={kind}>{scenarioNames[kind] || humanLabel(kind)}</option>)}
          </select></label>
          <label>Bus running-time assumption<select value={filters.sensitivity} onChange={(event) => changeFilter('sensitivity', event.target.value)}>
            <option value="">All assumptions</option>
            {!filterOptions.sensitivities.includes(filters.sensitivity) && filters.sensitivity && <option value={filters.sensitivity}>{sensitivityLabel(Number(filters.sensitivity))} · no recorded runs</option>}
            {filterOptions.sensitivities.map((seconds) => <option key={seconds} value={seconds}>{seconds === 'unknown' ? 'Assumption not included' : seconds === '0' ? 'Base running time' : `Hypothetical +${Number(seconds) / 60} minutes`}</option>)}
          </select></label>
        </div>
        <p className="other-runs-note" role="status" aria-live="polite">{shownEntries.length} shown of {completedRuns.length} complete. Results retain their exact source, requests, scenario and assumptions.</p>
        {shownEntries.length === 0 && <div className="empty-panel"><h3>No recorded results for this combination</h3><p>Choose another filter combination to inspect the included comparisons.</p></div>}
        <div className="saved-run-groups">{runGroups.map((group) => {
          const summary = group.summary;
          const sourceTime = summary.sourceTime ? `${formatBrisbaneTimestamp(summary.sourceTime)} Brisbane` : 'Source time not included in this index';
          const snapshotLabel = summary.snapshotId ? `Snapshot ${String(summary.snapshotId).slice(0, 8)}…` : 'Snapshot details unavailable';
          const subtitle = [sourceTime, snapshotLabel, summary.scenarioWindow].filter(Boolean).join(' · ');
          return <div className="saved-run-group" key={group.key}>
            <div className="saved-run-group-heading"><div><span className="eyebrow">{group.runs.length > 1 ? 'Same source, journeys and disruption' : 'Recorded comparison'}</span><h3>{summary.scenarioLabel}</h3><p>{subtitle}</p></div>{summary.legacy && <Badge tone="warning">Legacy result</Badge>}</div>
            <div className="saved-run-list">{group.runs.map(({ run, summary: runInfo }) => {
              const id = run.run_id ?? run.id ?? 'unknown';
              const budgetLabel = Number.isFinite(runInfo.budget)
                ? `${runInfo.budget} bus-hour${runInfo.budget === 1 ? '' : 's'} budget`
                : 'Budget not included in this index';
              const usedLabel = Number.isFinite(runInfo.usedBusHours) ? ` · ${runInfo.usedBusHours} used` : '';
              const outcome = Number.isFinite(runInfo.metrics?.restored_count) && Number.isFinite(runInfo.metrics?.request_count)
                ? `${runInfo.metrics.restored_count} of ${runInfo.metrics.request_count} test journeys restored`
                : null;
              return <button key={id} className="saved-run-button" onClick={() => openRun(run)}>
                <span className="saved-run-icon"><Icon name="document" size={17} /></span>
                <span><strong>{budgetLabel}{usedLabel}</strong><small>{sensitivityLabel(runInfo.sensitivity)}{outcome ? ` · ${outcome}` : ''}</small><small className="saved-run-id">Run ID {id}</small></span>
                <Icon name="right" size={17} />
              </button>;
            })}</div>
          </div>;
        })}</div>
      </section>}
      {otherRuns.length > 0 && <section className="panel other-runs-panel"><div className="panel-heading"><div><span className="eyebrow">Run records</span><h2>Not completed</h2></div><Badge>{otherRuns.length}</Badge></div><p className="other-runs-note">These records have no completed comparison result.</p><div className="other-run-list">{otherRuns.map((run) => <div className="other-run-row" key={run.run_id ?? run.id}><span><strong>{humanLabel(run.status || 'unknown')}</strong><small>Run ID {run.run_id ?? run.id ?? 'not recorded'}</small></span><StatusPill value={run.status || 'unknown'} /></div>)}</div></section>}
      {opening && <div className="loading-inline">Opening recorded comparison…</div>}
      {openedError && <div className="notice notice-error"><Icon name="alert" /><span>{openedError}</span></div>}
      {openedRun && <>
        <div className="opened-run-context"><strong>{openedRun.summary.scenarioLabel}</strong><span>{openedRun.summary.sourceTime ? `${formatBrisbaneTimestamp(openedRun.summary.sourceTime)} Brisbane` : 'Source snapshot time not included'} · {Number.isFinite(openedRun.summary.budget) ? `${openedRun.summary.budget} bus-hour budget` : 'Budget not included'} · {sensitivityLabel(openedRun.summary.sensitivity)}</span></div>
        <RecoveryCard job={{ ...openedRun.run, input: openedRun.payload.input, result: openedRun.payload.result ?? openedRun.payload, budget_bus_hours: openedRun.payload.result?.budget_bus_hours ?? openedRun.payload.budget_bus_hours }} network={(openedRun.payload.snapshot_id ?? openedRun.run.snapshot_id) === networkSnapshotId ? network : null} serviceDate={snapshots.find((item) => item.snapshot_id === (openedRun.payload.snapshot_id || openedRun.run.snapshot_id))?.service_date} />
      </>}
      {!doneJobs.length && !completedRuns.length && <div className="empty-panel"><div className="empty-symbol large"><Icon name="arrows" size={25} /></div><h2>No completed recovery comparisons yet</h2><p>{mode === 'static' ? 'No completed runs are included in this recorded afternoon bundle. No comparison has been invented.' : 'Submit a disruption scenario to compare the returned plans at 0, 2, 4 and 8 bus-hours.'}</p><div className="empty-footnote">A two-hour duty uses one bus. Unreachable journeys remain in the 90-minute capped-time objective.</div></div>}
    </>
  );
}

function RecoveryCard({ job, network, serviceDate }) {
  const result = job.result?.result ?? job.result;
  const plan = result?.plan;
  const metrics = plan?.evaluation?.metrics;
  if (!plan || !metrics) return <article className="panel recovery-card"><div className="notice notice-error"><Icon name="alert" /><span>This saved result has no complete plan and evaluation to compare.</span></div></article>;

  const candidates = [
    { label: 'No intervention', objective: result.no_intervention, kind: 'quiet' },
    { label: 'Busiest affected pattern', objective: result.busiest_affected_pattern, kind: 'simple' },
    { label: 'Best evaluated recovery', objective: plan.objective, kind: 'best' },
  ].filter((item) => item.objective);
  const requestCount = Math.max(1, metrics.request_count || 0);
  const average = (total) => Number.isFinite(total) ? total / requestCount : null;
  const routeNames = routeNameById(network);
  const inputCandidates = new Map((job.input?.candidates ?? []).map((candidate) => [candidate.candidate_id, candidate]));
  const dutyText = plan.duties?.length ? plan.duties.map((duty) => {
    const candidate = duty.candidate ?? duty;
    const sourceCandidate = inputCandidates.get(candidate.candidate_id) ?? {};
    const routeIds = candidate.route_ids ?? sourceCandidate.route_ids
      ?? candidate.pattern?.route_ids ?? sourceCandidate.pattern?.route_ids
      ?? [candidate.route_id ?? sourceCandidate.route_id ?? candidate.pattern?.route_id ?? sourceCandidate.pattern?.route_id].filter(Boolean);
    const routeLabels = [...new Set((Array.isArray(routeIds) ? routeIds : [routeIds])
      .map((routeId) => routeNames.get(String(routeId))?.shortName).filter(Boolean))];
    const dutyLabel = routeLabels.length ? `Route ${routeLabels.join(', ')}` : 'Bus duty';
    const candidateDetail = candidate.candidate_id ? ` · candidate ID ${candidate.candidate_id}` : '';
    const activation = Number.isInteger(candidate.activation_s) && serviceDate
      ? `activates ${formatServiceTime(serviceDate, candidate.activation_s)}` : 'activation time recorded';
    return `${dutyLabel}${candidateDetail} · ${activation} · ${duty.cycle_count} complete cycle${duty.cycle_count === 1 ? '' : 's'} · 2-hour duty`;
  }).join('; ') : 'No bus duty selected';
  const baselineCappedSeconds = result.no_intervention?.total_capped_duration_s;
  const selectedCappedSeconds = plan.objective?.total_capped_duration_s;
  const aggregateCappedChange = Number.isFinite(baselineCappedSeconds) && Number.isFinite(selectedCappedSeconds)
    ? baselineCappedSeconds - selectedCappedSeconds : null;

  return (
    <article className="panel recovery-card">
      <div className="recovery-card-heading"><div><span className="eyebrow">Budget comparison</span><h2>{result.budget_bus_hours ?? job.budget_bus_hours} bus-hours</h2><p>{requestCount} equally weighted test journeys · not passenger counts</p></div><Badge tone="teal">Result recorded</Badge></div>
      <div className="metric-row">
        <Metric label="Lost after disruption" value={`${metrics.lost_count} / ${requestCount}`} detail="Journeys previously within 60 min" />
        <Metric label="Restored by selected plan" value={`${metrics.restored_count} / ${requestCount}`} detail={metrics.lost_count === 0 ? 'No baseline loss in this test set' : `${formatPercent(metrics.restored_fraction)} of lost test journeys`} />
        <Metric label="Recovery reachability" value={`${metrics.recovered_reachable_count} / ${requestCount}`} detail="Test journeys arriving within 60 minutes" />
        <Metric label="Best plan cost" value={`${plan.bus_hours} h`} detail={`${plan.bus_count} bus${plan.bus_count === 1 ? '' : 'es'} · 2-hour duties`} />
      </div>
      <div className="policy-table-wrap">
        <table className="policy-table"><thead><tr><th>Compared option</th><th>Restored</th><th>Average capped time</th><th>Bus-hours</th></tr></thead><tbody>
          {candidates.map((item) => <tr key={item.label} className={item.kind === 'best' ? 'best-row' : ''}><th scope="row">{item.label}{item.kind === 'simple' && <small>Service frequency, not passenger demand</small>}</th><td>{item.objective.restored_count}</td><td>{formatDuration(average(item.objective.total_capped_duration_s))}<small>{formatCount(item.objective.total_capped_duration_s)} s total</small></td><td>{item.objective.bus_hours} h</td></tr>)}
        </tbody></table>
      </div>
      <div className="duration-note"><span className="duration-cap">90m</span><div className="duration-note-copy"><p><strong>How travel time is compared</strong><span>Each journey is capped at 90 minutes for the objective. An unreachable journey receives the full 90-minute penalty; this is not its measured travel time. Averages and totals use all {requestCount} test journeys.</span></p><p className="aggregate-time-change"><strong>Aggregate capped-time change vs no intervention</strong><span>{aggregateCappedChange === null ? 'Not available' : aggregateCappedChange > 0 ? `${formatCount(aggregateCappedChange)} seconds lower` : aggregateCappedChange < 0 ? `${formatCount(Math.abs(aggregateCappedChange))} seconds higher` : 'No change'}</span><small>Summed across {requestCount} equally weighted test journeys · not passenger demand</small></p></div></div>
      <div className="duties-row"><div><span className="eyebrow">Selected duties</span><p>{dutyText}</p><small>Activation is no earlier than 10 minutes after the snapshot; each duty is limited to two hours.</small></div><div className="optimality-note">{result.optimality_proven ? 'Exact optimum proved for the supplied candidate set.' : 'Best plan evaluated within the search limit; global optimality is not claimed.'}</div></div>
      {result.infeasible_candidates?.length > 0 && <details className="infeasible-details"><summary>{result.infeasible_candidates.length} candidate{result.infeasible_candidates.length === 1 ? '' : 's'} could not be scheduled</summary><ul>{result.infeasible_candidates.map((item) => <li key={item.candidate_id}><strong>{item.candidate_id}</strong> · {humanLabel(item.reason)}</li>)}</ul></details>}
    </article>
  );
}

function Metric({ label, value, detail }) {
  return <div className="metric-card"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>;
}

function EvidenceView({ catalog, snapshot, snapshots, display, choices, runs, loading }) {
  const quality = display?.quality ?? snapshot?.quality ?? {};
  const vehicleCounts = countVehicleQuality(display?.vehicles ?? []);
  const coverage = catalog?.release_gate?.coverage ?? {};
  const gates = catalog?.release_gate?.gates ?? {};
  const failedGateCount = Object.values(gates).filter((value) => value === false).length;
  const sourceSummary = catalog?.source_summary;
  const fairfieldPlatforms = ['600052', '600194'].map((id) => (choices?.stops ?? []).find((stop) => String(stop.stop_id) === id)).filter(Boolean);
  const ordered = [...snapshots].sort((a, b) => Date.parse(a.snapshot_at) - Date.parse(b.snapshot_at));

  return (
    <>
      <SectionHeading eyebrow="Source record & limitations" title="Evidence">
        See what was recorded, when the data arrived, what is missing and how the simulation is constrained.
      </SectionHeading>
      <section className="panel evidence-current">
        <div className="panel-heading"><div><span className="eyebrow">Selected recording</span><h2>{snapshot?.service_date || 'No date selected'}</h2></div><Badge tone="coral">{catalog?.preview_only ? 'Private preview' : 'Recorded demo'}</Badge></div>
        <div className="evidence-grid">
          <EvidenceValue label="Snapshot received cutoff" value={formatBrisbaneTimestamp(snapshot?.snapshot_at, { dateStyle: 'full', timeStyle: 'medium' })} />
          <EvidenceValue label="Schedule" value={<StatusPill value={quality.schedule_status} />} />
          <EvidenceValue label="Realtime feed" value={<StatusPill value={quality.realtime_status} />} />
          <EvidenceValue label="Walking paths" value={<StatusPill value={quality.walking_status} />} />
          <EvidenceValue label="Recorded positions" value={display ? `${formatCount(display.vehicles?.length ?? 0)} · ${vehicleCounts.fresh} fresh, ${vehicleCounts.stale} stale, ${vehicleCounts.unmatched} unmatched, ${vehicleCounts.unknown} unknown` : loading ? 'Loading selected frame…' : 'Not available'} />
          <EvidenceValue label="Reported frame gaps" value={display ? formatCount(display.gaps?.length ?? 0) : loading ? 'Loading…' : 'Not available'} />
          <EvidenceValue label="Source alerts" value={display ? formatCount(display.alerts?.length ?? 0) : loading ? 'Loading…' : 'Not available'} />
          <EvidenceValue label="Recorded comparisons" value={formatCount(runs.length)} />
        </div>
        <div className="quality-labels">
          {sourceSummary?.replay_label && <p>{sourceSummary.replay_label}</p>}
          <div><span className="eyebrow">Source statements</span><p>{display?.labels?.positions || 'Vehicle markers retain their source event and receipt times.'}</p><p>{display?.labels?.predictions || 'Predicted timestamps are not measured arrivals.'}</p><p>{display?.labels?.scenarios || 'Disruptions and recovery plans are hypothetical.'}</p></div>
          <div><span className="eyebrow">Current quality notes</span>{quality.warnings?.length ? <ul>{quality.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : <p>No quality warnings are attached to this recording.</p>}</div>
        </div>
      </section>

      <div className="evidence-columns">
        <section className="panel">
          <div className="panel-heading"><div><span className="eyebrow">Collection completeness</span><h2>Morning evidence</h2></div><Badge tone={coverage.complete_weekday_windows > 0 ? 'warning' : 'muted'}>{coverage.complete_weekday_windows ?? 0} / {coverage.required_windows ?? 5} weekdays</Badge></div>
          <div className="gate-progress"><div className="gate-progress-track"><span style={{ width: `${Math.min(100, ((coverage.complete_weekday_windows ?? 0) / Math.max(1, coverage.required_windows ?? 5)) * 100)}%` }} /></div><p>{coverage.definition || 'Complete receipt coverage for all three source feeds is required.'}</p></div>
          <div className="morning-window-list">{(coverage.windows ?? []).map((window) => <div className="morning-window" key={`${window.service_date}-${window.start}`}><div><strong>{window.service_date}</strong><span>{formatBrisbaneTimestamp(window.start)} – {formatBrisbaneTimestamp(window.end)}</span></div><StatusPill value={window.complete ? 'complete' : 'incomplete'} label={window.complete ? 'Complete' : 'Incomplete'} /></div>)}</div>
          <div className="preview-callout"><strong>{isWeekdayMorningSnapshot(snapshot) ? 'This frame has a weekday morning timestamp.' : 'This frame is outside the weekday morning window.'}</strong><span>A timestamp alone does not prove a complete six-hour collection. The five-window and three-bundle release counts are tracked separately.</span></div>
          <div className="snapshot-history"><span className="eyebrow">Recorded frame timeline</span>{ordered.map((item, index) => <div key={item.snapshot_id} className={`history-item ${item.snapshot_id === snapshot?.snapshot_id ? 'history-selected' : ''}`}><span className="history-node" /><div><strong>{formatBrisbaneTimestamp(item.snapshot_at, { dateStyle: 'short', timeStyle: 'medium' })}</strong><small>{index ? `${arrivalGap(item, ordered[index - 1])} after previous frame` : 'First retained frame'} · {humanLabel(item.quality?.realtime_status || 'unknown')}</small></div></div>)}</div>
        </section>

        <section className="panel">
          <div className="panel-heading"><div><span className="eyebrow">Pilot scope</span><h2>What this snapshot can support</h2></div></div>
          <div className="pilot-budget-grid"><EvidenceValue label="Maximum walk" value="600 m · 1.2 m/s" /><EvidenceValue label="Transfer allowance" value="300 seconds" /><EvidenceValue label="Vehicle changes" value="Up to 3" /><EvidenceValue label="Recovery budget" value="0, 2, 4 or 8 bus-hours" /></div>
          <p className="evidence-paragraph">Only actual GTFS shapes and directed OSM paths are used. Missing platform connections stay unresolved; map proximity does not create a walking route.</p>
          {fairfieldPlatforms.length > 0 && <div className="platform-evidence"><span className="eyebrow">Fairfield rail platforms in this timetable</span>{fairfieldPlatforms.map((stop) => <div key={stop.stop_id} className="platform-evidence-row"><span><strong>{stop.name}</strong><small>GTFS stop {stop.stop_id}</small></span><StatusPill value={stop.active_boardings > 0 ? 'verified' : 'missing'} label={stop.active_boardings > 0 ? `${stop.active_boardings} active pickups` : 'No active service'} /></div>)}<p>These platform ids remain visible in the source. No train service is inferred where the timetable has none.</p></div>}
          {catalog?.preview_only ? <div className="release-gates"><div className="subsection-heading"><div><span className="eyebrow">Release checks</span><h3>{failedGateCount} checks still open</h3></div></div>{Object.entries(gates).map(([key, passed]) => <div key={key} className="release-gate-row"><span className={passed ? 'gate-check passed' : 'gate-check'}>{passed ? <Icon name="check" size={13} /> : '·'}</span><span>{releaseGateName(key)}</span><strong>{passed ? 'Complete' : 'Pending'}</strong></div>)}</div> : <p className="evidence-paragraph">Release verification and reproducible findings are documented in the <a href="https://github.com/Suhail15/brisbane-transport-resilience-lab/blob/main/docs/RELEASE.md" target="_blank" rel="noreferrer">repository evidence</a>. This recorded demo does not provide live travel advice.</p>}
        </section>
      </div>

      <section className="panel source-credits">
        <div className="panel-heading"><div><span className="eyebrow">Attribution & terms</span><h2>Source credits</h2></div></div>
        <div className="source-credit-grid">
          <div><span className="source-monogram">T</span><div><strong>Translink · Queensland Department of Transport and Main Roads</strong><p>{TRANSLINK_ATTRIBUTION}</p><a href="https://translink.com.au/about-translink/open-data" target="_blank" rel="noreferrer">Translink open data ↗</a> · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0 ↗</a></div></div>
          <div><span className="source-monogram osm-monogram">O</span><div><strong>OpenStreetMap contributors</strong><p>© OpenStreetMap contributors · ODbL 1.0. The extract is not historic.</p><a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">Copyright and licence ↗</a></div></div>
        </div>
        {sourceSummary && <details className="provenance-details"><summary>Inspect bundle provenance</summary><pre>{JSON.stringify(sourceSummary, null, 2)}</pre></details>}
      </section>
    </>
  );
}

function EvidenceValue({ label, value }) {
  return <div className="evidence-value"><span>{label}</span><strong>{value}</strong></div>;
}

function releaseGateName(key) {
  const labels = {
    five_complete_windows: 'Five complete weekday mornings',
    three_real_morning_bundles: 'Three recorded morning bundles',
    independent_otp: 'Independent route comparison',
    performance: 'Performance review',
    licences: 'Source licence review',
    secrets: 'Credential and private-data scan',
    ci: 'Continuous integration',
    static_demo: 'Static demo package',
  };
  return labels[key] || humanLabel(key);
}

function App() {
  const [mode, setMode] = useState(INITIAL_MODE);
  const adapter = useMemo(() => createAdapter(mode, { baseUrl: API_BASE_URL, bundleUrl: BUNDLE_URL }), [mode]);
  const [page, setPage] = useState('replay');
  const [catalog, setCatalog] = useState(null);
  const [snapshots, setSnapshots] = useState([]);
  const [snapshotId, setSnapshotId] = useState('');
  const [display, setDisplay] = useState(null);
  const [choices, setChoices] = useState(null);
  const [network, setNetwork] = useState(null);
  const [savedRuns, setSavedRuns] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [loadingFrame, setLoadingFrame] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [originId, setOriginId] = useState('');
  const [destinationId, setDestinationId] = useState('');
  const [scenarioKind, setScenarioKind] = useState('trip_cancellation');
  const [scenarioTargetId, setScenarioTargetId] = useState('');
  const [delayMinutes, setDelayMinutes] = useState(10);
  const [openingRun, setOpeningRun] = useState(false);
  const [openedRun, setOpenedRun] = useState(null);
  const mountedRef = useRef(true);

  const selectedSnapshot = snapshots[selectedIndex] ?? null;
  const eligible = useMemo(() => eligibleStops(choices, catalog), [choices, catalog]);

  const reloadCatalog = useCallback(async () => {
    setLoadingCatalog(true); setLoadError(null); setCatalog(null); setSnapshots([]); setSnapshotId('');
    setDisplay(null); setChoices(null); setNetwork(null); setSavedRuns([]); setJobs([]); setOpenedRun(null);
    try {
      const [nextCatalog, nextRuns] = await Promise.all([adapter.getCatalog(), adapter.getRuns()]);
      const ordered = [...(nextCatalog.snapshots ?? [])].sort((a, b) => Date.parse(a.snapshot_at) - Date.parse(b.snapshot_at));
      const preferredIndex = ordered.findIndex((item) => item.snapshot_id === nextCatalog.preferred_snapshot_id);
      const initialIndex = preferredIndex >= 0 ? preferredIndex : defaultSnapshotIndex(ordered);
      if (!mountedRef.current) return;
      setCatalog(nextCatalog); setSnapshots(ordered); setSelectedIndex(Math.max(0, initialIndex));
      setSnapshotId(ordered[initialIndex]?.snapshot_id ?? ''); setSavedRuns(nextRuns);
      if (!ordered.length) setLoadError(new Error('This data source has no recorded snapshots yet.'));
    } catch (error) {
      if (mountedRef.current) setLoadError(error);
    } finally {
      if (mountedRef.current) setLoadingCatalog(false);
    }
  }, [adapter]);

  useEffect(() => {
    mountedRef.current = true;
    void reloadCatalog();
    return () => { mountedRef.current = false; };
  }, [reloadCatalog]);

  useEffect(() => {
    if (!snapshotId) return undefined;
    let cancelled = false;
    setLoadingFrame(true); setLoadError(null); setDisplay(null); setChoices(null); setNetwork(null);
    const settle = (request, onSuccess) => request.then((value) => {
      if (!cancelled) onSuccess(value);
    }).catch((error) => {
      if (!cancelled) setLoadError((current) => current ?? error);
    });
    Promise.all([
      settle(adapter.getDisplay(snapshotId), setDisplay),
      settle(adapter.getChoices(snapshotId), setChoices),
      settle(adapter.getNetwork(snapshotId), setNetwork),
    ]).finally(() => { if (!cancelled) setLoadingFrame(false); });
    return () => { cancelled = true; };
  }, [adapter, snapshotId]);

  useEffect(() => {
    if (!selectedSnapshot) return;
    if (!eligible.origins.some((stop) => String(stop.stop_id) === originId)) setOriginId(String(eligible.origins[0]?.stop_id ?? ''));
    if (!eligible.destinations.some((stop) => String(stop.stop_id) === destinationId)) setDestinationId(String(eligible.destinations[0]?.stop_id ?? ''));
  }, [selectedSnapshot, eligible, originId, destinationId]);

  useEffect(() => {
    if (mode !== 'local') return undefined;
    const active = jobs.filter((job) => job.run_id && ['queued', 'running', 'cancellation_requested'].includes(job.status));
    if (!active.length) return undefined;
    let cancelled = false;
    let timer;
    const poll = async () => {
      await Promise.all(active.map(async (job) => {
        try {
          const update = await adapter.getRun(job.run_id);
          if (cancelled) return;
          setJobs((current) => current.map((item) => item.run_id === job.run_id ? {
            ...item,
            status: update.status,
            progress: update.progress ?? item.progress,
            progress_details: update.progress_details ?? item.progress_details,
            result: update.result ?? item.result,
            error: update.error ?? null,
          } : item));
        } catch (error) {
          if (cancelled) return;
          setJobs((current) => current.map((item) => item.run_id === job.run_id ? { ...item, status: 'failed', error: error.message } : item));
        }
      }));
      if (!cancelled) timer = setTimeout(poll, 1200);
    };
    timer = setTimeout(poll, 1000);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [adapter, jobs, mode]);

  useEffect(() => {
    if (!playing || snapshots.length < 2) return undefined;
    const timer = setTimeout(() => {
      setSelectedIndex((current) => {
        const next = current + 1;
        if (next >= snapshots.length) { setPlaying(false); return current; }
        setSnapshotId(snapshots[next].snapshot_id);
        return next;
      });
    }, Math.max(350, 1500 / speed));
    return () => clearTimeout(timer);
  }, [playing, selectedIndex, snapshots, speed]);

  const setFrameIndex = (index) => {
    const bounded = Math.min(Math.max(index, 0), snapshots.length - 1);
    setSelectedIndex(bounded); setSnapshotId(snapshots[bounded]?.snapshot_id ?? '');
  };

  const targetOptions = useMemo(() => {
    if (!choices) return [];
    if (scenarioKind === 'stop_unavailable') return eligible.activeStops;
    if (scenarioKind === 'corridor_closure') {
      const futureTrips = (choices.trips ?? []).filter((trip) => trip.departure_s >= choices.snapshot_s && trip.departure_s < choices.snapshot_s + 3600);
      const stopsById = new Map((choices.stops ?? []).map((stop) => [String(stop.stop_id), stop]));
      return (choices.segments ?? []).filter((segment) => futureTrips.some((trip) => {
        const ids = trip.stop_ids ?? [];
        return ids.some((id, index) => String(id) === String(segment.from_stop_id) && String(ids[index + 1]) === String(segment.to_stop_id));
      })).map((segment) => ({ ...segment, key: `${segment.from_stop_id}:${segment.to_stop_id}`, from: stopsById.get(String(segment.from_stop_id))?.name || segment.from_stop_id, to: stopsById.get(String(segment.to_stop_id))?.name || segment.to_stop_id }))
        .sort((a, b) => `${a.from} ${a.to}`.localeCompare(`${b.from} ${b.to}`)).slice(0, 180);
    }
    return (choices.trips ?? []).filter((trip) => Number.isInteger(trip.departure_s) && trip.departure_s >= choices.snapshot_s && trip.departure_s < choices.snapshot_s + 3600)
      .sort((a, b) => a.departure_s - b.departure_s || a.trip_instance_id.localeCompare(b.trip_instance_id));
  }, [choices, eligible.activeStops, scenarioKind]);

  useEffect(() => {
    const targetValue = (item) => scenarioKind === 'stop_unavailable' ? String(item.stop_id) : scenarioKind === 'corridor_closure' ? item.key : item.trip_instance_id;
    if (!targetOptions.some((item) => targetValue(item) === scenarioTargetId)) setScenarioTargetId(targetOptions.length ? targetValue(targetOptions[0]) : '');
  }, [scenarioKind, scenarioTargetId, targetOptions]);

  const handleSubmit = async () => {
    if (!selectedSnapshot || !choices) return;
    const targetValue = (item) => scenarioKind === 'stop_unavailable' ? String(item.stop_id) : scenarioKind === 'corridor_closure' ? item.key : item.trip_instance_id;
    const target = targetOptions.find((item) => targetValue(item) === scenarioTargetId);
    try {
      const requests = makeFixedRequests({ snapshotId: selectedSnapshot.snapshot_id, originStopId: originId, destinationStopId: destinationId, snapshotS: choices.snapshot_s });
      const scenario = makeScenario({
        kind: scenarioKind,
        target,
        snapshotS: choices.snapshot_s,
        delaySeconds: delayMinutes * 60,
        scenarioId: `scenario-${scenarioKind}-${selectedSnapshot.snapshot_id.slice(0, 8)}-${Date.now().toString(36)}`,
      });
      setJobs(BUDGETS.map((budget) => ({ budget_bus_hours: budget, snapshot_id: selectedSnapshot.snapshot_id, service_date: selectedSnapshot.service_date, status: 'submitting', progress: 0, result: null, error: null })));
      setPage('impact');
      for (const budget of BUDGETS) {
        try {
          const payload = makeExperimentPayload({ snapshotId: selectedSnapshot.snapshot_id, requests, scenario, budgetBusHours: budget });
          const queued = await adapter.createRun(payload);
          setJobs((current) => current.map((job) => job.budget_bus_hours === budget ? {
            ...job,
            run_id: queued.run_id,
            status: queued.status || 'queued',
            progress: queued.progress ?? 0,
            error: null,
            snapshot_id: selectedSnapshot.snapshot_id,
            service_date: selectedSnapshot.service_date,
            requests,
            scenario,
          } : job));
        } catch (error) {
          setJobs((current) => current.map((job) => job.budget_bus_hours === budget ? { ...job, status: 'failed', error: error.message } : job));
        }
      }
      const refreshed = await adapter.getRuns().catch(() => null);
      if (refreshed) setSavedRuns(refreshed);
    } catch (error) {
      setLoadError(error);
    }
  };

  const cancelActiveRuns = async () => {
    const active = jobs.filter((job) => job.run_id && ['queued', 'running'].includes(job.status));
    await Promise.all(active.map(async (job) => {
      try {
        await adapter.cancelRun(job.run_id);
        setJobs((current) => current.map((item) => item.run_id === job.run_id ? { ...item, status: 'cancellation_requested' } : item));
      } catch (error) {
        setJobs((current) => current.map((item) => item.run_id === job.run_id ? { ...item, error: error.message } : item));
      }
    }));
  };

  const openSavedRun = async (run) => {
    setOpeningRun(true);
    try {
      const payload = await adapter.getRun(run.run_id ?? run.id);
      setOpenedRun({ run, payload });
    } finally {
      setOpeningRun(false);
    }
  };

  const switchMode = (value) => { setPlaying(false); setMode(value); };
  const currentError = loadingCatalog ? null : loadError;

  return (
    <div className="app-shell">
      <Header mode={mode} catalog={catalog} snapshot={selectedSnapshot} onModeChange={switchMode} />
      <div className="workspace-shell">
        <Sidebar page={page} onPageChange={setPage} />
        <main className="main-content">
          {loadingCatalog && <div className="loading-state"><div className="spinner" /><span>Opening the recorded service bundle…</span></div>}
          {currentError && !catalog && <div className="empty-panel connection-panel"><div className="empty-symbol large"><Icon name="alert" size={24} /></div><h2>We couldn’t open this data source</h2><p>{currentError.message}</p><div className="connection-actions"><button className="button button-primary" onClick={() => void reloadCatalog()}>Try again</button><button className="button button-secondary" onClick={() => switchMode(mode === 'local' ? 'static' : 'local')}>Open {mode === 'local' ? 'static bundle' : 'local API'}</button></div><small>{mode === 'local' ? 'Start the replay service on 127.0.0.1:8000, or open the prepared static bundle.' : 'The static bundle must be available beside this site.'}</small></div>}
          {catalog && <>
            {page === 'replay' && <ReplayView catalog={catalog} snapshot={selectedSnapshot} snapshots={snapshots} selectedIndex={selectedIndex} onSelectIndex={setFrameIndex} playing={playing} onPlayToggle={() => setPlaying((value) => !value)} speed={speed} onSpeedChange={setSpeed} display={display} choices={choices} network={network} loading={loadingFrame} loadError={loadError} onRetry={() => void reloadCatalog()} />}
            {page === 'impact' && <ImpactView mode={mode} catalog={catalog} snapshot={selectedSnapshot} choices={choices} network={network} eligible={eligible} savedRunCount={savedRuns.length} kind={scenarioKind} setKind={setScenarioKind} targetId={scenarioTargetId} setTargetId={setScenarioTargetId} originId={originId} setOriginId={setOriginId} destinationId={destinationId} setDestinationId={setDestinationId} delayMinutes={delayMinutes} setDelayMinutes={setDelayMinutes} jobs={jobs} onRun={handleSubmit} onCancel={cancelActiveRuns} onNavigate={setPage} />}
            {page === 'recovery' && <RecoveryView jobs={jobs} savedRuns={savedRuns} snapshots={snapshots} network={network} networkSnapshotId={selectedSnapshot?.snapshot_id} adapter={adapter} onRefresh={() => void reloadCatalog()} mode={mode} />}
            {page === 'evidence' && <EvidenceView catalog={catalog} snapshot={selectedSnapshot} snapshots={snapshots} display={display} choices={choices} runs={savedRuns} loading={loadingFrame} />}
          </>}
          <footer className="app-footer"><span>Brisbane Transport Resilience Lab</span><span>Recorded inputs · hypothetical scenarios</span><span style={{ minWidth: 0, maxWidth: '70vw', textAlign: 'right', lineHeight: 1.5 }}>{TRANSLINK_ATTRIBUTION}</span></footer>
        </main>
      </div>
    </div>
  );
}

export default App;
