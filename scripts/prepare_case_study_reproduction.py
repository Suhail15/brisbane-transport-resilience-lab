"""Prepare a reviewed pack with complete Python package boundaries.

This packaging projection adds two docstring-only initializers to the unchanged
producer's pack before its final manifest is externally pinned. It performs no
journey calculation. Recompute with Python -B to preserve the strict file set.
"""
import argparse
import ast
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services'))
from resilience.pipeline.case_study import canonical, code_hash, load_json, pack, sha, write_json
from resilience.pipeline.files import atomic_write
from resilience.pipeline.integrity import verify_manifest_files

INITIALIZERS = ('services/resilience/__init__.py',
                'services/resilience/pipeline/__init__.py')


def prepare(source, destination, dates, report):
    source, destination, report = Path(source), Path(destination), Path(report)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Use a new empty reproduction destination')
    if report.resolve().is_relative_to(destination.resolve()):
        raise ValueError('Projection report must be outside the immutable pack')
    initializers = {}
    for relative in INITIALIZERS:
        payload = (ROOT / relative).read_bytes()
        body = ast.parse(payload.decode('utf-8')).body
        if not (len(body) == 1 and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            raise ValueError('Initializer is not docstring-only; review required: ' + relative)
        initializers[relative] = payload
    source_commit, commit_matches = None, None
    try:
        head = subprocess.run(['git', 'rev-parse', '--verify', 'HEAD'], cwd=ROOT,
                              capture_output=True, check=False)
        if head.returncode == 0:
            source_commit = head.stdout.decode().strip()
            commit_matches = all(subprocess.run(['git', 'show', source_commit + ':' + relative],
                cwd=ROOT, capture_output=True, check=True).stdout == payload
                for relative, payload in initializers.items())
            if not commit_matches:
                raise ValueError('Initializer differs from its source commit; review required')
    except FileNotFoundError:
        pass  # A source ZIP can still bind exact initializer content hashes.
    before = code_hash()
    original = pack(source, destination, dates)
    manifest = load_json(destination / 'manifest.json')
    if manifest['code_sha256'] != before:
        raise ValueError('Producer code changed during packaging')
    projection = []
    for relative, payload in initializers.items():
        target = 'code/' + relative
        atomic_write(destination / target, payload, immutable=True)
        projection.append({'path': target, 'source_relative_path': relative,
                           'sha256': sha(payload), 'docstring_only': True})
    manifest['files'] = {p.relative_to(destination).as_posix(): sha(p.read_bytes())
        for p in sorted(destination.rglob('*')) if p.is_file() and p != destination / 'manifest.json'}
    # This is the explicitly reviewed pre-pin packaging projection, not a run edit.
    atomic_write(destination / 'manifest.json', canonical(manifest))
    verify_manifest_files(destination, manifest['files'])
    if code_hash() != before:
        raise ValueError('Producer code changed during initializer projection')
    result = {'schema_version': 1, 'projection_version': 'docstring-package-initializers-v1',
        'packaging_only': True, 'projection_complete': True,
        'initial_manifest_sha256': original['manifest_sha256'],
        'reproduction_manifest_sha256': sha((destination / 'manifest.json').read_bytes()),
        'protocol_sha256': sha((source / 'protocol.json').read_bytes()),
        'code_sha256': before, 'code_sha256_unchanged': True,
        'initializer_source_commit': source_commit, 'initializers_match_source_commit': commit_matches,
        'initializer_files': projection, 'dates': list(dates),
        'recompute_command': 'python -B code/scripts/run_case_study.py reproduce --destination . --expected-manifest-sha256 ' + sha((destination / 'manifest.json').read_bytes())}
    write_json(report, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--dates', nargs='+', required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.source, args.destination, args.dates, args.report)
    print(canonical(result).decode(), flush=True)


if __name__ == '__main__':
    main()
