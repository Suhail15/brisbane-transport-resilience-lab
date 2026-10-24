import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, readFile, rm, symlink, writeFile, unlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve, dirname } from 'node:path';
import { buildStatic, checkedRelativePath, stageCompactBundle, verifyCompactBundle } from '../../frontend/scripts/build-static.mjs';
import { defaultSnapshotIndex } from '../../frontend/src/domain.js';

const sha = (bytes) => createHash('sha256').update(bytes).digest('hex');
async function fixture(t, { publicBundle = false } = {}) {
  const root = await mkdtemp(resolve(tmpdir(), 'resilience-static-test-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const source = resolve(root, 'source');
  const catalog = { compact: true, candidate_preparation_only: !publicBundle,
    publication_authorized: publicBundle, preferred_snapshot_id: 'decision',
    snapshots: [{ snapshot_id: 'decision', url: 'snapshots/decision.json',
      display_url: 'snapshots/decision.display.json', choices_url: 'snapshots/decision.choices.json',
      network_url: 'networks/one.geojson' }], source_summary: { replay_label: '15-minute recorded samples; no interpolation' } };
  const documents = {
    'catalog.json': catalog,
    'experiments/index.json': { version: 1, runs: [{ run_id: 'run', url: 'experiments/run.json' }] },
    'experiments/run.json': { run_id: 'run', input_url: 'run-inputs/run.input.json', metadata_url: 'run-inputs/run.metadata.json' },
    'run-inputs/run.input.json': { requests: [{ request_id: 'one' }], candidates: [] },
    'run-inputs/run.metadata.json': { input_sha256: 'a'.repeat(64) },
    'snapshots/decision.json': { metadata: { snapshot_id: 'decision' }, compact_display_only: true },
    'snapshots/decision.display.json': { vehicles: [] },
    'snapshots/decision.choices.json': { stops: [] },
    'networks/one.geojson': { type: 'FeatureCollection', features: [] },
  };
  const files = {};
  for (const [path, document] of Object.entries(documents)) {
    const bytes = JSON.stringify(document);
    await mkdir(dirname(resolve(source, path)), { recursive: true });
    await writeFile(resolve(source, path), bytes); files[path] = sha(bytes);
  }
  const manifest = { version: 1, compact: true, public: publicBundle,
    candidate_preparation_only: !publicBundle, files };
  await writeFile(resolve(source, 'manifest.json'), JSON.stringify(manifest, null, 2));
  return { root, source, catalog, manifest, documents };
}

async function update(fixture, path, document) {
  const bytes = JSON.stringify(document);
  await writeFile(resolve(fixture.source, path), bytes);
  fixture.manifest.files[path] = sha(bytes);
  await writeFile(resolve(fixture.source, 'manifest.json'), JSON.stringify(fixture.manifest, null, 2));
}

for (const publicBundle of [false, true]) {
  test(`staging preserves every compact byte, lazy references and ${publicBundle ? 'public' : 'candidate'} flags`, async (t) => {
    const f = await fixture(t, { publicBundle });
    const stage = resolve(f.root, 'stage');
    await stageCompactBundle(f.source, stage);
    for (const path of [...Object.keys(f.manifest.files), 'manifest.json']) {
      assert.deepEqual(await readFile(resolve(stage, path)), await readFile(resolve(f.source, path)));
    }
    const catalog = JSON.parse(await readFile(resolve(stage, 'catalog.json')));
    assert.equal(catalog.publication_authorized, publicBundle);
    assert.equal(catalog.candidate_preparation_only, !publicBundle);
    assert.equal(JSON.parse(await readFile(resolve(stage, 'manifest.json'))).public, publicBundle);
    assert.equal(catalog.preferred_snapshot_id, 'decision');
  });
}

test('corrupt, missing and extra regular files reject before staging', async (t) => {
  for (const kind of ['corrupt', 'missing', 'extra']) {
    const f = await fixture(t);
    if (kind === 'corrupt') await writeFile(resolve(f.source, 'catalog.json'), '{}');
    if (kind === 'missing') await unlink(resolve(f.source, 'run-inputs/run.input.json'));
    if (kind === 'extra') await writeFile(resolve(f.source, 'unlisted.json'), '{}');
    await assert.rejects(stageCompactBundle(f.source, resolve(f.root, 'stage')), kind === 'corrupt' ? /SHA256 mismatch/ : /file set differs/);
    await assert.rejects(readFile(resolve(f.root, 'stage/catalog.json')), /ENOENT/);
  }
});

test('unsafe paths and malformed hashes are rejected', async (t) => {
  for (const path of ['../outside.json', '/absolute.json', 'C:/outside.json', 'a\\b.json', './catalog.json', 'a//b', 'a/%2e%2e/b', 'https://example.invalid/a', 'a/..']) {
    assert.throws(() => checkedRelativePath(path), /Unsafe path/);
    const f = await fixture(t);
    f.manifest.files[path] = 'a'.repeat(64);
    await writeFile(resolve(f.source, 'manifest.json'), JSON.stringify(f.manifest));
    await assert.rejects(verifyCompactBundle(f.source), /Unsafe path/);
  }
  const f = await fixture(t);
  f.manifest.files['catalog.json'] = 'wrong';
  await writeFile(resolve(f.source, 'manifest.json'), JSON.stringify(f.manifest));
  await assert.rejects(verifyCompactBundle(f.source), /Invalid SHA256/);
});

test('symlink files and symlink directories reject even when contents hash correctly', async (t) => {
  const file = await fixture(t);
  await writeFile(resolve(file.root, 'outside.json'), await readFile(resolve(file.source, 'catalog.json')));
  await unlink(resolve(file.source, 'catalog.json'));
  await symlink(resolve(file.root, 'outside.json'), resolve(file.source, 'catalog.json'));
  await assert.rejects(verifyCompactBundle(file.source), /Symlink/);
  const directory = await fixture(t);
  await symlink(resolve(directory.source, 'run-inputs'), resolve(directory.source, 'linked'));
  await assert.rejects(verifyCompactBundle(directory.source), /Symlink/);
});

test('compact flag cannot hide full engine timetables or noncompact snapshot headers', async (t) => {
  const f = await fixture(t);
  await update(f, 'snapshots/decision.json', { metadata: {}, connections: [], walking_links: [] });
  await assert.rejects(verifyCompactBundle(f.source), /Noncompact full timetable/);
  await update(f, 'snapshots/decision.json', { metadata: {} });
  await assert.rejects(verifyCompactBundle(f.source), /compact display header/);
  await update(f, 'snapshots/decision.json', { metadata: {}, compact_display_only: true });
  f.manifest.compact = false;
  await writeFile(resolve(f.source, 'manifest.json'), JSON.stringify(f.manifest));
  await assert.rejects(verifyCompactBundle(f.source), /compact data bundle/);
});

test('lazy references must resolve to safely manifested local files', async (t) => {
  const f = await fixture(t);
  await update(f, 'experiments/run.json', { input_url: '../private.json' });
  await assert.rejects(verifyCompactBundle(f.source), /Unsafe path/);
  await update(f, 'experiments/run.json', { metadata_url: 'run-inputs/missing.json' });
  await assert.rejects(verifyCompactBundle(f.source), /Unmanifested bundle reference/);
  const study = await fixture(t);
  await update(study, 'catalog.json', { ...study.catalog, case_study_url: 'case-study.json' });
  await assert.rejects(verifyCompactBundle(study.source), /Unmanifested bundle reference/);
  await update(study, 'case-study.json', { schema_version: 1, study_id: 'fixture-only', dates: [] });
  assert.equal((await verifyCompactBundle(study.source)).catalog.case_study_url, 'case-study.json');
});

test('separately licensed walking database is distributable without admitting a full timetable', async (t) => {
  const f = await fixture(t);
  await mkdir(resolve(f.source, 'walking'));
  const walking = { licence: 'ODbL 1.0', licence_url: 'https://opendatacommons.org/licenses/odbl/1-0/', walking_links: [] };
  await update(f, 'walking/derived.json', walking);
  await verifyCompactBundle(f.source);
  await update(f, 'walking/derived.json', { ...walking, connections: [] });
  await assert.rejects(verifyCompactBundle(f.source), /Noncompact full timetable/);
  await update(f, 'walking/derived.json', { ...walking, licence: 'unknown' });
  await assert.rejects(verifyCompactBundle(f.source), /Noncompact full timetable/);
});

test('App honors only matching preferred snapshot and keeps the existing default fallback', async () => {
  const app = await readFile(new URL('../../frontend/src/App.jsx', import.meta.url), 'utf8');
  // Evaluate the exact small selection expression used by the component without a DOM runtime.
  const selection = app.match(/const preferredIndex = ([^;]+);\s*const initialIndex = ([^;]+);/);
  assert.ok(selection);
  const select = new Function('ordered', 'nextCatalog', 'defaultSnapshotIndex', `const preferredIndex = ${selection[1]}; return ${selection[2]};`);
  const ordered = [{ snapshot_id: 'first', snapshot_at: '2026-10-19T06:00:05+10:00' },
    { snapshot_id: 'decision', snapshot_at: '2026-10-19T07:30:05+10:00' }];
  assert.equal(select(ordered, { preferred_snapshot_id: 'decision' }, defaultSnapshotIndex), 1);
  for (const nextCatalog of [{}, { preferred_snapshot_id: 'absent' }]) {
    assert.equal(select(ordered, nextCatalog, defaultSnapshotIndex), defaultSnapshotIndex(ordered));
  }
  assert.equal(select([], {}, defaultSnapshotIndex), defaultSnapshotIndex([]));
  assert.match(app, /catalog\.source_summary\.replay_label/);
});


test('Vite builds a synthetic compact source selected through the environment without changing its data manifest', async (t) => {
  const f = await fixture(t);
  const previous = Object.fromEntries(['RESILIENCE_BUNDLE_SOURCE', 'VITE_DATA_MODE', 'VITE_BUNDLE_URL', 'VITE_BASE_PATH', 'VITE_BUNDLE_DIR'].map((key) => [key, process.env[key]]));
  t.after(() => {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key]; else process.env[key] = value;
    }
  });
  process.env.RESILIENCE_BUNDLE_SOURCE = f.source;
  const outDir = resolve(f.root, 'dist');
  await buildStatic({ outDir });
  assert.match(await readFile(resolve(outDir, 'index.html'), 'utf8'), /<script/);
  for (const path of [...Object.keys(f.manifest.files), 'manifest.json']) {
    assert.deepEqual(await readFile(resolve(outDir, path)), await readFile(resolve(f.source, path)));
  }
  const manifest = JSON.parse(await readFile(resolve(outDir, 'manifest.json')));
  assert.equal(Object.hasOwn(manifest.files, 'index.html'), false);
});
