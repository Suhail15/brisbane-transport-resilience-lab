"""Private, hash verified offline artifacts and exact analytical recomputation."""
import json
from pathlib import Path
from pydantic import TypeAdapter
from ..contracts import TimetableSnapshot,JourneyRequest,Scenario,RecoveryCandidate
from .analysis import canonical,engine_digest,plan_with_unavailable,ROOT
from .integrity import verify_run,sha,adapter_digest,checked_file,verify_manifest_files
from .files import atomic_write


def pack(archive,output,run_ids,extras=()):
    dest=Path(output)
    if dest.exists() and any(dest.iterdir()):raise ValueError('Use a fresh reproduction directory')
    def copy(path,relative):atomic_write(dest/relative,path.read_bytes(),immutable=True)
    for rid in run_ids:
        run,inp=verify_run(archive,rid)
        for rel in (f'run-results/{rid}.json',f'run-inputs/{rid}.input.json',f'run-inputs/{rid}.metadata.json',f"snapshots/{inp['snapshot_id']}.json"):
            copy(archive.root/'processed'/rel,'processed/'+rel)
        if inp['derived_input']:copy(archive.root/'processed'/inp['derived_input']['path'],'processed/'+inp['derived_input']['path'])
        snapshot=json.loads((archive.root/'processed'/'snapshots'/f"{inp['snapshot_id']}.json").read_bytes())
        atomic_write(dest/'walking'/f"{inp['snapshot_id']}.json",canonical({'walking_links':snapshot['walking_links'],'source_osm_sha256':inp['source_osm_sha256'],'licence':'ODbL 1.0; OpenStreetMap contributors; derived walking database'}),immutable=True)
        for sid in inp['source_record_ids']:
            receipt=archive.get(sid)
            atomic_write(dest/'receipts'/f'{sid}.json',canonical(receipt),immutable=True)
            copy(archive.root/receipt['object_path'],receipt['object_path'])
    for path in extras:copy(Path(path),'supplementary/'+Path(path).name)
    if extras:
        cutoff=min(json.loads((archive.root/'processed/run-inputs'/f'{rid}.input.json').read_bytes())['snapshot_at'] for rid in run_ids)
        from datetime import datetime
        od=archive.latest('MONTHLY_OD',datetime.fromisoformat(cutoff))
        if od:
            archive.read(od)
            atomic_write(dest/'receipts'/f"{od['record_id']}.json",canonical(od),immutable=True)
            copy(archive.root/od['object_path'],od['object_path'])
    for path in [ROOT/'services/resilience/contracts.py',*sorted((ROOT/'services/resilience/engine').glob('*.py')),*[ROOT/'services/resilience/pipeline'/n for n in ('analysis.py','sensitivity.py','journey_set.py','integrity.py','reproduction.py','files.py','proxy.py')],ROOT/'configs/journey-set.v1.json',ROOT/'requirements.lock.txt',ROOT/'scripts/reproduce.py',ROOT/'LICENSE',ROOT/'DATA_LICENSE.md']:
        copy(path,'code/'+path.relative_to(ROOT).as_posix())
    atomic_write(dest/'walking/ATTRIBUTION.txt','© OpenStreetMap contributors. ODbL 1.0: https://opendatacommons.org/licenses/odbl/1-0/\nWalking data is an OSM-derived database; retain attribution and applicable share-alike obligations. Full snapshots contain the same walking data.\n',immutable=True)
    atomic_write(dest/'README.txt','Private development reproduction pack. Real recorded afternoon inputs; scenarios and recovery are hypothetical. Translink CC BY 4.0 source conditions apply; publication approval is pending. See code/DATA_LICENSE.md. OSM walking database is separately under walking/ with ODbL attribution. Verify the externally reviewed manifest hash before recomputing. No network downloads are used.\n',immutable=True)
    manifest={'version':1,'private_only':True,'run_ids':run_ids,'engine_code_sha256':engine_digest(),'adapter_code_sha256':adapter_digest(),'files':{p.relative_to(dest).as_posix():sha(p.read_bytes()) for p in sorted(dest.rglob('*')) if p.is_file()}}
    atomic_write(dest/'manifest.json',canonical(manifest),immutable=True)
    return {'root':str(dest),'manifest_sha256':sha(canonical(manifest)),'files':len(manifest['files'])}

def comparable(result):
    result=result.model_dump(mode='json') if hasattr(result,'model_dump') else result
    p=result['plan']
    return {'metrics':p['evaluation']['metrics'],'objective':p['objective'],'candidate_ids':p['candidate_ids'],'duties':p['duties'],'bus_hours':p['bus_hours'],'bus_count':p['bus_count'],'no_intervention':result['no_intervention'],'busiest_affected_pattern':result['busiest_affected_pattern'],'considered_candidate_ids':result['considered_candidate_ids'],'infeasible_candidates':result['infeasible_candidates']}

def reproduce(output,run_ids=None,expected_manifest_sha256=None):
    root=Path(output);manifest_bytes=(root/'manifest.json').read_bytes()
    if expected_manifest_sha256 and sha(manifest_bytes)!=expected_manifest_sha256:raise ValueError('Reviewed manifest identity mismatch')
    manifest=json.loads(manifest_bytes)
    verify_manifest_files(root,manifest['files'])
    if manifest['engine_code_sha256']!=engine_digest() or manifest['adapter_code_sha256']!=adapter_digest():raise ValueError('Use the matching engine and adapter revision')
    reports=[]
    for rid in run_ids or manifest['run_ids']:
        if rid not in manifest['run_ids']:raise ValueError('Run not present in pack')
        inp=json.loads((root/'processed/run-inputs'/f'{rid}.input.json').read_bytes());saved=json.loads((root/'processed/run-results'/f'{rid}.json').read_bytes())
        checked_file(root/'processed/run-inputs'/f'{rid}.input.json',saved['metadata']['input_sha256'])
        path=root/'processed'/inp['derived_input']['path'] if inp['derived_input'] else root/'processed/snapshots'/f"{inp['snapshot_id']}.json"
        snapshot=TimetableSnapshot.model_validate_json(path.read_bytes())
        result=plan_with_unavailable(snapshot,TypeAdapter(tuple[JourneyRequest,...]).validate_python(inp['requests']),TypeAdapter(tuple[Scenario,...]).validate_python(inp['scenarios']),TypeAdapter(tuple[RecoveryCandidate,...]).validate_python(inp['candidates']),inp['budget_bus_hours'],max_swap_evaluations=inp['max_swap_evaluations'])
        if comparable(result)!=comparable(saved['result']):raise ValueError(f'Exact recomputation mismatch: {rid}')
        reports.append({'run_id':rid,'matched':True,'metrics':result.plan.evaluation.metrics.model_dump(mode='json')})
    return reports
