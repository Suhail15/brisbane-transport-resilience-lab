"""Draft-only transport and isolated, exact verification of one frozen study cell.

No production calculation, release publication, Actions artifact, or result logging.
The trusted parent holds transport credentials; the frozen child receives none.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid
import zipfile

REPOSITORY = 'Suhail15/brisbane-transport-resilience-lab'
API = 'https://api.github.com'
UPLOAD = 'https://uploads.github.com'
MAX_ZIP = 512 * 1024**2
MAX_EXPANDED = 2 * 1024**3
MAX_FILE = 512 * 1024**2
MAX_FILES = 512
MAX_RESULT = 128 * 1024**2
MAX_REDIRECTS = 5
MATRIX = ((0, 0), (2, 0), (4, 0), (8, 0), (2, 300), (2, 600))
DATES = ('2026-10-22', '2026-10-19', '2026-10-20', '2026-10-21')
SMOKE = '2026-10-09:2:0'
TOKEN_PATTERN = re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)')


class ReviewError(Exception):
    """Only bounded, non-sensitive reason codes may reach Actions logs."""


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def cells(mode):
    if mode == 'smoke':
        return [SMOKE]
    if mode == 'full':
        return [f'{day}:{budget}:{delta}' for day in DATES for budget, delta in MATRIX]
    raise ReviewError('invalid_mode')


def cell_key(value):
    allowed = set(cells('full') + cells('smoke'))
    if value not in allowed:
        raise ReviewError('invalid_cell')
    day, budget, delta = value.split(':')
    return day, int(budget), int(delta)


def valid_url(url, origins):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.username is not None or parsed.password is not None
            or parsed.port not in (None, 443) or parsed.fragment
            or f'https://{parsed.hostname}' not in origins):
        raise ReviewError('untrusted_transport_url')
    return parsed


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitHubTransport:
    def __init__(self, token, repository=REPOSITORY, opener=None):
        if not token or repository != REPOSITORY:
            raise ReviewError('repository_or_token_invalid')
        self.token = token
        self.opener = opener or build_opener(NoRedirect())

    def request(self, url, *, auth_origin=None, accept='application/vnd.github+json', body=None):
        valid_url(url, {auth_origin} if auth_origin else {API, 'https://release-assets.githubusercontent.com', 'https://objects.githubusercontent.com', 'https://github.com'})
        headers = {'Accept': accept, 'User-Agent': 'corridor-frozen-review', 'X-GitHub-Api-Version': '2022-11-28'}
        if auth_origin:
            headers['Authorization'] = 'Bearer ' + self.token
        if body is not None:
            headers['Content-Type'] = 'application/gzip'
        return self.opener.open(Request(url, data=body, headers=headers), timeout=90)

    def json(self, url, *, body=None, auth_origin=API):
        try:
            with self.request(url, auth_origin=auth_origin, body=body) as response:
                raw = response.read(8 * 1024**2 + 1)
            if len(raw) > 8 * 1024**2:
                raise ReviewError('metadata_limit')
            return json.loads(raw)
        except (HTTPError, URLError, ValueError) as exc:
            raise ReviewError('github_metadata_transport_failed') from None

    def draft(self, release_id):
        url = f'{API}/repos/{REPOSITORY}/releases/{release_id}'
        release = self.json(url)
        if (release.get('id') != release_id or release.get('draft') is not True
                or release.get('published_at') is not None or release.get('url') != url):
            raise ReviewError('draft_state_mismatch')
        return release

    def download(self, release_id, asset_id, destination, expected_sha):
        release = self.draft(release_id)
        asset = next((a for a in release.get('assets', ()) if a.get('id') == asset_id), None)
        initial = f'{API}/repos/{REPOSITORY}/releases/assets/{asset_id}'
        if (not asset or asset.get('url') != initial or asset.get('state') != 'uploaded'
                or not isinstance(asset.get('size'), int) or not 0 < asset['size'] <= MAX_ZIP):
            raise ReviewError('draft_input_asset_invalid')
        current = initial
        for hop in range(MAX_REDIRECTS + 1):
            self.draft(release_id)  # Recheck before each download/redirect request.
            try:
                response = self.request(current, auth_origin=API if hop == 0 else None,
                                        accept='application/octet-stream')
            except HTTPError as exc:
                if exc.code not in (301, 302, 303, 307, 308) or hop == MAX_REDIRECTS:
                    raise ReviewError('input_download_failed') from None
                location = exc.headers.get('Location')
                if not location:
                    raise ReviewError('input_redirect_missing') from None
                current = urljoin(current, location)
                valid_url(current, {API, 'https://release-assets.githubusercontent.com', 'https://objects.githubusercontent.com', 'https://github.com'})
                continue  # No Authorization is sent on ANY redirected request.
            except URLError:
                raise ReviewError('input_download_failed') from None
            count, digest = 0, hashlib.sha256()
            with response, Path(destination).open('xb') as output:
                while chunk := response.read(1024**2):
                    count += len(chunk)
                    if count > MAX_ZIP or count > asset['size']:
                        raise ReviewError('input_download_limit')
                    digest.update(chunk)
                    output.write(chunk)
            if count != asset['size'] or digest.hexdigest() != expected_sha:
                raise ReviewError('input_zip_hash_mismatch')
            self.draft(release_id)
            return
        raise ReviewError('input_redirect_limit')

    def upload(self, release_id, name, payload):
        self.draft(release_id)
        if not re.fullmatch(r'case-study-review-[A-Za-z0-9.-]+\.json\.gz', name) or len(payload) > MAX_RESULT:
            raise ReviewError('result_asset_invalid')
        # Never trust a caller-supplied upload_url host or path.
        url = f'{UPLOAD}/repos/{REPOSITORY}/releases/{release_id}/assets?' + urlencode({'name': name})
        result = self.json(url, body=payload, auth_origin=UPLOAD)
        if (result.get('name') != name or result.get('state') != 'uploaded'
                or result.get('size') != len(payload) or not isinstance(result.get('id'), int)):
            raise ReviewError('result_upload_identity_mismatch')
        digest = result.get('digest')
        if digest is not None and digest != 'sha256:' + sha(payload):
            raise ReviewError('result_upload_hash_mismatch')
        self.draft(release_id)


def safe_extract(archive, destination):
    root = Path(destination)
    root.mkdir()
    total, names = 0, set()
    try:
        with zipfile.ZipFile(archive) as source:
            items = source.infolist()
            if not 1 <= len(items) <= MAX_FILES:
                raise ReviewError('zip_member_limit')
            for item in items:
                name = item.filename
                path, windows = PurePosixPath(name), PureWindowsPath(name)
                mode = stat.S_IFMT(item.external_attr >> 16)
                if (item.orig_filename != name or not name or path.is_absolute() or windows.drive or windows.root or '\\' in name
                        or ':' in name or '..' in path.parts or path.as_posix() != name.rstrip('/')
                        or name.rstrip('/') in names or mode not in (0, stat.S_IFREG, stat.S_IFDIR)
                        or item.flag_bits & 1 or item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                    raise ReviewError('unsafe_zip_member')
                names.add(name.rstrip('/'))
                if (any(p in {'raw', 'objects', 'bootstrap', '.git', '.secrets', 'secrets'} for p in path.parts)
                        or any(p.startswith('.env') for p in path.parts)
                        or path.suffix.lower() in {'.zip', '.sqlite', '.sqlite3', '.duckdb', '.parquet', '.pem', '.key', '.p12', '.pfx'}):
                    raise ReviewError('forbidden_archive_material')
                total += item.file_size
                if item.file_size > MAX_FILE or total > MAX_EXPANDED:
                    raise ReviewError('zip_expansion_limit')
                target = root.joinpath(*path.parts)
                if item.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                count, carry = 0, b''
                with source.open(item) as incoming, target.open('xb') as output:
                    while chunk := incoming.read(1024**2):
                        count += len(chunk)
                        if count > item.file_size or count > MAX_FILE:
                            raise ReviewError('zip_member_size_mismatch')
                        scanned = carry + chunk
                        if TOKEN_PATTERN.search(scanned):
                            raise ReviewError('credential_material_in_pack')
                        carry = scanned[-256:]
                        output.write(chunk)
                if count != item.file_size:
                    raise ReviewError('zip_member_size_mismatch')
    except (zipfile.BadZipFile, OSError):
        raise ReviewError('zip_extraction_failed') from None


def verify_pack(root, expected_manifest):
    root = Path(root)
    raw = (root / 'manifest.json').read_bytes()
    if sha(raw) != expected_manifest:
        raise ReviewError('manifest_hash_mismatch')
    manifest = json.loads(raw)
    expected = set(manifest['files'])
    actual = set()
    for p in root.rglob('*'):
        if p.is_symlink():
            raise ReviewError('pack_symlink')
        if p.is_file() and p != root / 'manifest.json':
            actual.add(p.relative_to(root).as_posix())
    if actual != expected:
        raise ReviewError('pack_file_set_mismatch')
    for name, digest in manifest['files'].items():
        path, windows = PurePosixPath(name), PureWindowsPath(name)
        if (path.is_absolute() or windows.drive or windows.root or '\\' in name
                or '..' in path.parts or name != path.as_posix() or ':' in name):
            raise ReviewError('unsafe_manifest_path')
        if sha((root / name).read_bytes()) != digest:
            raise ReviewError('pack_file_hash_mismatch')
    for name in ('code/services/resilience/__init__.py', 'code/services/resilience/pipeline/__init__.py'):
        if name not in expected:
            raise ReviewError('package_initializer_missing')
    if (root / 'code/requirements.lock.txt').read_bytes() != (Path(__file__).resolve().parents[1] / 'requirements.lock.txt').read_bytes():
        raise ReviewError('dependency_lock_mismatch')
    return manifest


def frozen_compute(pack, expected_manifest, key, provenance, output):
    sys.dont_write_bytecode = True
    root = Path(pack).resolve()
    manifest = verify_pack(root, expected_manifest)
    blocked = []

    def guard(event, values):
        if event in ('socket.connect', 'socket.bind', 'socket.getaddrinfo', 'urllib.Request', 'http.client.connect'):
            blocked.append(event)
            raise ReviewError('network_unavailable_during_compute')
        if event == 'open' and values and isinstance(values[0], (str, bytes, os.PathLike)):
            target = Path(os.fsdecode(values[0])).resolve()
            checkout_data = Path(__file__).resolve().parents[1] / 'data'
            if target.is_relative_to(checkout_data):
                blocked.append('original_archive_open')
                raise ReviewError('archive_unavailable_during_compute')

    sys.addaudithook(guard)
    if any(k for k in os.environ if re.search(r'TOKEN|SECRET|PASSWORD|CREDENTIAL', k, re.I)):
        raise ReviewError('credential_environment_in_compute')
    sys.path.insert(0, str(root / 'code/services'))
    from resilience.pipeline import case_study as frozen
    for name, module in tuple(sys.modules.items()):
        if name == 'resilience' or name.startswith('resilience.'):
            location = getattr(module, '__file__', None)
            if location and not Path(location).resolve().is_relative_to(root / 'code/services'):
                raise ReviewError('non_frozen_module')
    if frozen.code_hash() != manifest['code_sha256'] or frozen._FULL_ROUTE_CACHE:
        raise ReviewError('frozen_code_or_initial_cache_mismatch')
    day, budget, delta = cell_key(key)
    if day not in manifest['dates']:
        raise ReviewError('cell_not_in_pack')
    protocol = json.loads((root / 'study/protocol.json').read_bytes())
    if protocol['config']['study_id'] != 'corridor-impact-v2' or protocol['code_sha256'] != manifest['code_sha256']:
        raise ReviewError('study_protocol_mismatch')
    started = time.perf_counter()
    saved = frozen.checked_cell(root / 'study', day, budget, delta)
    actual = frozen.compute_cell(root / 'study', day, budget, delta)
    if (actual.get('date') != day or actual.get('budget_bus_hours') != budget
            or actual.get('additional_bus_seconds') != delta):
        raise ReviewError('recomputed_cell_identity_mismatch')
    if saved['result'] != actual or blocked:
        raise ReviewError('full_result_mismatch')
    frozen.verify_manifest_files(root, manifest['files'])
    report = {'schema_version': 1, 'matched': True, 'date': day, 'budget': budget, 'delta': delta,
        'cell_key': key, 'elapsed_seconds': time.perf_counter() - started,
        'protocol_sha256': sha((root / 'study/protocol.json').read_bytes()),
        'reproduction_manifest_sha256': expected_manifest, 'code_sha256': frozen.code_hash(),
        'stored_cell_sha256': sha(frozen.cell_path(root / 'study', day, budget, delta).read_bytes()),
        'recomputed_result_sha256': frozen.digest(actual), 'provenance': provenance,
        'fresh_process': True, 'initial_route_cache_entries': 0, 'blocked_access_attempt_count': 0,
        'python_version': sys.version.split()[0], 'recomputed_result': actual}
    with Path(output).open('xb') as target:
        target.write(gzip.compress(encoded(report), compresslevel=6, mtime=0))


def run_review(args):
    if os.environ.get('GITHUB_REPOSITORY') != REPOSITORY:
        raise ReviewError('repository_mismatch')
    token = os.environ.get('REVIEW_TOKEN', '')
    transport = GitHubTransport(token)
    for value in (args.zip_sha256, args.manifest_sha256):
        if not re.fullmatch(r'[a-f0-9]{64}', value):
            raise ReviewError('invalid_external_hash')
    cell_key(args.cell)
    run_id, attempt, git_sha = (os.environ.get(k, '') for k in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_SHA'))
    if not run_id.isdigit() or not attempt.isdigit() or not re.fullmatch(r'[a-f0-9]{40}', git_sha):
        raise ReviewError('actions_identity_invalid')
    provenance = {'repository': REPOSITORY, 'release_id': args.release_id, 'input_asset_id': args.asset_id,
        'run_id': run_id, 'run_attempt': attempt, 'git_sha': git_sha,
        'input_zip_sha256': args.zip_sha256, 'original_manifest_sha256': args.manifest_sha256,
        'worker_sha256': sha(Path(__file__).read_bytes()), 'cell_key': args.cell}
    with tempfile.TemporaryDirectory(prefix='case-study-review-', dir=os.environ.get('RUNNER_TEMP')) as temporary:
        base = Path(temporary)
        transport.download(args.release_id, args.asset_id, base / 'input.zip', args.zip_sha256)
        safe_extract(base / 'input.zip', base / 'pack')
        verify_pack(base / 'pack', args.manifest_sha256)  # No frozen imports before this gate.
        (base / 'provenance.json').write_bytes(encoded(provenance))
        result = base / 'result.json.gz'
        # No job/runtime token or checkout credential reaches frozen calculation.
        child_env = {k: os.environ[k] for k in ('PATH', 'LANG', 'LC_ALL', 'SYSTEMROOT', 'TEMP', 'TMP') if k in os.environ}
        child_env['PYTHONDONTWRITEBYTECODE'] = '1'
        command = [sys.executable, '-B', str(Path(__file__).resolve()), 'compute', '--pack', str(base / 'pack'),
            '--manifest-sha256', args.manifest_sha256, '--cell', args.cell,
            '--provenance', str(base / 'provenance.json'), '--output', str(result)]
        with (base / 'private-compute.log').open('wb') as log:
            completed = subprocess.run(command, env=child_env, stdout=log, stderr=subprocess.STDOUT, check=False)
        if completed.returncode != 0 or not result.is_file() or result.stat().st_size > MAX_RESULT:
            raise ReviewError('frozen_compute_failed')
        name = f'case-study-review-{run_id}-{attempt}-{git_sha[:12]}-{args.cell.replace(":", "-")}-{uuid.uuid4().hex[:12]}.json.gz'
        transport.upload(args.release_id, name, result.read_bytes())
    print('Draft-only review completed.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    matrix = commands.add_parser('matrix'); matrix.add_argument('--mode', choices=('smoke', 'full'), required=True)
    review = commands.add_parser('review')
    for name in ('release-id', 'asset-id'):
        review.add_argument('--' + name, type=int, required=True)
    for name in ('zip-sha256', 'manifest-sha256', 'cell'):
        review.add_argument('--' + name, required=True)
    compute = commands.add_parser('compute')
    for name in ('pack', 'manifest-sha256', 'cell', 'provenance', 'output'):
        compute.add_argument('--' + name, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'matrix':
            print(json.dumps(cells(args.mode), separators=(',', ':')))
        elif args.command == 'review':
            run_review(args)
        else:
            frozen_compute(args.pack, args.manifest_sha256, args.cell,
                           json.loads(Path(args.provenance).read_bytes()), args.output)
    except ReviewError as exc:
        print('Review failed: ' + str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    except Exception:
        print('Review failed: bounded_verification_failure', file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
