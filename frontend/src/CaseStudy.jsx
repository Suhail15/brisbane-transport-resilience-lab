import { useState } from 'react';
import './case-study.css';

function records(value) {
  if (Array.isArray(value)) return value;
  if (value && typeof value === 'object') return Object.values(value);
  return [];
}

function formatLabel(value) {
  return String(value ?? '')
    .replaceAll('_', ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^\w/, (letter) => letter.toUpperCase());
}

function formatCount(value) {
  return Number.isFinite(value) ? new Intl.NumberFormat('en-AU').format(value) : value === null ? 'Not available' : 'Not included';
}

function formatMeasure(value) {
  return Number.isFinite(value) ? new Intl.NumberFormat('en-AU', { maximumFractionDigits: 2 }).format(value) : value === null ? 'Not available' : 'Not included';
}

export function queryMinutesPerBusHourLabel(value, usedBusHours) {
  if (value === null && usedBusHours === 0) return 'Not defined · zero cost';
  if (value === null) return 'Not available';
  return formatMeasure(value);
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return seconds === null ? 'Not available' : 'Not included';
  const minutes = Math.round(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return hours ? `${hours}h ${String(remainder).padStart(2, '0')}m` : `${minutes} min`;
}

function formatJourneyDuration(seconds) {
  if (seconds === null) return 'Unreachable';
  return Number.isFinite(seconds) ? formatDuration(seconds) : 'Not included';
}

function formatBusHours(value) {
  if (!Number.isFinite(value)) return value === null ? 'Not available' : 'Not included';
  return `${new Intl.NumberFormat('en-AU', { maximumFractionDigits: 2 }).format(value)} bus-hours`;
}

function formatTimestamp(value) {
  if (!value) return 'Not included';
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return 'Invalid timestamp';
  return new Intl.DateTimeFormat('en-AU', {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    timeZone: 'Australia/Brisbane', timeZoneName: 'short',
  }).format(date);
}

function formatServiceTime(serviceDate, serviceSeconds) {
  if (!Number.isInteger(serviceSeconds) || !/^\d{4}-\d{2}-\d{2}$/.test(serviceDate ?? '')) return 'Not included';
  const date = new Date(`${serviceDate}T00:00:00+10:00`);
  date.setTime(date.getTime() + serviceSeconds * 1000);
  if (!Number.isFinite(date.getTime())) return 'Not included';
  return new Intl.DateTimeFormat('en-AU', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: 'Australia/Brisbane',
  }).format(date);
}

function fieldValue(value) {
  if (value === null) return 'Not available';
  if (value === undefined || value === '') return 'Not included';
  if (typeof value === 'boolean' || typeof value === 'number' || typeof value === 'string') return String(value);
  if (Array.isArray(value)) return value.map(fieldValue).join(', ');
  return Object.entries(value).map(([key, entry]) => `${formatLabel(key)}: ${fieldValue(entry)}`).join(' · ');
}

function namedEntries(value) {
  if (Array.isArray(value)) return value.map((entry, index) => [String(index), entry]);
  if (value && typeof value === 'object') return Object.entries(value);
  return [];
}

export function resolveCaseStudySelection(study, dateChoice = '', budgetChoice = '') {
  const dates = records(study?.dates);
  const selectedDate = dates.find((item) => String(item?.date ?? '') === dateChoice)
    ?? dates.find((item) => item?.role === 'confirmation')
    ?? dates[0]
    ?? null;
  const budgets = [...records(selectedDate?.budgets)].sort((left, right) => (left?.budget_bus_hours ?? Infinity) - (right?.budget_bus_hours ?? Infinity));
  const selectedBudget = budgets.find((item) => String(item?.budget_bus_hours ?? '') === budgetChoice)
    ?? budgets.find((item) => item?.budget_bus_hours === 2)
    ?? budgets[0]
    ?? null;
  const sensitivities = [...records(selectedDate?.sensitivities)]
    .filter((item) => selectedBudget && item?.budget_bus_hours === selectedBudget.budget_bus_hours)
    .sort((left, right) => (left?.additional_bus_seconds ?? Infinity) - (right?.additional_bus_seconds ?? Infinity));
  const example = selectedBudget?.example ?? selectedDate?.example ?? null;
  return { dates, selectedDate, budgets, selectedBudget, sensitivities, example };
}

export function stressAvailabilityMessage(budgetBusHours) {
  return budgetBusHours === 2
    ? 'Each row compares the same two bus-hour budget under an assumed running-time increase for existing and extra buses. Lost and restored journeys are calculated within that row. These are hypothetical sensitivity cases, not observed delays.'
    : 'This study tests running-time stress at two bus-hours. Select 2 bus-hours to view those sensitivity results.';
}

