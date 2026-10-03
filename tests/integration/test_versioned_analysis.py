from datetime import datetime,date,timezone
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from resilience.contracts import (TimetableSnapshot,SnapshotMetadata,SourceRecord,Stop,Connection,QualityMetadata,BusPattern,PatternStop,PatternPair,JourneyRequest,RecoveryCandidate)
from resilience.pipeline.archive import Archive
from resilience.pipeline.analysis import canonical,digest,prepare_input,persist_input,plan_with_unavailable
from resilience.pipeline.sensitivity import stress_snapshot
from resilience.engine import build_recovery_duty

@pytest.fixture
def snapshot():
    # Synthetic chronology/duty fixture, never pilot coverage or passenger evidence.
    metadata=SnapshotMetadata(snapshot_id='fixture',snapshot_at=datetime.fromisoformat('2026-10-02T00:10:00+10:00'),service_date=date(2026,10,2),sources=(SourceRecord(record_id='gtfs',source_kind='gtfs',received_at=datetime.fromisoformat('2026-10-02T00:00:00+10:00'),sha256='a'*64,source_ref='https://example.invalid'),),quality=QualityMetadata(schedule_status='verified'))
    stops=tuple(Stop(stop_id=x,latitude=-27.5,longitude=153.02+i*.001) for i,x in enumerate(('a','b','c')))
    cs=(Connection(connection_id='bus:0',trip_instance_id='bus',route_id='r',mode='bus',sequence=0,from_stop_id='a',to_stop_id='b',departure_s=1000,arrival_s=1600),Connection(connection_id='in:0',trip_instance_id='in',route_id='r',mode='bus',sequence=0,from_stop_id='b',to_stop_id='a',departure_s=1000,arrival_s=1600),Connection(connection_id='progress:0',trip_instance_id='progress',route_id='r',mode='bus',sequence=0,from_stop_id='a',to_stop_id='b',departure_s=500,arrival_s=700),Connection(connection_id='progress:1',trip_instance_id='progress',route_id='r',mode='bus',sequence=1,from_stop_id='b',to_stop_id='c',departure_s=800,arrival_s=1000),Connection(connection_id='rail:0',trip_instance_id='rail',route_id='rail',mode='rail',sequence=0,from_stop_id='a',to_stop_id='c',departure_s=1000,arrival_s=1100),Connection(connection_id='zero:0',trip_instance_id='zero',route_id='r',mode='bus',sequence=0,from_stop_id='b',to_stop_id='c',departure_s=1000,arrival_s=1000))
    def pattern(pid,a,b):return BusPattern(pattern_id=pid,route_id='r',direction_id=pid,source_trip_instance_ids=(('bus',) if pid=='out' else ('in',)),stops=(PatternStop(stop_id=a,arrival_offset_s=0,departure_offset_s=0),PatternStop(stop_id=b,arrival_offset_s=600,departure_offset_s=600)))
    pair=PatternPair(pair_id='pair',outbound=pattern('out','a','b'),inbound=pattern('in','b','a'))
    return TimetableSnapshot(metadata=metadata,stops=stops,connections=cs,recovery_pairs=(pair,))

def test_canonical_hash_defaults_budget_and_immutable_input(tmp_path,snapshot):
    archive=Archive(tmp_path);path=tmp_path/'processed/snapshots/fixture.json';path.parent.mkdir(parents=True);path.write_text(snapshot.model_dump_json())
    requests=(JourneyRequest(request_id='r',origin_stop_id='a',destination_stop_id='b',departure_s=600),)
    normalized,metadata=prepare_input(archive,snapshot,requests,(),(),0)
    assert metadata.input_sha256==digest(normalized)
    assert metadata.candidate_set_sha256==digest([])
    assert 'od_weight' in normalized['requests'][0] and normalized['requests'][0]['od_weight'] is None
    other,_=prepare_input(archive,snapshot,requests,(),(),2)
    assert digest(other)!=metadata.input_sha256
    with pytest.raises(ValidationError):metadata.budget_bus_hours=2
    persist_input(archive,'run',normalized,metadata)
    with pytest.raises(ValueError):persist_input(archive,'run',other,metadata)
    assert json.loads((tmp_path/'processed/run-inputs/run.metadata.json').read_text())==metadata.model_dump(mode='json')

def test_unavailable_requests_remain_in_all_denominators(snapshot):
    requests=(JourneyRequest(request_id='valid',origin_stop_id='a',destination_stop_id='b',departure_s=600),JourneyRequest(request_id='missing',origin_stop_id='absent',destination_stop_id='b',departure_s=600))
    result=plan_with_unavailable(snapshot,requests,(),(),0)
    metrics=result.plan.evaluation.metrics
    assert metrics.request_count==2 and metrics.baseline_reachable_count==1
    assert metrics.baseline_total_capped_duration_s==6400
    assert len(result.plan.evaluation.baseline)==2 and not result.plan.evaluation.baseline[1].reachable
    assert result.plan.objective.total_capped_duration_s==metrics.recovered_total_capped_duration_s
    empty=plan_with_unavailable(snapshot,(requests[1],),(),(),0)
    assert empty.plan.evaluation.metrics.request_count==1
    assert empty.plan.objective.total_capped_duration_s==5400

