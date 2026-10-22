"""Private, hash verified offline artifacts and exact analytical recomputation."""
import json
from pathlib import Path
from datetime import date,datetime
from zoneinfo import ZoneInfo
from pydantic import TypeAdapter
from ..contracts import TimetableSnapshot,JourneyRequest,Scenario,RecoveryCandidate
from .analysis import canonical,engine_digest,plan_with_unavailable,ROOT
from .integrity import verify_run,sha,adapter_digest,checked_file,verify_manifest_files
from .files import atomic_write

BRISBANE=ZoneInfo('Australia/Brisbane')
REALTIME_FEEDS={'TripUpdates','VehiclePositions','Alerts'}


def _public_candidate_runs(archive,run_ids,selected_dates):
    """Verify every requested public run before pack output is written."""
    if isinstance(run_ids,(str,bytes)):
        raise ValueError('Public reproduction candidate requires an explicit run id list')
    try:run_ids=tuple(run_ids)
    except TypeError as exc:raise ValueError('Public reproduction candidate requires an explicit run id list') from exc
    if not run_ids or any(not isinstance(rid,str) or not rid.strip() for rid in run_ids):
        raise ValueError('Public reproduction candidate requires non-empty run ids')
    if len(run_ids)!=len(set(run_ids)):raise ValueError('Duplicate public reproduction run id')

    from .evidence import release_evidence
    raw_dates=release_evidence().get('public_bundle_service_dates',[])
    if not isinstance(raw_dates,(list,tuple)) or len(raw_dates)!=3 or len(set(raw_dates))!=3:
        raise ValueError('Public reproduction candidate requires exactly three selected service dates')
    selected=set(raw_dates)
    if selected!=selected_dates:raise ValueError('Selected public service dates changed during candidate validation')

    verified=[];represented=set()
    for rid in run_ids:
        run,inp=verify_run(archive,rid)
        if run.get('run_id')!=rid or run.get('status')!='completed' or not run.get('metadata'):
            raise ValueError(f'Public reproduction candidate contains an incomplete or legacy run: {rid}')
        if inp.get('snapshot_id')!=run.get('snapshot_id'):
            raise ValueError(f'Public reproduction run snapshot identity differs: {rid}')
        snapshot_path=archive.root/'processed'/'snapshots'/f"{inp['snapshot_id']}.json"
        snapshot=json.loads(snapshot_path.read_bytes())
        metadata=snapshot.get('metadata',{})
        captured=datetime.fromisoformat(inp['snapshot_at'])
        stored_at=datetime.fromisoformat(metadata['snapshot_at'])
        if captured.utcoffset() is None or stored_at.utcoffset() is None or captured!=stored_at:
            raise ValueError(f'Public reproduction snapshot time differs: {rid}')
        local=captured.astimezone(BRISBANE)
        service_date=metadata.get('service_date')
        if (metadata.get('snapshot_id')!=inp['snapshot_id'] or service_date!=local.date().isoformat()
                or service_date not in selected or local.weekday()>=5 or not 6<=local.hour<12):
            raise ValueError(f'Public reproduction run is outside a selected weekday morning: {rid}')

        receipts={}
        for source in metadata.get('sources',[]):
            receipt=archive.get(source['record_id'])
            if not receipt:raise ValueError(f'Public reproduction source receipt is missing: {source["record_id"]}')
            receipts[source['record_id']]=receipt
            realtime=source.get('source_kind')=='gtfs_rt' or receipt.get('feed') in REALTIME_FEEDS
            if not realtime:continue
            if receipt.get('feed') not in REALTIME_FEEDS:
                raise ValueError(f'Public reproduction realtime source feed is invalid: {source["record_id"]}')
            received=datetime.fromisoformat(receipt['received_at'])
            details=receipt.get('details',{})
            if isinstance(details,str):details=json.loads(details)
            if (received.utcoffset() is None or received.astimezone(BRISBANE).date()!=local.date()
                    or not 6<=received.astimezone(BRISBANE).hour<12
                    or not isinstance(details,dict) or details.get('development_capture') is not False):
                raise ValueError(f'Public reproduction realtime source is not eligible morning provenance: {source["record_id"]}')
        represented.add(service_date)
        verified.append((rid,run,inp,snapshot,receipts))
    if represented!=selected:
        missing=', '.join(sorted(selected-represented))
        raise ValueError('Public reproduction candidate is missing a selected service date: '+missing)
    return verified


