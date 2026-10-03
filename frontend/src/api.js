export class AdapterError extends Error {
  constructor(message, { status = null, path = '', mode = 'local', cause } = {}) {
    super(message, { cause });
    this.name = 'AdapterError';
    this.status = status;
    this.path = path;
    this.mode = mode;
  }
}

async function decodeJsonResponse(response, url, mode) {
  let bytes;
  try {
    bytes = new Uint8Array(await response.arrayBuffer());
  } catch (cause) {
    throw new AdapterError('The response could not be read.', { status: response.status, path: url, mode, cause });
  }

  if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
    if (typeof globalThis.DecompressionStream !== 'function'
      || typeof globalThis.Blob !== 'function'
      || typeof globalThis.Response !== 'function') {
      throw new AdapterError(
        'This browser cannot open the compressed map geometry. Update the browser and reload the static bundle.',
        { status: response.status, path: url, mode },
      );
    }
    try {
      const stream = new Blob([bytes]).stream().pipeThrough(new globalThis.DecompressionStream('gzip'));
      bytes = new Uint8Array(await new Response(stream).arrayBuffer());
    } catch (cause) {
      throw new AdapterError('The compressed source file could not be opened. Try refreshing the replay bundle.', {
        status: response.status,
        path: url,
        mode,
        cause,
      });
    }
  }

  try {
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch (cause) {
    throw new AdapterError('The response was not valid JSON.', {
      status: response.status,
      path: url,
      mode,
      cause,
    });
  }
}

async function readJson(fetcher, url, options, mode) {
  let response;
  try {
    response = await fetcher(url, options);
  } catch (cause) {
    throw new AdapterError(
      mode === 'local'
        ? 'The local replay service could not be reached.'
        : 'The prepared replay bundle could not be reached.',
      { path: url, mode, cause },
    );
  }

  if (!response.ok) {
    let detail = '';
    try {
      const body = await response.json();
      detail = body?.detail || body?.error || '';
    } catch {
      // Keep the response status useful when an endpoint returns no JSON body.
    }
    const message = detail || (response.status === 404
      ? 'That recording or comparison is no longer available.'
      : `The request failed (${response.status}).`);
    throw new AdapterError(message, { status: response.status, path: url, mode });
  }

  return decodeJsonResponse(response, url, mode);
}

function withTrailingSlash(value) {
  return value.endsWith('/') ? value : `${value}/`;
}

export function createLocalAdapter({
  baseUrl = 'http://127.0.0.1:8000/v1',
  fetcher = globalThis.fetch,
} = {}) {
  const base = baseUrl.replace(/\/$/, '');
  const get = (path) => readJson(fetcher, `${base}${path}`, undefined, 'local');
  const post = (path, body) => readJson(fetcher, `${base}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  }, 'local');

  return {
    mode: 'local',
    getCatalog: () => get('/catalog'),
    getSnapshots: async () => (await get('/snapshots')).snapshots ?? [],
    getNetwork: (snapshotId) => get(`/network?snapshot_id=${encodeURIComponent(snapshotId)}`),
    getDisplay: (snapshotId) => get(`/snapshots/${encodeURIComponent(snapshotId)}/display`),
    getChoices: (snapshotId) => get(`/snapshots/${encodeURIComponent(snapshotId)}/choices`),
    getRuns: async () => (await get('/experiments')).runs ?? [],
    getRun: (runId) => get(`/experiments/${encodeURIComponent(runId)}`),
    createRun: (payload) => post('/experiments', payload),
    cancelRun: (runId) => post(`/experiments/${encodeURIComponent(runId)}/cancel`, {}),
  };
}

export function createStaticAdapter({
  bundleUrl = './',
  fetcher = globalThis.fetch,
  pageUrl = globalThis.location?.href || 'http://localhost/',
} = {}) {
  const base = new URL(withTrailingSlash(bundleUrl), pageUrl);
  let catalogPromise;
  let experimentIndexPromise;

  const fetchFile = (relativePath) => {
    const fileUrl = new URL(relativePath, base).toString();
    return readJson(fetcher, fileUrl, undefined, 'static');
  };
  const catalog = () => {
    catalogPromise ||= fetchFile('catalog.json');
    return catalogPromise;
  };
  const findSnapshot = async (snapshotId) => {
    const value = await catalog();
    const item = (value.snapshots ?? []).find((snapshot) => snapshot.snapshot_id === snapshotId);
    if (!item) throw new AdapterError('That recording is not in this bundle.', { mode: 'static' });
    return item;
  };
  const experimentIndex = () => {
    experimentIndexPromise ||= fetchFile('experiments/index.json');
    return experimentIndexPromise;
  };

  return {
    mode: 'static',
    getCatalog: catalog,
    getSnapshots: async () => (await catalog()).snapshots ?? [],
    getNetwork: async (snapshotId) => {
      const snapshot = await findSnapshot(snapshotId);
      if (!snapshot.network_url) {
        throw new AdapterError('No network drawing is included for this recording.', { mode: 'static' });
      }
      return fetchFile(snapshot.network_url);
    },
    getDisplay: async (snapshotId) => {
      const snapshot = await findSnapshot(snapshotId);
      if (!snapshot.display_url) {
        throw new AdapterError('No recorded vehicle frame is included for this recording.', { mode: 'static' });
      }
      return fetchFile(snapshot.display_url);
    },
    getChoices: async (snapshotId) => {
      const snapshot = await findSnapshot(snapshotId);
      if (!snapshot.choices_url) {
        throw new AdapterError('No route choices are included for this recording.', { mode: 'static' });
      }
      return fetchFile(snapshot.choices_url);
    },
    getRuns: async () => (await experimentIndex()).runs ?? [],
    getRun: async (runId) => {
      const index = await experimentIndex();
      const entry = (index.runs ?? []).find((run) => (run.run_id ?? run.id) === runId);
      const path = entry?.url ?? entry?.result_url;
      if (!path) throw new AdapterError('That completed comparison is not in this bundle.', { mode: 'static' });
      return fetchFile(path);
    },
    createRun: async () => {
      throw new AdapterError('New comparisons need the local replay service. This bundle contains recorded results only.', {
        mode: 'static',
      });
    },
    cancelRun: async () => {
      throw new AdapterError('A recorded comparison cannot be cancelled.', { mode: 'static' });
    },
  };
}

export function createAdapter(mode, options = {}) {
  return mode === 'static'
    ? createStaticAdapter(options)
    : createLocalAdapter(options);
}
