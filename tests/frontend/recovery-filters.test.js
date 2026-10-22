import test from 'node:test';
import assert from 'node:assert/strict';
import {
  DEFAULT_RECOVERY_FILTERS, filterRecoveryRuns, recoveryFilterOptions, recoveryRecordingDate,
} from '../../frontend/src/domain.js';

const dates = ['2026-10-19', '2026-10-20', '2026-10-21'];
const kinds = ['trip_cancellation', 'stop_unavailable', 'corridor_closure', 'additional_delay'];
function entries() {
  return dates.flatMap((date) => kinds.flatMap((scenario) => [
    ...[0, 2, 4, 8].map((budget) => ({ run: { run_id: `${date}:${scenario}:0:${budget}` },
      summary: { serviceDate: date, scenarioKinds: [scenario], sensitivity: 0, budget, groupKey: `${date}:${scenario}:0` } })),
    ...(scenario === 'stop_unavailable' ? [300, 600].map((sensitivity) => ({
      run: { run_id: `${date}:${scenario}:${sensitivity}:2` },
      summary: { serviceDate: date, scenarioKinds: [scenario], sensitivity, budget: 2, groupKey: `${date}:${scenario}:${sensitivity}` },
    })) : []),
  ]));
}

test('initial filters follow the declared first final date and paired sensitivity protocol', () => {
  assert.deepEqual(DEFAULT_RECOVERY_FILTERS, { date: '2026-10-19', scenario: 'stop_unavailable', sensitivity: '0' });
  const shown = filterRecoveryRuns(entries());
  assert.equal(shown.length, 4);
  assert.deepEqual(shown.map(({ summary }) => summary.budget), [0, 2, 4, 8]);
});

test('actual available options preserve all dates, scenario kinds and stress assumptions', () => {
  const all = entries();
  const before = structuredClone(all);
  assert.equal(all.length, 54);
  assert.deepEqual(recoveryFilterOptions(all), { dates, scenarios: [...kinds].sort(), sensitivities: ['0', '300', '600'] });
  assert.deepEqual(all, before);
  assert.deepEqual(recoveryFilterOptions([]), { dates: [], scenarios: [], sensitivities: [] });
});

test('all available exact combinations are accessible and unsupported combinations remain empty', () => {
  const all = entries(); const reached = new Set();
  for (const date of dates) {
    for (const scenario of kinds) {
      for (const sensitivity of ['0', '300', '600']) {
        const shown = filterRecoveryRuns(all, { date, scenario, sensitivity });
        assert.equal(shown.length, sensitivity === '0' ? 4 : scenario === 'stop_unavailable' ? 1 : 0);
        for (const { run, summary } of shown) {
          reached.add(run.run_id);
          assert.equal(summary.serviceDate, date);
          assert.deepEqual(summary.scenarioKinds, [scenario]);
          assert.equal(String(summary.sensitivity), sensitivity);
        }
      }
    }
  }
  assert.equal(reached.size, 54);
  assert.equal(filterRecoveryRuns(all, { date: '2026-10-22', scenario: 'stop_unavailable', sensitivity: '0' }).length, 0);
  assert.equal(filterRecoveryRuns(all, { date: '', scenario: '', sensitivity: '' }).length, 54);
});

test('filtering keeps exact group identities separate and never changes or fetches outcomes', () => {
  const first = entries()[4];
  const differentInput = { run: { run_id: 'different-input' }, summary: { ...first.summary, groupKey: 'different-input-identity' } };
  const shown = filterRecoveryRuns([first, differentInput]);
  assert.equal(shown.length, 2);
  assert.equal(shown[0], first); assert.equal(shown[1], differentInput);
  assert.notEqual(shown[0].summary.groupKey, shown[1].summary.groupKey);
});

test('Brisbane source dates and explicit unknown metadata remain selectable without fallback', () => {
  assert.equal(recoveryRecordingDate('2026-10-18T21:30:05Z'), '2026-10-19');
  assert.equal(recoveryRecordingDate('invalid'), 'unknown');
  assert.equal(recoveryRecordingDate(null), 'unknown');
  const sparse = [{ run: { run_id: 'sparse' }, summary: {} },
    { run: { run_id: 'utc' }, summary: { sourceTime: '2026-10-18T21:30:05Z', scenarioKinds: ['stop_unavailable'], sensitivity: 0 } }];
  assert.deepEqual(recoveryFilterOptions(sparse), { dates: ['2026-10-19', 'unknown'],
    scenarios: ['stop_unavailable', 'unknown'], sensitivities: ['0', 'unknown'] });
  assert.equal(filterRecoveryRuns(sparse, { date: 'unknown', scenario: 'unknown', sensitivity: 'unknown' })[0], sparse[0]);
  assert.equal(filterRecoveryRuns(sparse).length, 1);
});
