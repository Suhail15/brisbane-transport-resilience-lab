import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const repositoryDirectory = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const frontendDirectory = resolve(repositoryDirectory, 'frontend');
const frontendRequire = createRequire(resolve(frontendDirectory, 'package.json'));
const { createServer } = await import(frontendRequire.resolve('vite'));
const React = frontendRequire('react');
const { renderToStaticMarkup } = frontendRequire('react-dom/server');

function fixtureStudy() {
  return {
    study_id: 'fixture-only-ui-test',
    title: 'Fixture only: corridor case study',
    question: 'How does the fixture disruption change this fixed test query set?',
    disruption: 'Fixture disruption description for component rendering checks.',
    classification: 'Fixture values · not study findings',
    protocol: { version: 'fixture-v1', hash: 'fixture-hash', selection_rule: 'Fixture selection rule' },
    assumptions: { example: 'Fixture assumption' },
    evidence: [{ title: 'Fixture source', url: 'https://example.invalid/fixture-evidence' }],
    dates: [
      {
        date: '2026-10-24', role: 'fixture second date', snapshot_id: 'fixture-snapshot-b',
        snapshot_at: '2026-10-24T07:00:00+10:00', request_count: 1,
        baseline_within60_count: 1, disrupted_within60_count: 1, lost_count: 0,
        budgets: [
          { budget_bus_hours: 2, used_bus_hours: 2, bus_count: 1, restored_count: 0, recovered_within60_count: 1, saved_capped_duration_s: 0, improved_count: 0, saved_query_minutes_per_bus_hour: 0, policies: {} },
          { budget_bus_hours: 4, used_bus_hours: 2, bus_count: 1, restored_count: 0, recovered_within60_count: 1, saved_capped_duration_s: 0, improved_count: 0, saved_query_minutes_per_bus_hour: 0, policies: {} },
        ],
        sensitivities: [], example: null,
      },
      {
        date: '2026-10-19', role: 'confirmation', snapshot_id: 'fixture-snapshot-a',
        snapshot_at: '2026-10-19T06:00:00+10:00', request_count: 2,
        baseline_within60_count: 2, disrupted_within60_count: 1, lost_count: 1,
        impacted_count: 1, added_capped_duration_s: 1200,
        budgets: [
          {
            budget_bus_hours: 2, used_bus_hours: 2, bus_count: 1, restored_count: 1,
            recovered_within60_count: 2, saved_capped_duration_s: 600, improved_count: 1,
            saved_query_minutes_per_bus_hour: 5, run_id: 'fixture-run-two',
            policies: {
              'fixture available policy': { restored_count: 1, total_capped_duration_s: 9000, used_bus_hours: 2 },
              'fixture zero-cost policy': { restored_count: 0, total_capped_duration_s: 9000, used_bus_hours: 0 },
              'fixture missing-cost policy': { restored_count: null, total_capped_duration_s: null, used_bus_hours: null },
              'fixture unavailable policy': null,
            },
            example: { request: { request_id: 'fixture-budget-request', departure_s: 21600 }, origin_name: 'Fixture budget origin', destination_name: 'Fixture destination', baseline_duration_s: 600, disrupted_duration_s: null, recovered_duration_s: null },
          },
          {
            budget_bus_hours: 0, used_bus_hours: 0, bus_count: 0, restored_count: 0,
            recovered_within60_count: 1, saved_capped_duration_s: 0, improved_count: 0,
            saved_query_minutes_per_bus_hour: null, run_id: 'fixture-run-zero',
            policies: { 'fixture zero-cost policy': { restored_count: 0, total_capped_duration_s: 10800, used_bus_hours: 0 }, 'fixture unavailable policy': null },
          },
        ],
        sensitivities: [
          { budget_bus_hours: 2, additional_bus_seconds: 0, bus_count: 1, used_bus_hours: 2, restored_count: 1, recovered_within60_count: 2, saved_capped_duration_s: 600, improved_count: 1, saved_query_minutes_per_bus_hour: 5, run_id: 'fixture-stress-zero' },
          { budget_bus_hours: 2, additional_bus_seconds: 300, bus_count: null, used_bus_hours: null, restored_count: null, recovered_within60_count: null, saved_capped_duration_s: null, improved_count: null, saved_query_minutes_per_bus_hour: null, run_id: 'fixture-stress-300' },
          { budget_bus_hours: 2, additional_bus_seconds: 600, bus_count: 1, used_bus_hours: 2, restored_count: 0, recovered_within60_count: 1, saved_capped_duration_s: 0, improved_count: 0, saved_query_minutes_per_bus_hour: 0, run_id: 'fixture-stress-600' },
        ],
        example: { request_id: 'fixture-request', origin_name: 'Fixture origin', destination_name: 'Fixture destination', departure_s: 21600, baseline_duration_s: 600, disrupted_duration_s: null, recovered_duration_s: null },
      },
    ],
  };
}

async function loadComponent(t) {
  const server = await createServer({
    configFile: resolve(frontendDirectory, 'vite.config.js'),
    root: frontendDirectory,
    server: { middlewareMode: true },
    appType: 'custom',
  });
  t.after(() => server.close());
  return server.ssrLoadModule('/src/CaseStudy.jsx');
}

function markup(Component, study) {
  return renderToStaticMarkup(React.createElement(Component, { study }));
}

