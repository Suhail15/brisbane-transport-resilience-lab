import { createHash } from 'node:crypto';
import { copyFile, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'vite';

const frontendDirectory = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repositoryDirectory = resolve(frontendDirectory, '..');
const sourceDirectory = resolve(repositoryDirectory, 'data/derived/demo');
const stagedBundle = await mkdtemp(resolve(tmpdir(), 'brisbane-resilience-static-'));

function checkedRelativePath(path) {
  const normalized = String(path ?? '').replaceAll('\\', '/');
  if (!normalized || normalized.startsWith('/') || normalized.split('/').some((part) => part === '..')) {
    throw new Error(`Unsafe path in prepared bundle: ${path}`);
  }
  return normalized;
}

async function copyBundleFile(relativePath) {
  const relative = checkedRelativePath(relativePath);
  const sourcePath = resolve(sourceDirectory, relative);
  const destinationPath = resolve(stagedBundle, relative);
  if (!destinationPath.startsWith(`${stagedBundle}${sep}`)) throw new Error(`Unsafe destination in prepared bundle: ${relative}`);
  await mkdir(dirname(destinationPath), { recursive: true });
  await copyFile(sourcePath, destinationPath);
}

try {
  const originalCatalog = JSON.parse(await readFile(resolve(sourceDirectory, 'catalog.json'), 'utf8'));
  const sourceRuns = JSON.parse(await readFile(resolve(sourceDirectory, 'experiments/index.json'), 'utf8'));
  const bundleFiles = new Set();
  const snapshots = (originalCatalog.snapshots ?? []).map((snapshot) => {
    const { url: fullSnapshotUrl, ...compactSnapshot } = snapshot;
    void fullSnapshotUrl;
    for (const key of ['network_url', 'display_url', 'choices_url']) {
      if (compactSnapshot[key]) bundleFiles.add(compactSnapshot[key]);
    }
    return compactSnapshot;
  });

  for (const run of sourceRuns.runs ?? []) {
    if (run.status !== 'completed') continue;
    const path = run.url ?? run.result_url;
    if (path) bundleFiles.add(path);
  }

  await Promise.all([...bundleFiles].map(copyBundleFile));
  await mkdir(resolve(stagedBundle, 'experiments'), { recursive: true });
  await writeFile(resolve(stagedBundle, 'catalog.json'), JSON.stringify({ ...originalCatalog, snapshots }));
  const completedRuns = (sourceRuns.runs ?? []).filter((run) => run.status === 'completed');
  await writeFile(resolve(stagedBundle, 'experiments/index.json'), JSON.stringify({ runs: completedRuns }));

  const files = {};
  async function collectFiles(directory, prefix = '') {
    const { readdir, readFile: readFileAtPath } = await import('node:fs/promises');
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
      const fullPath = resolve(directory, entry.name);
      if (entry.isDirectory()) await collectFiles(fullPath, relative);
      else if (entry.isFile() && entry.name !== 'manifest.json') {
        files[relative] = createHash('sha256').update(await readFileAtPath(fullPath)).digest('hex');
      }
    }
  }
  await collectFiles(stagedBundle);
  await writeFile(resolve(stagedBundle, 'manifest.json'), JSON.stringify({ version: 1, public: false, compact: true, files }, null, 2));

  process.env.VITE_DATA_MODE = 'static';
  process.env.VITE_BUNDLE_URL ||= './';
  process.env.VITE_BASE_PATH ||= '/brisbane-transport-resilience-lab/';
  process.env.VITE_BUNDLE_DIR = stagedBundle;
  await build();
} finally {
  await rm(stagedBundle, { recursive: true, force: true });
}