function policyName(key, policy) {
  if (policy && typeof policy === 'object') {
    const name = policy.name ?? policy.choice ?? policy.label ?? policy.policy;
    if (name != null) return String(name);
  }
  return formatLabel(key) || 'Policy comparison';
}

function Metric({ label, value, detail }) {
  return <div className="cstudy-metric"><span>{label}</span><strong>{value}</strong>{detail && <small>{detail}</small>}</div>;
}

function Section({ eyebrow, title, children, className = '' }) {
  return <section className={`cstudy-panel ${className}`}>
    <div className="cstudy-panel-heading"><div><span className="cstudy-eyebrow">{eyebrow}</span><h2>{title}</h2></div></div>
    {children}
  </section>;
}

function CaseStudy({ study }) {
  const [dateChoice, setDateChoice] = useState('');
  const [budgetChoice, setBudgetChoice] = useState('');
  const { dates, selectedDate, budgets, selectedBudget, sensitivities, example } = resolveCaseStudySelection(study, dateChoice, budgetChoice);
  const policies = namedEntries(selectedBudget?.policies);
  const protocol = study?.protocol ?? {};
  const assumptions = study?.assumptions;
  const assumptionEntries = namedEntries(assumptions);
  const evidence = records(study?.evidence).filter((item) => {
    try { return new URL(item?.url).protocol === 'https:'; } catch { return false; }
  });
  const exampleRequest = example?.request && typeof example.request === 'object' ? example.request : {};
  const exampleOrigin = example?.origin_name ?? example?.origin?.name ?? exampleRequest.origin_name ?? exampleRequest.origin?.name;
  const exampleDestination = example?.destination_name ?? example?.destination?.name ?? exampleRequest.destination_name ?? exampleRequest.destination?.name;
  const exampleRequestId = example?.request_id ?? exampleRequest.request_id ?? exampleRequest.id;
  const exampleDeparture = example?.departure_s ?? exampleRequest.departure_s;
  const hasImpactCount = selectedDate != null && Object.hasOwn(selectedDate, 'impacted_count');
  const hasAddedCappedDuration = selectedDate != null && Object.hasOwn(selectedDate, 'added_capped_duration_s');
  const meanAddedSeconds = !hasAddedCappedDuration ? undefined
    : selectedDate.added_capped_duration_s === null ? null
      : Number.isFinite(selectedDate.added_capped_duration_s) && Number.isFinite(selectedDate.request_count) && selectedDate.request_count > 0
        ? selectedDate.added_capped_duration_s / selectedDate.request_count : undefined;

  const changeDate = (value) => {
    setDateChoice(value);
    const nextBudget = resolveCaseStudySelection(study, value).selectedBudget;
    setBudgetChoice(nextBudget ? String(nextBudget.budget_bus_hours ?? '') : '');
  };

  const question = study?.question || 'Study question not included.';
  const title = study?.title || 'Corridor impact case study';
  const hasStudy = Boolean(study && typeof study === 'object');

  return <div className="cstudy">
    <header className="cstudy-heading">
      <div><span className="cstudy-eyebrow">Separate corridor impact study</span><h1>{title}</h1><p>{question}</p></div>
      {study?.classification != null && <span className="cstudy-classification">{fieldValue(study.classification)}</span>}
    </header>

    {!hasStudy && <div className="cstudy-empty" role="status">
      <strong>No corridor case study is available.</strong>
      <span>This section appears when a reviewed study record is supplied.</span>
    </div>}

    {hasStudy && <>
      <section className="cstudy-overview" aria-label="Study context">
        <section className="cstudy-panel cstudy-context-panel">
          <div className="cstudy-selectors">
            {dates.length ? <label className="cstudy-control"><span>Study date</span><select aria-label="Study date" value={selectedDate?.date ?? ''} onChange={(event) => changeDate(event.target.value)}>
              {dates.map((item, index) => <option key={`${item?.date ?? 'date'}-${index}`} value={item?.date ?? ''}>{item?.date ?? 'Date not included'} · {formatLabel(item?.role) || 'role not included'}</option>)}
            </select></label> : <div className="cstudy-empty-inline">No study dates are included in this record.</div>}
            <label className="cstudy-control"><span>Bus-hour budget</span><select aria-label="Bus-hour budget" value={selectedBudget?.budget_bus_hours ?? ''} onChange={(event) => setBudgetChoice(event.target.value)} disabled={!budgets.length}>
              {budgets.length ? budgets.map((item, index) => <option key={`${item?.budget_bus_hours ?? 'budget'}-${index}`} value={item?.budget_bus_hours ?? ''}>{formatBusHours(item?.budget_bus_hours)}</option>) : <option value="">No budget results</option>}
            </select></label>
          </div>
          {selectedDate && <div className="cstudy-date-meta">
            <span><strong>Study role</strong>{formatLabel(selectedDate.role) || 'Not included'}</span>
            <span><strong>Snapshot cutoff · Brisbane</strong>{formatTimestamp(selectedDate.snapshot_at)}</span>
            <span><strong>Fixed test journeys · denominator</strong>{formatCount(selectedDate.request_count)}</span>
          </div>}
          {selectedBudget?.run_id && <span className="cstudy-run-id">Run ID {selectedBudget.run_id}</span>}
        </section>

        <section className="cstudy-panel cstudy-story">
          <span className="cstudy-eyebrow">Simulated disruption</span>
          <h2>{study.disruption ? 'What changes in this scenario' : 'Disruption details'}</h2>
          <p>{study.disruption || 'Disruption description not included.'}</p>
          <p className="cstudy-limit">Recovery duties are hypothetical. Results describe fixed test journeys, not passenger outcomes or fleet availability.</p>
        </section>
      </section>

      {selectedDate && <>
        <Section eyebrow="Reachability under disruption" title="Fixed query set · 60-minute threshold" className="cstudy-reachability">
          <div className="cstudy-metrics cstudy-metrics-three">
            <Metric label="Baseline reachable" value={`${formatCount(selectedDate.baseline_within60_count)} / ${formatCount(selectedDate.request_count)}`} detail="Test journeys within 60 minutes" />
            <Metric label="During disruption" value={`${formatCount(selectedDate.disrupted_within60_count)} / ${formatCount(selectedDate.request_count)}`} detail="Same fixed test journeys and threshold" />
            <Metric label="Lost from baseline" value={formatCount(selectedDate.lost_count)} detail="Baseline journeys no longer within 60 minutes" />
          </div>
          {(hasImpactCount || hasAddedCappedDuration) && <div className="cstudy-metrics cstudy-impact-metrics">
            {hasImpactCount && <Metric label="Impacted fixed queries" value={formatCount(selectedDate.impacted_count)} detail="Count from the study record" />}
            {hasAddedCappedDuration && <Metric label="Added capped time across all fixed queries" value={formatDuration(selectedDate.added_capped_duration_s)} detail={`${formatCount(selectedDate.added_capped_duration_s)} exact seconds · 90-minute cap per query`} />}
            {hasAddedCappedDuration && <Metric label="Mean added seconds per fixed query" value={meanAddedSeconds === null ? 'Not available' : Number.isFinite(meanAddedSeconds) ? `${formatMeasure(meanAddedSeconds)} seconds` : selectedDate.request_count === 0 ? 'Not defined · no test queries' : 'Not included'} detail={`Across ${formatCount(selectedDate.request_count)} fixed test queries`} />}
          </div>}
          <p className="cstudy-footnote">This study date is independent of the replay selection. Counts are model outputs for a fixed test workload, not passenger reachability.</p>
        </Section>

        <Section eyebrow="Recovery budget" title="Cost and outcome comparison" className="cstudy-budget">
          <div className="cstudy-table-wrap">
            <table className="cstudy-table">
              <caption>Resource trade-off across all registered budgets · same fixed queries and base running time.</caption>
              <thead><tr><th scope="col">Budget</th><th scope="col">Actually used</th><th scope="col">Journeys restored</th><th scope="col">Queries improved</th><th scope="col">Total capped time saved</th></tr></thead>
              <tbody>{budgets.map((item) => <tr key={item.budget_bus_hours}>
                <th scope="row">{formatBusHours(item.budget_bus_hours)}</th>
                <td>{formatBusHours(item.used_bus_hours)}</td><td>{formatCount(item.restored_count)}</td>
                <td>{formatCount(item.improved_count)}</td>
                <td>{formatDuration(item.saved_capped_duration_s)}<small>{formatCount(item.saved_capped_duration_s)} exact seconds</small></td>
              </tr>)}</tbody>
            </table>
          </div>
          {selectedBudget ? <>
            <div className="cstudy-metrics cstudy-budget-metrics">
              <Metric label="Buses in plan" value={formatCount(selectedBudget.bus_count)} />
              <Metric label="Bus-hours used" value={formatBusHours(selectedBudget.used_bus_hours)} detail={`Budget: ${formatBusHours(selectedBudget.budget_bus_hours)}`} />
              <Metric label="Journeys restored" value={formatCount(selectedBudget.restored_count)} detail="Fixed test journeys" />
              <Metric label="Recovered within 60 minutes" value={formatCount(selectedBudget.recovered_within60_count)} detail={`Of ${formatCount(selectedDate.request_count)} fixed journeys`} />
              <Metric label="Saved capped journey time" value={formatDuration(selectedBudget.saved_capped_duration_s)} detail="90-minute cap across the fixed query set" />
              {Number.isFinite(selectedBudget.impacted_saved_capped_duration_s) && <Metric label="Saved time among closure-delayed journeys" value={formatDuration(selectedBudget.impacted_saved_capped_duration_s)} detail="The fixed nominally delayed cohort; excludes gains for other journeys" />}
              <Metric label="Improved journeys" value={formatCount(selectedBudget.improved_count)} detail="Fixed test journeys" />
              <Metric label="Saved query-minutes per bus-hour" value={queryMinutesPerBusHourLabel(selectedBudget.saved_query_minutes_per_bus_hour, selectedBudget.used_bus_hours)} detail="Fixed test workload measure; not a financial return" />
            </div>
            {Number.isFinite(selectedBudget.impacted_saved_capped_duration_s) && <p className="cstudy-footnote">Of the saved capped time, {formatDuration(selectedBudget.impacted_saved_capped_duration_s)} is among the {formatCount(selectedDate.impacted_count)} queries delayed by the nominal closure; {formatDuration(selectedBudget.other_saved_capped_duration_s)} is among the remaining queries.</p>}
            {Number.isFinite(selectedBudget.after_closure_saved_capped_duration_s) && <p className="cstudy-footnote">{formatDuration(selectedBudget.after_closure_saved_capped_duration_s)} of saved capped time comes from queries whose recovered arrival is after the closure ends. Full two-hour duty costs are included.</p>}
            <div className="cstudy-table-wrap">
              <table className="cstudy-table">
                <caption>Compared policies for this budget. An unavailable policy remains unavailable.</caption>
                <thead><tr><th scope="col">Compared choice</th><th scope="col">Journeys restored</th><th scope="col">Total capped test-journey time</th><th scope="col">Bus-hours used</th></tr></thead>
                <tbody>{policies.length ? policies.map(([key, policy], index) => <tr key={`${key}-${index}`} className={policy == null ? 'cstudy-unavailable-row' : undefined}>
                  <th scope="row">{policyName(key, policy)}{policy == null && <small>Not available in this record</small>}</th>
                  <td>{policy == null ? 'Not available' : formatCount(policy.restored_count)}</td>
                  <td>{policy == null ? 'Not available' : Number.isFinite(policy.total_capped_duration_s)
                    ? <>{formatDuration(policy.total_capped_duration_s)}<small>{formatCount(policy.total_capped_duration_s)} exact seconds</small></>
                    : formatDuration(policy.total_capped_duration_s)}</td>
                  <td>{policy == null ? 'Not available' : formatBusHours(policy.used_bus_hours)}</td>
                </tr>) : <tr><td colSpan="4" className="cstudy-table-empty">Policy comparisons not included for this budget.</td></tr>}</tbody>
              </table>
            </div>
          </> : <div className="cstudy-empty-inline">No budget results are included for this study date.</div>}
        </Section>

        <Section eyebrow="Sensitivity" title="Hypothetical bus running-time stress" className="cstudy-stress">
          <p className="cstudy-section-note">{stressAvailabilityMessage(selectedBudget?.budget_bus_hours)}</p>
          <div className="cstudy-table-wrap">
            <table className="cstudy-table">
              <caption>Stress outcomes for {selectedBudget ? formatBusHours(selectedBudget.budget_bus_hours) : 'the selected budget'}.</caption>
              <thead><tr><th scope="col">Additional bus seconds</th><th scope="col">Buses in plan</th><th scope="col">Lost within 60 minutes</th><th scope="col">Journeys restored</th><th scope="col">Recovered within 60 minutes</th><th scope="col">Capped time saved</th><th scope="col">Improved journeys</th><th scope="col">Bus-hours used</th><th scope="col">Query-minutes per bus-hour</th><th scope="col">Run ID</th></tr></thead>
              <tbody>{selectedBudget?.budget_bus_hours === 2 && sensitivities.length ? sensitivities.map((item, index) => <tr key={`${item?.additional_bus_seconds ?? 'stress'}-${index}`}>
                <th scope="row">{Number.isFinite(item?.additional_bus_seconds) ? item.additional_bus_seconds === 0 ? '0 · base running time' : `${formatCount(item.additional_bus_seconds)} · hypothetical` : 'Assumption not included'}</th>
                <td>{formatCount(item?.bus_count)}</td><td>{formatCount(item?.lost_count)}<small>{formatCount(item?.baseline_within60_count)} → {formatCount(item?.disrupted_within60_count)} before recovery</small></td><td>{formatCount(item?.restored_count)}</td><td>{formatCount(item?.recovered_within60_count)}</td><td>{formatDuration(item?.saved_capped_duration_s)}</td><td>{formatCount(item?.improved_count)}</td><td>{formatBusHours(item?.used_bus_hours)}</td>
                <td>{queryMinutesPerBusHourLabel(item?.saved_query_minutes_per_bus_hour, item?.used_bus_hours)}</td><td>{item?.run_id ?? 'Not included'}</td>
              </tr>) : <tr><td colSpan="10" className="cstudy-table-empty">{selectedBudget?.budget_bus_hours === 2
                ? 'No sensitivity outcomes are included for this study date and two bus-hour budget.'
                : 'This study tests stress at two bus-hours only. Select 2 bus-hours to inspect those outcomes.'}</td></tr>}</tbody>
            </table>
          </div>
        </Section>

        <Section eyebrow="Example journey" title="One fixed test request" className="cstudy-example">
          {example ? <>
            <div className="cstudy-journey-route"><span>{exampleOrigin || 'Origin not included'}</span><span className="cstudy-route-arrow" aria-hidden="true">→</span><span>{exampleDestination || 'Destination not included'}</span></div>
            <p className="cstudy-journey-id">Test request {exampleRequestId || 'ID not included'} · departure {formatServiceTime(selectedDate.date, exampleDeparture)} Brisbane time</p>
            <div className="cstudy-metrics cstudy-metrics-three cstudy-duration-metrics">
              <Metric label="Baseline duration" value={formatJourneyDuration(example.baseline_duration_s)} />
              <Metric label="During disruption" value={formatJourneyDuration(example.disrupted_duration_s)} />
              <Metric label="After recovery" value={formatJourneyDuration(example.recovered_duration_s)} detail={example.recovered_duration_s === null ? 'No recovered route for this request' : undefined} />
            </div>
            <p className="cstudy-footnote">A journey marked unreachable has no route duration in this simulation. It is one test request, not a passenger account.</p>
          </> : <div className="cstudy-empty-inline">No example journey is included for this study date.</div>}
        </Section>
      </>}

      <details className="cstudy-panel cstudy-method">
        <summary><span className="cstudy-eyebrow">Method and evidence</span><strong>Protocol, assumptions and sources</strong></summary>
        <div className="cstudy-method-content">
          <div className="cstudy-method-grid">
            <div><h3>Protocol</h3><dl className="cstudy-details">
              <div><dt>Version</dt><dd>{fieldValue(protocol.version)}</dd></div>
              <div><dt>Selected snapshot ID</dt><dd>{fieldValue(selectedDate?.snapshot_id)}</dd></div>
              <div><dt>Protocol hash</dt><dd className="cstudy-hash">{fieldValue(protocol.hash ?? protocol.protocol_hash ?? protocol.hash_sha256 ?? protocol.sha256)}</dd></div>
              <div><dt>Selection rule</dt><dd>{fieldValue(protocol.selection_rule)}</dd></div>
              <div><dt>Reachability threshold</dt><dd>60 minutes</dd></div>
              <div><dt>Capped duration threshold</dt><dd>90 minutes</dd></div>
            </dl></div>
            <div><h3>Assumptions</h3>{Array.isArray(assumptions) ? assumptions.length
              ? <ul className="cstudy-assumption-list">{assumptions.map((value, index) => <li key={index}>{fieldValue(value)}</li>)}</ul>
              : <p className="cstudy-section-note">Assumptions not included in this record.</p>
              : assumptionEntries.length ? <dl className="cstudy-details">{assumptionEntries.map(([key, value], index) => <div key={`${key}-${index}`}><dt>{formatLabel(key) || `Assumption ${index + 1}`}</dt><dd>{fieldValue(value)}</dd></div>)}</dl>
                : <p className="cstudy-section-note">Assumptions not included in this record.</p>}</div>
          </div>
          <div className="cstudy-evidence"><h3>Evidence links</h3>{evidence.length ? <ul>{evidence.map((item, index) => <li key={`${item.url}-${index}`}><a href={item.url} target="_blank" rel="noreferrer">{item.title || item.label || item.url}</a></li>)}</ul> : <p className="cstudy-section-note">No HTTPS evidence links are included.</p>}</div>
        </div>
      </details>
    </>}
  </div>;
}

export default CaseStudy;
