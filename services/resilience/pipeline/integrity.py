"""Verify recorded artifacts without rewriting historical identities."""
import hashlib
import json
from datetime import datetime
from pathlib import Path,PurePosixPath,PureWindowsPath
from .analysis import canonical,digest,engine_digest


def sha(data):return hashlib.sha256(data).hexdigest()
def adapter_digest():
    root=Path(__file__).parent
    return sha(b''.join((root/name).read_bytes() for name in ('analysis.py','sensitivity.py','journey_set.py')))
def checked_file(path,expected):
    data=Path(path).read_bytes()
    if sha(data)!=expected:raise ValueError(f'Artifact hash mismatch: {Path(path).name}')
    return data

def recorded_runs(archive):
    """Immutable finals take precedence; compare progress before any filtering."""
    root=archive.root/'processed'
    records={}
    for path in sorted((root/'run-results').glob('*.json')):
        run=json.loads(path.read_bytes())
        if run.get('run_id')!=path.stem:raise ValueError('Immutable result identity differs from filename')
        mutable=root/'experiments'/path.name
        if mutable.exists() and json.loads(mutable.read_bytes())!=run:raise ValueError('Mutable result differs from immutable final')
        records[path.stem]=run
    for path in sorted((root/'experiments').glob('*.json')):
        if path.stem not in records:
            run=json.loads(path.read_bytes())
            if run.get('run_id')!=path.stem:raise ValueError('Mutable result identity differs from filename')
            records[path.stem]=run
    return records

def verify_manifest_files(root,files):
    """Verify the exact reviewed regular-file set, confined to the bundle root."""
    root=Path(root).resolve()
    expected=set(files)
    for name in expected:
        path=PurePosixPath(name);windows=PureWindowsPath(name)
        if path.is_absolute() or path.root or windows.drive or windows.root or '\\' in name or '..' in path.parts or name!=path.as_posix() or name=='manifest.json':raise ValueError('Unsafe manifest path')
        target=root/Path(name)
        if any(part.is_symlink() for part in (target,*target.parents) if part!=root and root in part.parents):raise ValueError('Symlink in manifest path')
        if not target.is_file():raise ValueError('Missing manifest file')
    actual=set()
    for path in root.rglob('*'):
        if path.is_symlink():raise ValueError('Symlink in candidate directory')
        if path.is_file() and path!=root/'manifest.json':actual.add(path.relative_to(root).as_posix())
    if actual!=expected:raise ValueError('Candidate file set differs from manifest')
    for name,digest in files.items():checked_file(root/name,digest)

def verify_run(archive,run_id,*,require_code=True):
    root=archive.root/'processed'
    final=root/'run-results'/f'{run_id}.json'
    run=json.loads(final.read_bytes())
    if run.get('run_id')!=run_id or run.get('status')!='completed' or not run.get('result'):raise ValueError('Run is not an immutable completed result')
    mutable=root/'experiments'/final.name
    if mutable.exists() and json.loads(mutable.read_bytes())!=run:raise ValueError('Mutable result differs from immutable final')
    meta=run.get('metadata')
    if not meta:raise ValueError('Legacy run has no reproducible metadata')
    inp_path=root/'run-inputs'/f'{run_id}.input.json'
    inp=json.loads(checked_file(inp_path,meta['input_sha256']))
    if canonical(inp)!=inp_path.read_bytes():raise ValueError('Input is not canonical')
    if json.loads((root/'run-inputs'/f'{run_id}.metadata.json').read_bytes())!=meta:raise ValueError('Metadata differs from immutable final')
    if run.get('input') is not None and run['input']!=inp:raise ValueError('Embedded input differs')
    for key,field in [('requests','request_set_sha256'),('scenarios','scenario_set_sha256'),('candidates','candidate_set_sha256')]:
        if digest(inp[key])!=meta[field]:raise ValueError(f'{key} identity mismatch')
    snapshot=json.loads(checked_file(root/'snapshots'/f"{inp['snapshot_id']}.json",inp['snapshot_content_sha256']))
    if inp['snapshot_content_sha256']!=meta['snapshot_content_sha256'] or inp['snapshot_id']!=meta['snapshot_id']:raise ValueError('Snapshot identity differs')
    if inp.get('derived_input'):
        derived=inp['derived_input'];checked_file(root/derived['path'],derived['snapshot_content_sha256'])
    for key in ('engine_version','engine_code_sha256','journey_set_version','snapshot_at','source_gtfs_sha256','source_osm_sha256','source_record_ids','budget_bus_hours','search_method','objective_version','candidate_selection_version','max_swap_evaluations','assumptions'):
        left=inp.get(key);right=meta.get(key)
        if key=='snapshot_at':
            left=datetime.fromisoformat(left);right=datetime.fromisoformat(right)
        if left!=right:raise ValueError(f'Input/metadata {key} mismatch')
    cutoff=datetime.fromisoformat(meta['snapshot_at'])
    sources=snapshot['metadata']['sources']
    if sorted(s['record_id'] for s in sources)!=sorted(meta['source_record_ids']):raise ValueError('Source identity differs')
    for source in sources:
        receipt=archive.get(source['record_id'])
        if not receipt or receipt['sha256']!=source['sha256'] or datetime.fromisoformat(receipt['received_at'])>cutoff:raise ValueError('Missing or future source receipt')
        if receipt['status']!='valid':raise ValueError('Quarantined source')
        if receipt['gtfs_sha256'] and receipt['gtfs_sha256']!=meta['source_gtfs_sha256']:raise ValueError('Source schedule digest differs')
        immutable_receipt=archive.root/'raw'/f"{source['record_id']}.json"
        if json.loads(immutable_receipt.read_bytes())!=receipt:raise ValueError('Receipt journal differs from immutable source receipt')
        archive.read(receipt)
    if require_code and (inp['engine_code_sha256']!=engine_digest() or inp.get('adapter_code_sha256')!=adapter_digest()):raise ValueError('Matching historical code unavailable')
    return run,inp