def pack(archive,output,run_ids,extras=(),*,public_candidate=False):
    verified_runs=None
    if public_candidate:
        from .coverage import release_gate
        gate=release_gate(archive)
        blocked=[name for name in ('five_complete_windows','three_real_morning_bundles','licences') if gate.get('gates',{}).get(name) is not True]
        if blocked:raise ValueError('Public reproduction candidate blocked: '+', '.join(blocked))
        from .evidence import release_evidence
        raw_dates=release_evidence().get('public_bundle_service_dates',[])
        try:selected_dates={date.fromisoformat(value).isoformat() for value in raw_dates}
        except (TypeError,ValueError) as exc:raise ValueError('Invalid selected public service dates') from exc
        if len(raw_dates)!=3 or len(selected_dates)!=3:raise ValueError('Public reproduction candidate requires exactly three selected service dates')
        verified_runs=_public_candidate_runs(archive,run_ids,selected_dates)
        run_ids=tuple(item[0] for item in verified_runs)
    dest=Path(output)
    if dest.exists() and any(dest.iterdir()):raise ValueError('Use a fresh reproduction directory')
    def copy(path,relative):atomic_write(dest/relative,path.read_bytes(),immutable=True)
    verified_by_id={item[0]:item[1:] for item in verified_runs} if verified_runs is not None else None
    for rid in run_ids:
        if verified_by_id is None:run,inp=verify_run(archive,rid)
        else:run,inp,snapshot,receipts=verified_by_id[rid]
        for rel in (f'run-results/{rid}.json',f'run-inputs/{rid}.input.json',f'run-inputs/{rid}.metadata.json',f"snapshots/{inp['snapshot_id']}.json"):
            copy(archive.root/'processed'/rel,'processed/'+rel)
        if inp['derived_input']:copy(archive.root/'processed'/inp['derived_input']['path'],'processed/'+inp['derived_input']['path'])
        if verified_by_id is None:snapshot=json.loads((archive.root/'processed'/'snapshots'/f"{inp['snapshot_id']}.json").read_bytes())
        atomic_write(dest/'walking'/f"{inp['snapshot_id']}.json",canonical({'walking_links':snapshot['walking_links'],'source_osm_sha256':inp['source_osm_sha256'],'licence':'ODbL 1.0; OpenStreetMap contributors; derived walking database'}),immutable=True)
        for sid in inp['source_record_ids']:
            receipt=receipts[sid] if verified_by_id is not None else archive.get(sid)
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
    atomic_write(dest/'README.txt','Prepared reproduction pack of real recorded source inputs; scenarios and recovery are hypothetical. Translink CC BY 4.0 source conditions apply; see code/DATA_LICENSE.md. OSM walking database is separately under walking/ with ODbL attribution. Verify the externally reviewed manifest hash before recomputing. No network downloads are used. Local candidate preparation does not authorize publication: all external release gates must pass.\n',immutable=True)
    manifest={'version':1,'private_only':not public_candidate,'candidate_preparation_only':public_candidate,'run_ids':run_ids,'engine_code_sha256':engine_digest(),'adapter_code_sha256':adapter_digest(),'files':{p.relative_to(dest).as_posix():sha(p.read_bytes()) for p in sorted(dest.rglob('*')) if p.is_file()}}
    atomic_write(dest/'manifest.json',canonical(manifest),immutable=True)
    return {'root':str(dest),'manifest_sha256':sha(canonical(manifest)),'files':len(manifest['files'])}

def comparable(result):
    result=result.model_dump(mode='json') if hasattr(result,'model_dump') else result
    p=result['plan']
    return {'metrics':p['evaluation']['metrics'],'objective':p['objective'],'candidate_ids':p['candidate_ids'],'duties':p['duties'],'bus_hours':p['bus_hours'],'bus_count':p['bus_count'],'no_intervention':result['no_intervention'],'busiest_affected_pattern':result['busiest_affected_pattern'],'considered_candidate_ids':result['considered_candidate_ids'],'infeasible_candidates':result['infeasible_candidates']}

def reproduce(output,run_ids=None,expected_manifest_sha256=None,*,on_progress=None):
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
        if on_progress:on_progress(reports[-1],len(reports))
    return reports
