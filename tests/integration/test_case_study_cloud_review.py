"""Transport and extraction gates use synthetic bytes and never contact GitHub."""
import importlib.util
import io
import json
from pathlib import Path
import stat
from urllib.error import HTTPError
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('cloud_review', ROOT / 'scripts/review_case_study_pack.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


class Response(io.BytesIO):
    pass


class Opener:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        return Response(reply)


def draft(asset_size=4, draft=True):
    return json.dumps({'id': 17, 'draft': draft, 'published_at': None,
        'url': review.API + '/repos/' + review.REPOSITORY + '/releases/17',
        'assets': [{'id': 23, 'state': 'uploaded', 'size': asset_size,
                    'url': review.API + '/repos/' + review.REPOSITORY + '/releases/assets/23'}]}).encode()


def test_redirect_strips_authorization_even_back_to_api(tmp_path):
    initial = review.API + '/repos/' + review.REPOSITORY + '/releases/assets/23'
    redirect = HTTPError(initial, 302, 'hidden', {'Location': initial + '?redirected=1'}, None)
    opener = Opener([draft(), draft(), redirect, draft(), b'data', draft()])
    transport = review.GitHubTransport('synthetic-token', opener=opener)
    transport.download(17, 23, tmp_path / 'input.zip', review.sha(b'data'))
    downloads = [r for r in opener.requests if '/releases/assets/' in r.full_url]
    assert downloads[0].get_header('Authorization') == 'Bearer synthetic-token'
    assert downloads[1].get_header('Authorization') is None
    assert (tmp_path / 'input.zip').read_bytes() == b'data'


def test_non_draft_blocks_download_before_asset_request(tmp_path):
    opener = Opener([draft(draft=False)])
    with pytest.raises(review.ReviewError, match='draft_state_mismatch'):
        review.GitHubTransport('synthetic-token', opener=opener).download(17, 23, tmp_path / 'input.zip', 'a' * 64)
    assert len(opener.requests) == 1
    assert not (tmp_path / 'input.zip').exists()


def test_upload_uses_canonical_origin_and_path():
    body = b'compressed-synthetic-result'
    name = 'case-study-review-123.json.gz'
    response = json.dumps({'id': 24, 'name': name, 'state': 'uploaded', 'size': len(body), 'digest': 'sha256:' + review.sha(body)}).encode()
    opener = Opener([draft(), response, draft()])
    review.GitHubTransport('synthetic-token', opener=opener).upload(17, name, body)
    request = opener.requests[1]
    assert request.full_url == review.UPLOAD + '/repos/' + review.REPOSITORY + '/releases/17/assets?name=' + name
    assert request.get_header('Authorization') == 'Bearer synthetic-token'
    assert request.data == body


@pytest.mark.parametrize('url', ['http://api.github.com/a', 'https://evil.example/a',
    'https://user:password@api.github.com/a', 'https://api.github.com:444/a'])
def test_untrusted_transport_rejected(url):
    with pytest.raises(review.ReviewError, match='untrusted_transport_url'):
        review.valid_url(url, {review.API})


@pytest.mark.parametrize('name,mode,content,reason', [
    ('../escape', 0, b'x', 'unsafe_zip_member'),
    ('/absolute', 0, b'x', 'unsafe_zip_member'),
    ('C:/escape', 0, b'x', 'unsafe_zip_member'),
    ('safe\\escape', 0, b'x', 'unsafe_zip_member'),
    ('safe\x00hidden', 0, b'x', 'unsafe_zip_member'),
    ('link', stat.S_IFLNK, b'/outside', 'unsafe_zip_member'),
    ('raw/feed.json', 0, b'x', 'forbidden_archive_material'),
    ('nested/archive.zip', 0, b'x', 'forbidden_archive_material'),
    ('safe.json', 0, b'ghp_' + b'a' * 30, 'credential_material_in_pack'),
])
def test_unsafe_zip_rejected(tmp_path, name, mode, content, reason):
    archive = tmp_path / 'input.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        item = zipfile.ZipInfo(name.replace('\x00', 'X'))
        item.external_attr = mode << 16
        output.writestr(item, content)
    if '\x00' in name:
        archive.write_bytes(archive.read_bytes().replace(name.replace('\x00', 'X').encode(), name.encode()))
    with pytest.raises(review.ReviewError, match=reason):
        review.safe_extract(archive, tmp_path / 'pack')
    assert not (tmp_path / 'escape').exists()


def test_zip_expansion_bound(tmp_path, monkeypatch):
    monkeypatch.setattr(review, 'MAX_EXPANDED', 2)
    archive = tmp_path / 'input.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('safe.json', b'123')
    with pytest.raises(review.ReviewError, match='zip_expansion_limit'):
        review.safe_extract(archive, tmp_path / 'pack')


def test_matrix_has_exact_registered_cells_and_separate_smoke():
    full = review.cells('full')
    assert len(full) == len(set(full)) == 24
    assert review.cells('smoke') == ['2026-10-09:2:0']
    assert not set(full) & set(review.cells('smoke'))


def test_reviewed_fixture_manifest_and_tamper_gate(tmp_path):
    source = ROOT / 'data/processed/corridor-impact-v2/verification/fixture-pack-initializers'
    if not source.exists():
        pytest.skip('Local immutable fixture pack is intentionally ignored')
    manifest_sha = review.sha((source / 'manifest.json').read_bytes())
    assert review.verify_pack(source, manifest_sha)['code_sha256'].startswith('924e7e')
    with pytest.raises(review.ReviewError, match='manifest_hash_mismatch'):
        review.verify_pack(source, '0' * 64)


def synthetic_pack(tmp_path, mode='match'):
    """Tiny synthetic trusted module tests the harness, never numerical parity."""
    root = tmp_path / 'synthetic-pack'
    code = root / 'code/services/resilience/pipeline'
    code.mkdir(parents=True)
    (code / '__init__.py').write_text('"""Synthetic fixture package."""\n')
    (code.parent / '__init__.py').write_text('"""Synthetic fixture package."""\n')
    module = '''import hashlib,json,os,socket
from pathlib import Path
_FULL_ROUTE_CACHE = __CACHE_VALUE__
MODE = MODE_VALUE
def code_hash(): return 'f'*64
def digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def cell_path(root,day,budget,delta): return Path(root)/'cells/synthetic.json'
def checked_cell(root,day,budget,delta): return json.loads(cell_path(root,day,budget,delta).read_bytes())
def verify_manifest_files(root,files):
    for name,h in files.items():
        assert hashlib.sha256((Path(root)/name).read_bytes()).hexdigest()==h
def compute_cell(root,day,budget,delta):
    assert not any('TOKEN' in k or 'SECRET' in k or 'CREDENTIAL' in k for k in os.environ)
    if MODE=='network': socket.socket().connect(('127.0.0.1',9))
    return {'date':day,'budget_bus_hours':budget,'additional_bus_seconds':delta,
            'routes':[{'duration_s':12,'legs':['synthetic-full-route']}]} 
'''.replace('__CACHE_VALUE__', "{'preexisting': 1}" if mode == 'cache' else '{}').replace('MODE_VALUE', repr(mode))
    (code / 'case_study.py').write_text(module)
    (root / 'code/requirements.lock.txt').write_bytes((ROOT / 'requirements.lock.txt').read_bytes())
    study = root / 'study'
    (study / 'cells').mkdir(parents=True)
    (study / 'protocol.json').write_bytes(review.encoded({'config': {'study_id': 'corridor-impact-v2'}, 'code_sha256': 'f' * 64}))
    result = {'date': '2026-10-09', 'budget_bus_hours': 2, 'additional_bus_seconds': 0,
              'routes': [{'duration_s': 12, 'legs': ['synthetic-full-route']}]}
    if mode == 'mismatch':
        result['routes'][0]['duration_s'] = 13  # Tampered stored result, then deliberately re-signed below.
    (study / 'cells/synthetic.json').write_bytes(review.encoded({'result': result}))
    files = {p.relative_to(root).as_posix(): review.sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
    (root / 'manifest.json').write_bytes(review.encoded({'files': files, 'dates': ['2026-10-09'], 'code_sha256': 'f' * 64}))
    return root, review.sha((root / 'manifest.json').read_bytes())


@pytest.mark.parametrize('mode,reason', [('match', None), ('mismatch', 'full_result_mismatch'),
    ('cache', 'frozen_code_or_initial_cache_mismatch'), ('network', 'network_unavailable_during_compute'),
    ('credentials', 'credential_environment_in_compute')])
def test_fresh_child_isolation_and_exact_routes(tmp_path, mode, reason):
    import gzip
    import os
    import subprocess
    import sys
    pack, manifest_sha = synthetic_pack(tmp_path, mode)
    provenance = tmp_path / 'provenance.json'
    provenance.write_text('{"fixture":"synthetic-only"}')
    output = tmp_path / 'result.json.gz'
    env = {k: os.environ[k] for k in ('PATH', 'LANG', 'SYSTEMROOT') if k in os.environ}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    if mode == 'credentials':
        env['GITHUB_TOKEN'] = 'synthetic-forbidden-child-token'
    run = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/review_case_study_pack.py'),
        'compute', '--pack', str(pack), '--manifest-sha256', manifest_sha, '--cell', review.SMOKE,
        '--provenance', str(provenance), '--output', str(output)], env=env, capture_output=True, text=True)
    if reason:
        assert run.returncode == 1 and reason in run.stderr
        assert not output.exists()
    else:
        assert run.returncode == 0, run.stderr
        assert run.stdout == ''
        result = json.loads(gzip.decompress(output.read_bytes()))
        assert result['matched'] and result['fresh_process']
        assert result['initial_route_cache_entries'] == result['blocked_access_attempt_count'] == 0
        assert result['recomputed_result']['routes'] == [{'duration_s': 12, 'legs': ['synthetic-full-route']}]


