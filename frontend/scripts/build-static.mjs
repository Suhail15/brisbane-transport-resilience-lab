import { createHash } from 'node:crypto';
import { lstat, mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { gunzipSync } from 'node:zlib';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const frontendDirectory = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repositoryDirectory = resolve(frontendDirectory, '..');
const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');

export function checkedRelativePath(path) {
  if (typeof path !== 'string' || !path || path.includes('\\')
      || path.split('/').some((part) => !/^[A-Za-z0-9_-][A-Za-z0-9_.-]*$/.test(part))) {
    throw new Error(`Unsafe path in prepared bundle: ${path}`);
  }
  return path;
}

async function regularFiles(directory, prefix = '') {
  if (!(await lstat(directory)).isDirectory()) throw new Error(`Bundle directory is not a regular directory: ${directory}`);
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const relative = checkedRelativePath(prefix ? `${prefix}/${entry.name}` : entry.name);
    const fullPath = resolve(directory, entry.name);
    const stat = await lstat(fullPath);
    if (stat.isSymbolicLink()) throw new Error(`Symlink in prepared bundle: ${relative}`);
    if (stat.isDirectory()) files.push(...await regularFiles(fullPath, relative));
    else if (stat.isFile()) files.push(relative);
    else throw new Error(`Nonregular file in prepared bundle: ${relative}`);
  }
  return files.sort();
}

export async function verifyCompactBundle(sourceDirectory) {
  const actual = await regularFiles(sourceDirectory);
  const manifestBytes = await readFile(resolve(sourceDirectory, 'manifest.json'));
  const manifest = JSON.parse(manifestBytes);
  if (manifest.version !== 1 || manifest.compact !== true || !manifest.files
      || typeof manifest.files !== 'object' || Array.isArray(manifest.files)) {
    throw new Error('Expected version 1 compact data bundle manifest');
  }
  const expected = Object.keys(manifest.files).sort();
  for (const path of expected) {
    checkedRelativePath(path);
    if (path === 'manifest.json' || path === 'index.html' || path.startsWith('assets/')) {
      throw new Error(`Reserved file in compact data manifest: ${path}`);
    }
    if (!/^[a-f0-9]{64}$/.test(manifest.files[path])) throw new Error(`Invalid SHA256 identity: ${path}`);
  }
  if (JSON.stringify(actual) !== JSON.stringify([...expected, 'manifest.json'].sort())) {
    throw new Error('Bundle regular-file set differs from manifest (missing or extra files)');
  }
  for (const required of ['catalog.json', 'experiments/index.json']) {
    if (!Object.hasOwn(manifest.files, required)) throw new Error(`Missing required bundle file: ${required}`);
  }
  let catalog;
  const compactHeaders = new Set();
  const checkReference = (path) => {
    checkedRelativePath(path);
    if (!Object.hasOwn(manifest.files, path)) throw new Error(`Unmanifested bundle reference: ${path}`);
  };
  const checkFields = (document, keys) => {
    for (const key of keys) if (document[key] != null) checkReference(document[key]);
  };
  const snapshotFields = ['url', 'network_url', 'display_url', 'choices_url'];
  const runFields = ['url', 'result_url', 'input_url', 'metadata_url'];
  for (const path of expected) {
    const bytes = await readFile(resolve(sourceDirectory, path));
    if (sha256(bytes) !== manifest.files[path]) throw new Error(`SHA256 mismatch: ${path}`);
    if (/\.json(?:\.gz)?$/.test(path)) {
      const document = JSON.parse(path.endsWith('.gz') ? gunzipSync(bytes) : bytes);
      const separateWalkingDatabase = path.startsWith('walking/')
        && document?.licence === 'ODbL 1.0'
        && document?.licence_url === 'https://opendatacommons.org/licenses/odbl/1-0/'
        && Array.isArray(document.walking_links)
        && !Object.hasOwn(document, 'connections') && !Object.hasOwn(document, 'recovery_pairs');
      if (document && typeof document === 'object' && !Array.isArray(document)
          && ['connections', 'walking_links', 'recovery_pairs'].some((key) => Object.hasOwn(document, key))
          && !separateWalkingDatabase) {
        throw new Error(`Noncompact full timetable snapshot: ${path}`);
      }
      if (path === 'catalog.json') {
        catalog = document;
        checkFields(document, ['network_url', 'case_study_url']);
        for (const snapshot of document.snapshots ?? []) checkFields(snapshot, snapshotFields);
      } else if (path === 'snapshots/index.json') {
        for (const snapshot of document.snapshots ?? []) checkFields(snapshot, snapshotFields);
      } else if (path === 'experiments/index.json') {
        for (const run of document.runs ?? []) checkFields(run, runFields);
      } else if (path.startsWith('experiments/')) checkFields(document, runFields);
      else if (path.startsWith('snapshots/')) {
        checkFields(document, ['display_url', 'choices_url']);
        if (document.compact_display_only === true) compactHeaders.add(path);
      }
      // Large run/input/display documents are released here, rather than retained for the whole bundle.
    }
  }
  if (catalog.compact !== true) throw new Error('Catalog is not compact');
  for (const snapshot of catalog.snapshots ?? []) {
    if (snapshot.url && !compactHeaders.has(snapshot.url)) {
      throw new Error(`Snapshot is not a compact display header: ${snapshot.url}`);
    }
  }
  return { manifest, manifestBytes, files: expected, catalog };
}

export async function stageCompactBundle(sourceDirectory, stagedBundle) {
  const verified = await verifyCompactBundle(sourceDirectory);
  await mkdir(stagedBundle, { recursive: true });
  for (const path of verified.files) {
    const bytes = await readFile(resolve(sourceDirectory, path));
    if (sha256(bytes) !== verified.manifest.files[path]) throw new Error(`Bundle changed during staging: ${path}`);
    const destination = resolve(stagedBundle, path);
    await mkdir(dirname(destination), { recursive: true });
    await writeFile(destination, bytes, { flag: 'wx' });
  }
  await writeFile(resolve(stagedBundle, 'manifest.json'), verified.manifestBytes, { flag: 'wx' });
  return verified;
}

export async function buildStatic({ outDir } = {}) {
  const sourceDirectory = resolve(process.env.RESILIENCE_BUNDLE_SOURCE || resolve(repositoryDirectory, 'data/derived/demo'));
  const stagedBundle = await mkdtemp(resolve(tmpdir(), 'brisbane-resilience-static-'));
  try {
    await stageCompactBundle(sourceDirectory, stagedBundle);
    process.env.VITE_DATA_MODE = 'static';
    process.env.VITE_BUNDLE_URL ||= './';
    process.env.VITE_BASE_PATH ||= '/brisbane-transport-resilience-lab/';
    process.env.VITE_BUNDLE_DIR = stagedBundle;
    const { build } = await import('vite');
    await build({ root: frontendDirectory, configFile: resolve(frontendDirectory, 'vite.config.js'),
      ...(outDir ? { build: { outDir } } : {}) });
  } finally {
    await rm(stagedBundle, { recursive: true, force: true });
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await buildStatic();
}
