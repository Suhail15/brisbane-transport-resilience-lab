import test from 'node:test';
import assert from 'node:assert/strict';
import { collectionGapsBeforeSnapshot } from '../../frontend/src/domain.js';

const snapshot = { service_date: '2026-10-19', snapshot_at: '2026-10-18T21:30:05Z' };
const gap = (started_at, ended_at, detected_at = '2026-10-18T21:00:00Z') => ({
  started_at, ended_at, detected_at, feed: 'TripUpdates', reason: 'collection interruption',
});

test('excludes historical archive gaps and detections after the recorded cutoff', () => {
  const rows = [gap('2026-10-04T20:00:00Z', '2026-10-04T21:00:00Z'),
    gap('2026-10-18T20:00:00Z', '2026-10-18T20:02:00Z', '2026-10-18T21:30:06Z'),
    gap('2026-10-18T21:30:06Z', null)];
  assert.deepEqual(collectionGapsBeforeSnapshot(rows, snapshot), []);
});

test('half-open morning boundary excludes end at06:00 but includes a cross-start interval', () => {
  const endedAtStart = gap('2026-10-18T19:59:00Z', '2026-10-18T20:00:00Z');
  const crossing = gap('2026-10-18T19:59:00Z', '2026-10-18T20:00:01Z');
  const atCutoff = gap('2026-10-18T21:30:05Z', null, snapshot.snapshot_at);
  assert.deepEqual(collectionGapsBeforeSnapshot([endedAtStart, crossing, atCutoff], snapshot), [
    { gap: crossing, status: 'overlap' }, { gap: atCutoff, status: 'overlap' },
  ]);
});

test('open gaps and intervals extending beyond cutoff are retained without altering source fields', () => {
  const rows = [gap('2026-10-18T20:15:00Z', null), gap('2026-10-18T21:00:00Z', '2026-10-18T22:00:00Z')];
  const original = structuredClone(rows);
  const selected = collectionGapsBeforeSnapshot(rows, snapshot);
  assert.equal(selected.length, 2);
  assert.equal(selected[0].gap, rows[0]);
  assert.deepEqual(rows, original);
});

test('malformed and unknown intervals remain visible as unknown, never asserted as valid coverage gaps', () => {
  const rows = [{ feed: 'Alerts', reason: 'unknown history' },
    gap('bad-start', null), gap('2026-10-18T20:20:00Z', 'bad-end'),
    gap('2026-10-18T20:20:00Z', '2026-10-18T20:10:00Z'),
    gap('2026-10-19T06:00:00', null), gap('2026-10-18T20:20:00Z', null, 'bad-detection')];
  const selected = collectionGapsBeforeSnapshot(rows, snapshot);
  assert.equal(selected.length, rows.length);
  assert.ok(selected.every(({ status }) => status === 'unknown'));
  assert.equal(collectionGapsBeforeSnapshot([gap('bad-start',null,'2026-10-18T21:31:00Z')], snapshot).length, 0);
});

test('missing detection remains eligible when interval is known; unknown snapshot timing never invents a scope', () => {
  const row = gap('2026-10-19T06:10:00+10:00', '2026-10-19T06:11:00+10:00', null);
  assert.equal(collectionGapsBeforeSnapshot([row], snapshot)[0].status, 'overlap');
  assert.equal(collectionGapsBeforeSnapshot([row], { service_date: '2026-10-19' })[0].status, 'unknown');
  assert.deepEqual(collectionGapsBeforeSnapshot([], snapshot), []);
});