def test_running_time_stress_chronology_and_complete_duties(snapshot):
    stressed,manifest=stress_snapshot(snapshot,300)
    original={c.connection_id:c for c in snapshot.connections};changed={c.connection_id:c for c in stressed.connections}
    assert changed['bus:0'].departure_s==1000 and changed['bus:0'].arrival_s==1900
    assert changed['progress:0']==original['progress:0']
    assert changed['progress:1'].departure_s==800 and changed['progress:1'].arrival_s==1120
    assert changed['rail:0']==original['rail:0']
    assert manifest['unsupported_trip_ids']==['zero']
    assert stressed.walking_links==snapshot.walking_links
    candidate=RecoveryCandidate(candidate_id='candidate',pair_id='pair',activation_s=1200)
    nominal,_=build_recovery_duty(snapshot,candidate);stress_duty,connections=build_recovery_duty(stressed,candidate)
    assert nominal.cycle_count==4 and stress_duty.cycle_count==3
    assert all(c.arrival_s<=stress_duty.duty_end_s for c in connections)
    assert {p.pair_id for p in stressed.recovery_pairs}=={'pair'}

def test_backend_restart_reconciles_pending_and_labels_legacy(tmp_path,monkeypatch):
    import resilience.api as api
    archive=Archive(tmp_path);root=tmp_path/'processed/experiments';root.mkdir(parents=True)
    (root/'pending.json').write_text(json.dumps({'run_id':'pending','status':'running','progress':.1,'result':None}))
    (root/'old.json').write_text(json.dumps({'run_id':'old','status':'completed','progress':1,'result':{}}))
    monkeypatch.setattr(api,'archive',archive);api.reconcile_runs()
    assert json.loads((root/'pending.json').read_text())['status']=='failed'
    legacy=api.read_run(root/'old.json')
    assert legacy['legacy_unversioned'] is True and legacy['reproducible'] is False
    assert 'metadata' not in legacy

def test_bundle_preserves_submitted_hashes_and_labels_legacy(tmp_path,snapshot,monkeypatch):
    from resilience.pipeline import bundle
    archive=Archive(tmp_path)
    receipt=archive.append('GTFS',b'fixture schedule',snapshot.metadata.sources[0].received_at,'https://example.invalid')
    source=snapshot.metadata.sources[0].model_copy(update={'record_id':receipt['record_id'],'sha256':receipt['sha256']})
    snapshot=snapshot.model_copy(update={'metadata':snapshot.metadata.model_copy(update={'sources':(source,)})})
    path=tmp_path/'processed/snapshots/fixture.json';path.parent.mkdir(parents=True);path.write_text(snapshot.model_dump_json())
    requests=(JourneyRequest(request_id='r',origin_stop_id='a',destination_stop_id='b',departure_s=600),)
    normalized,metadata=prepare_input(archive,snapshot,requests,(),(),0);persist_input(archive,'versioned',normalized,metadata)
    runs=tmp_path/'processed/experiments';runs.mkdir()
    record={'run_id':'versioned','snapshot_id':'fixture','status':'completed','progress':1,'url':'experiments/versioned.json','metadata':metadata.model_dump(mode='json'),'input':normalized,'result':plan_with_unavailable(snapshot,requests,(),(),0).model_dump(mode='json')}
    (runs/'versioned.json').write_text(json.dumps(record))
    finals=tmp_path/'processed/run-results';finals.mkdir();(finals/'versioned.json').write_bytes(canonical(record))
    legacy={k:v for k,v in record.items() if k not in ('metadata','input')};legacy.update(run_id='legacy',url='experiments/legacy.json');(runs/'legacy.json').write_text(json.dumps(legacy))
    monkeypatch.setattr(bundle,'network',lambda *args:{'type':'FeatureCollection','features':[]})
    monkeypatch.setattr(bundle,'display_frame',lambda *args:{'snapshot_id':'fixture'})
    monkeypatch.setattr(bundle,'choices',lambda *args:{'snapshot_id':'fixture'})
    output=tmp_path/'bundle';bundle.export_bundle(archive,output)
    import gzip
    catalog=json.loads((output/'catalog.json').read_text())
    network_path=output/catalog['snapshots'][0]['network_url']
    assert network_path.suffix=='.gz'
    assert json.loads(gzip.decompress(network_path.read_bytes()))=={'type':'FeatureCollection','features':[]}
    assert not (output/'network.geojson').exists()
    exported=json.loads((output/'experiments/versioned.json').read_text())
    assert exported['metadata']==metadata.model_dump(mode='json')
    assert digest(json.loads((output/exported['input_url']).read_text()))==metadata.input_sha256
    assert json.loads((output/'experiments/legacy.json').read_text())['legacy_unversioned'] is True
    with pytest.raises(ValueError):bundle.export_bundle(archive,tmp_path/'public',public=True)
    (tmp_path/'processed/run-inputs/versioned.input.json').write_text('{}')
    with pytest.raises(ValueError,match='hash mismatch'):bundle.export_bundle(archive,tmp_path/'corrupt')

def test_stress_integer_ceil_does_not_add_float_rounding_second(snapshot):
    retained=tuple(c for c in snapshot.connections if c.trip_instance_id!='bus')
    split=(Connection(connection_id='bus:0',trip_instance_id='bus',route_id='r',mode='bus',sequence=0,from_stop_id='a',to_stop_id='b',departure_s=1000,arrival_s=1100),Connection(connection_id='bus:1',trip_instance_id='bus',route_id='r',mode='bus',sequence=1,from_stop_id='b',to_stop_id='c',departure_s=1100,arrival_s=4000))
    source=snapshot.model_copy(update={'connections':retained+split})
    stressed,_=stress_snapshot(source,300)
    first=next(c for c in stressed.connections if c.connection_id=='bus:0')
    assert first.arrival_s==1110 # exact100*3300/3000, not floatceil110.00000000000001