test('case study renders selected date context, fixed-query counts, budget controls and a nullable journey', async (t) => {
  const { default: CaseStudy } = await loadComponent(t);
  const html = markup(CaseStudy, fixtureStudy());

  assert.match(html, /Fixture only: corridor case study/);
  assert.match(html, /Study role/);
  assert.match(html, /Confirmation/);
  assert.match(html, /Snapshot cutoff · Brisbane/);
  assert.match(html, /Fixed test journeys · denominator/);
  assert.match(html, /aria-label="Study date"/);
  assert.match(html, /aria-label="Bus-hour budget"/);
  assert.ok(html.indexOf('Snapshot cutoff · Brisbane') < html.indexOf('Baseline reachable'));
  assert.ok(html.indexOf('Simulated disruption') < html.indexOf('Baseline reachable'));
  const detailsStart = html.indexOf('<details class="cstudy-panel cstudy-method">');
  assert.ok(detailsStart > html.indexOf('Baseline reachable'));
  assert.ok(html.indexOf('fixture-snapshot-a') > detailsStart);
  assert.ok(html.indexOf('fixture-hash') > detailsStart);
  assert.match(html, /Baseline reachable/);
  assert.match(html, /2 \/ 2/);
  assert.match(html, /During disruption/);
  assert.match(html, /Lost from baseline/);
  assert.match(html, /Bus-hour budget/);
  assert.match(html, /2 bus-hours/);
  assert.match(html, /Impacted fixed queries/);
  assert.match(html, /Added capped time across all fixed queries/);
  assert.match(html, /1,200 exact seconds/);
  assert.match(html, /600 seconds/);
  assert.match(html, /9,000 exact seconds/);
  assert.match(html, /0 bus-hours/);
  assert.match(html, /Fixture unavailable policy/);
  assert.match(html, /Fixture missing-cost policy/);
  assert.match(html, /Not available in this record/);
  assert.match(html, /Hypothetical bus running-time stress/);
  assert.match(html, /Fixture budget origin/);
  assert.match(html, /fixture-budget-request/);
  assert.match(html, /Unreachable/);
  assert.match(html, /fixed test journeys, not passenger outcomes/i);
  assert.match(html, /https:\/\/example\.invalid\/fixture-evidence/);
});

test('confirmation date and two-hour budget are preferred; date and budget choices resolve exact cases', async (t) => {
  const { resolveCaseStudySelection, stressAvailabilityMessage } = await loadComponent(t);
  const study = fixtureStudy();
  const before = structuredClone(study);

  const firstDate = resolveCaseStudySelection(study);
  assert.equal(firstDate.selectedDate.date, '2026-10-19');
  assert.equal(firstDate.selectedDate.role, 'confirmation');
  assert.equal(firstDate.selectedBudget.budget_bus_hours, 2);
  assert.equal(firstDate.sensitivities.length, 3);
  assert.equal(firstDate.sensitivities[0].additional_bus_seconds, 0);
  assert.equal(firstDate.example.origin_name, 'Fixture budget origin');
  assert.equal(firstDate.example.request.request_id, 'fixture-budget-request');

  const selected = resolveCaseStudySelection(study, '2026-10-19', '2');
  assert.equal(selected.selectedDate.snapshot_id, 'fixture-snapshot-a');
  assert.equal(selected.selectedBudget.run_id, 'fixture-run-two');
  assert.equal(selected.sensitivities.length, 3);
  assert.deepEqual(selected.sensitivities.map((item) => item.additional_bus_seconds), [0, 300, 600]);

  const zeroBudget = resolveCaseStudySelection(study, '2026-10-19', '0');
  assert.equal(zeroBudget.selectedBudget.used_bus_hours, 0);
  assert.equal(zeroBudget.selectedBudget.saved_query_minutes_per_bus_hour, null);
  assert.equal(zeroBudget.sensitivities.length, 0);
  assert.match(stressAvailabilityMessage(0), /tests running-time stress at two bus-hours\. Select 2 bus-hours/);

  const otherDate = resolveCaseStudySelection(study, '2026-10-24', '4');
  assert.equal(otherDate.selectedDate.request_count, 1);
  assert.equal(otherDate.selectedBudget.budget_bus_hours, 4);
  assert.equal(otherDate.sensitivities.length, 0);
  const dateChange = resolveCaseStudySelection(study, '2026-10-24');
  assert.equal(dateChange.selectedBudget.budget_bus_hours, 2);
  assert.deepEqual(study, before);
});

test('nullable policies, stress results and missing study data stay distinct from zero', async (t) => {
  const { default: CaseStudy, queryMinutesPerBusHourLabel } = await loadComponent(t);
  const html = markup(CaseStudy, fixtureStudy());
  const empty = markup(CaseStudy, null);
  const emptyDates = markup(CaseStudy, { study_id: 'fixture-empty-dates', dates: [] });
  const zeroOnlyStudy = fixtureStudy();
  zeroOnlyStudy.dates = [zeroOnlyStudy.dates.find((date) => date.role === 'confirmation')];
  zeroOnlyStudy.dates[0].budgets = zeroOnlyStudy.dates[0].budgets.filter((budget) => budget.budget_bus_hours === 0);
  const zeroBudgetHtml = markup(CaseStudy, zeroOnlyStudy);

  assert.match(html, /Not available/);
  assert.match(html, /0 min/);
  assert.match(empty, /No corridor case study is available/);
  assert.match(emptyDates, /No study dates are included in this record/);
  assert.match(html, /0 bus-hours/);
  assert.match(html, /Unreachable/);
  assert.doesNotMatch(empty, /Bus-hour budget/);
  assert.match(zeroBudgetHtml, /Not defined · zero cost/);
  assert.match(zeroBudgetHtml, /This study tests running-time stress at two bus-hours\. Select 2 bus-hours/);
  assert.equal(queryMinutesPerBusHourLabel(null, 0), 'Not defined · zero cost');
  assert.equal(queryMinutesPerBusHourLabel(null, null), 'Not available');
  assert.equal(queryMinutesPerBusHourLabel(0, 0), '0');
});