def test_transport_parent_strips_all_tokens_before_real_child(tmp_path, monkeypatch, capsys):
    import gzip
    import os
    from types import SimpleNamespace
    pack, manifest_sha = synthetic_pack(tmp_path)
    archive = tmp_path / 'synthetic.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        for path in pack.rglob('*'):
            if path.is_file():
                output.write(path, path.relative_to(pack).as_posix())
    returned = []
    class SyntheticTransport:
        def __init__(self, token):
            assert token == 'synthetic-parent-token'
        def download(self, release, asset, destination, expected):
            assert review.sha(archive.read_bytes()) == expected
            Path(destination).write_bytes(archive.read_bytes())
        def upload(self, release, name, payload):
            returned.append(json.loads(gzip.decompress(payload)))
    monkeypatch.setattr(review, 'GitHubTransport', SyntheticTransport)
    for name, value in {'GITHUB_REPOSITORY': review.REPOSITORY, 'REVIEW_TOKEN': 'synthetic-parent-token',
        'GITHUB_TOKEN': 'synthetic-job-token', 'ACTIONS_ID_TOKEN_REQUEST_TOKEN': 'synthetic-runtime-token',
        'OTHER_SECRET': 'synthetic-secret', 'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1',
        'GITHUB_SHA': 'a' * 40, 'RUNNER_TEMP': str(tmp_path)}.items():
        monkeypatch.setenv(name, value)
    review.run_review(SimpleNamespace(zip_sha256=review.sha(archive.read_bytes()), manifest_sha256=manifest_sha,
                                      cell=review.SMOKE, release_id=17, asset_id=23))
    assert returned[0]['matched'] and returned[0]['provenance']['run_id'] == '123'
    captured = capsys.readouterr()
    assert captured.out == 'Draft-only review completed.\n' and captured.err == ''
    assert os.environ['REVIEW_TOKEN'] == 'synthetic-parent-token'


def test_preloaded_non_frozen_module_rejected(tmp_path):
    import os
    import shutil
    import subprocess
    import sys
    pack, manifest_sha = synthetic_pack(tmp_path)
    external = tmp_path / 'outside-pack-services'
    shutil.copytree(pack / 'code/services', external)
    provenance = tmp_path / 'provenance.json'
    provenance.write_text('{}')
    loader = "import sys,runpy;sys.path.insert(0,sys.argv[1]);import resilience.pipeline.case_study;sys.argv=sys.argv[2:];runpy.run_path(sys.argv[0],run_name='__main__')"
    run = subprocess.run([sys.executable, '-B', '-c', loader, str(external),
        str(ROOT / 'scripts/review_case_study_pack.py'), 'compute', '--pack', str(pack),
        '--manifest-sha256', manifest_sha, '--cell', review.SMOKE,
        '--provenance', str(provenance), '--output', str(tmp_path / 'result.gz')],
        env={k: os.environ[k] for k in ('PATH', 'LANG') if k in os.environ}, capture_output=True, text=True)
    assert run.returncode == 1 and 'non_frozen_module' in run.stderr
    assert not (tmp_path / 'result.gz').exists()
