import json
from pathlib import Path
import pytest
from resilience.pipeline.evidence import evidence_check
from resilience.pipeline.integrity import sha,checked_file
from resilience.pipeline.run_index import summary

def test_boolean_reference_does_not_authorize_release(tmp_path):
    assert evidence_check({'passed':True,'evidence_ref':'arbitrary'},name='licences',revision='abc',root=tmp_path)[0] is False
    review=tmp_path/'review.md';review.write_text('Concrete reviewed scope')
    report={'gate':'licences','candidate_revision':'abc','passed':True,'publisher_approval_received':True,'scope':'selected sources and public bytes','checks':[{'passed':True,'evidence':{'path':'review.md','sha256':sha(review.read_bytes())}}],'acceptance':{'reviewer':'root','reference':'review.md','sha256':sha(review.read_bytes())}}
    p=tmp_path/'report.json';p.write_text(json.dumps(report));item={'report':'report.json','sha256':sha(p.read_bytes())}
    assert evidence_check(item,name='licences',revision='abc',root=tmp_path)[0]
    assert not evidence_check(item,name='licences',revision='other',root=tmp_path)[0]
    review.write_text('Changed acceptance');assert not evidence_check(item,name='licences',revision='abc',root=tmp_path)[0]

def test_pack_hash_rejects_changed_snapshot_or_derived_bytes(tmp_path):
    path=tmp_path/'snapshot.json';path.write_bytes(b'{"snapshot":"recorded"}');digest=sha(path.read_bytes())
    checked_file(path,digest);path.write_bytes(b'{"snapshot":"changed"}')
    with pytest.raises(ValueError,match='hash mismatch'):checked_file(path,digest)

def test_summary_keeps_identity_without_routes():
    inp={'requests':[{}]*100,'scenarios':[{'kind':'stop_unavailable','stop_ids':['3713'],'start_s':100,'end_s':200}],'search_method':'greedy_bounded_swap'}
    r={'run_id':'r','status':'completed','snapshot_id':'s','metadata':{'budget_bus_hours':4,'request_set_sha256':'q','scenario_set_sha256':'x','candidate_set_sha256':'c','max_swap_evaluations':16,'assumptions':{'bus_running_time_sensitivity_seconds':300}},'result':{'plan':{'bus_hours':2,'evaluation':{'metrics':{'restored_count':0}},'objective':{}}},'reproducible':True}
    value=summary(r,inp)
    assert value['request_count']==100 and value['budget_bus_hours']==4 and value['used_bus_hours']==2
    assert value['search_method']=='greedy_bounded_swap' and value['scenario_summaries'][0]['target_ids']==['3713']
    assert 'baseline' not in str(value.keys()) and value['hypothetical'] is True

def test_full_artifact_verification_rejects_results_snapshot_derived_and_future(tmp_path):
    from datetime import datetime,date,timezone
    from resilience.contracts import TimetableSnapshot,SnapshotMetadata,SourceRecord,JourneyRequest
    from resilience.pipeline.archive import Archive
    from resilience.pipeline.analysis import canonical,prepare_input,persist_input,plan_with_unavailable
    from resilience.pipeline.integrity import verify_run
    ar=Archive(tmp_path);at=datetime(2026,10,2,tzinfo=timezone.utc)
    receipt=ar.append('GTFS',b'synthetic schedule',at,'https://example.invalid')
    snap=TimetableSnapshot(metadata=SnapshotMetadata(snapshot_id='fixture',snapshot_at=at,service_date=date(2026,10,2),sources=(SourceRecord(record_id=receipt['record_id'],source_kind='gtfs',received_at=at,sha256=receipt['sha256'],source_ref=receipt['source_url']),)),stops=(),connections=())
    p=tmp_path/'processed/snapshots/fixture.json';p.parent.mkdir(parents=True);p.write_bytes(canonical(snap))
    derived=tmp_path/'processed/derived-inputs/fixture.json';derived.parent.mkdir();derived.write_bytes(canonical(snap))
    req=(JourneyRequest(request_id='absent',origin_stop_id='a',destination_stop_id='b',departure_s=0),)
    inp,meta=prepare_input(ar,snap,req,(),(),0,derived={'path':'derived-inputs/fixture.json','snapshot_content_sha256':sha(derived.read_bytes())})
    persist_input(ar,'r',inp,meta)
    run={'run_id':'r','status':'completed','snapshot_id':'fixture','input':inp,'metadata':meta.model_dump(mode='json'),'result':plan_with_unavailable(snap,req,(),(),0).model_dump(mode='json')}
    f=tmp_path/'processed/run-results/r.json';f.parent.mkdir();f.write_bytes(canonical(run))
    m=tmp_path/'processed/experiments/r.json';m.parent.mkdir();m.write_bytes(canonical(run));verify_run(ar,'r')
    altered=dict(run,status='failed');m.write_bytes(canonical(altered))
    with pytest.raises(ValueError,match='Mutable result'):verify_run(ar,'r')
    m.write_bytes(canonical(run));original=p.read_bytes();p.write_bytes(b'{}')
    with pytest.raises(ValueError,match='hash mismatch'):verify_run(ar,'r')
    p.write_bytes(original);derived.write_bytes(b'{}')
    with pytest.raises(ValueError,match='hash mismatch'):verify_run(ar,'r')
    derived.write_bytes(original)
    with ar.connect() as db:db.execute('UPDATE receipts SET received_at=?',('2026-10-03T00:00:00+00:00',))
    with pytest.raises(ValueError,match='future source'):verify_run(ar,'r')

def test_proxy_wall_clock_bins_and_fraction_conservation():
    from fractions import Fraction
    from resilience.pipeline.proxy import time_bin,BINS,fraction
    assert time_bin('2026-10-02',14*3600)==BINS[1]
    assert time_bin('2026-10-02',15*3600)==BINS[2]
    assert time_bin('2026-10-02',25*3600)=='Weekend'
    assert fraction(Fraction(123,3))=={'numerator':41,'denominator':1}
    assert Fraction(123,3)*3+Fraction(37,2)*2==160


def test_proxy_duration_cap_is_independent_of_reachability_horizon():
    from resilience.pipeline.proxy import capped_duration
    def route(arrival,reachable=True):return {'reachable':reachable,'arrival_s':arrival,'request':{'departure_s':0}}
    assert capped_duration(route(3700))==3700
    assert capped_duration(route(6000))==5400
    assert capped_duration(route(None,False))==5400

@pytest.fixture
def final_archive(tmp_path,monkeypatch):
    from datetime import datetime,date,timezone
    from resilience.contracts import TimetableSnapshot,SnapshotMetadata,SourceRecord,JourneyRequest
    from resilience.pipeline.archive import Archive
    from resilience.pipeline.analysis import canonical,prepare_input,persist_input,plan_with_unavailable
    from resilience.pipeline import bundle
    ar=Archive(tmp_path);at=datetime(2026,10,2,tzinfo=timezone.utc)
    receipt=ar.append('GTFS',b'synthetic export fixture',at,'https://example.invalid')
    snap=TimetableSnapshot(metadata=SnapshotMetadata(snapshot_id='fixture',snapshot_at=at,service_date=date(2026,10,2),sources=(SourceRecord(record_id=receipt['record_id'],source_kind='gtfs',received_at=at,sha256=receipt['sha256'],source_ref=receipt['source_url']),)),stops=(),connections=())
    p=tmp_path/'processed/snapshots/fixture.json';p.parent.mkdir(parents=True);p.write_bytes(canonical(snap))
    req=(JourneyRequest(request_id='absent',origin_stop_id='a',destination_stop_id='b',departure_s=0),)
    inp,meta=prepare_input(ar,snap,req,(),(),0);persist_input(ar,'final',inp,meta)
    run={'run_id':'final','status':'completed','snapshot_id':'fixture','url':'experiments/final.json','input':inp,'metadata':meta.model_dump(mode='json'),'result':plan_with_unavailable(snap,req,(),(),0).model_dump(mode='json')}
    for folder in ('experiments','run-results'):
        p=tmp_path/'processed'/folder/'final.json';p.parent.mkdir();p.write_bytes(canonical(run))
    monkeypatch.setattr(bundle,'network',lambda *args:{'type':'FeatureCollection','features':[]})
    monkeypatch.setattr(bundle,'display_frame',lambda *args:{'snapshot_id':'fixture'})
    monkeypatch.setattr(bundle,'choices',lambda *args:{'snapshot_id':'fixture'})
    return ar,run

@pytest.mark.parametrize('change',['failed_status','missing_metadata','wrong_snapshot'])
def test_export_and_api_reject_mutable_disagreement_before_filter(final_archive,tmp_path,monkeypatch,change):
    import asyncio
    import resilience.api as api
    from fastapi import HTTPException
    from resilience.pipeline.bundle import export_bundle
    ar,run=final_archive;altered=dict(run)
    if change=='failed_status':altered['status']='failed'
    elif change=='missing_metadata':altered.pop('metadata')
    else:altered['snapshot_id']='not-selected'
    (ar.root/'processed/experiments/final.json').write_text(json.dumps(altered))
    with pytest.raises(ValueError,match='Mutable result'):export_bundle(ar,tmp_path/'bundle')
    monkeypatch.setattr(api,'archive',ar);monkeypatch.setattr(api,'runs',{})
    with pytest.raises(HTTPException) as exc:asyncio.run(api.experiments())
    assert exc.value.status_code==409 and 'Mutable result' in exc.value.detail

def test_export_and_api_include_final_without_mutable(final_archive,tmp_path,monkeypatch):
    import asyncio
    import resilience.api as api
    from resilience.pipeline.bundle import export_bundle
    ar,run=final_archive;(ar.root/'processed/experiments/final.json').unlink()
    assert export_bundle(ar,tmp_path/'bundle')['completed_runs']==1
    from resilience.pipeline.integrity import verify_manifest_files
    files=json.loads((tmp_path/'bundle/manifest.json').read_text())['files']
    assert 'experiments/final.json' in files and all('\\' not in key for key in files)
    verify_manifest_files(tmp_path/'bundle',files)
    exported=json.loads((tmp_path/'bundle/experiments/final.json').read_text())
    assert exported['metadata']==run['metadata'] and not exported['legacy_unversioned']
    monkeypatch.setattr(api,'archive',ar);monkeypatch.setattr(api,'runs',{})
    indexed=asyncio.run(api.experiments())['runs']
    assert len(indexed)==1 and indexed[0]['run_id']=='final' and indexed[0]['reproducible']

def test_release_verifier_rejects_unlisted_file_in_accepted_candidate(tmp_path,monkeypatch):
    import runpy,sys
    from resilience.pipeline import coverage,evidence
    root=tmp_path/'candidate';root.mkdir();(root/'listed.txt').write_text('reviewed')
    manifest={'public':True,'files':{'listed.txt':sha((root/'listed.txt').read_bytes())}}
    (root/'manifest.json').write_text(json.dumps(manifest))
    report=tmp_path/'accepted.json';report.write_text(json.dumps({'public_manifest_sha256':sha((root/'manifest.json').read_bytes())}))
    monkeypatch.setattr(coverage,'release_gate',lambda *args:{'passed':True,'blocking':[]})
    monkeypatch.setattr(evidence,'release_evidence',lambda:{'public_artifacts':{'report':str(report)}})
    monkeypatch.setattr(sys,'argv',['verify_release.py','--bundle',str(root),'--data-dir',str(tmp_path/'archive')])
    script=Path(__file__).resolve().parents[2]/'scripts/verify_release.py'
    runpy.run_path(str(script),run_name='__main__')
    (root/'unreviewed.txt').write_text('unreviewed')
    with pytest.raises(ValueError,match='file set differs'):runpy.run_path(str(script),run_name='__main__')

@pytest.mark.parametrize('unsafe',['../outside.txt','/absolute.txt','C:/absolute.txt','..\\outside.txt','alias.txt'])
def test_manifest_verification_rejects_escaping_paths(tmp_path,unsafe):
    from resilience.pipeline.integrity import verify_manifest_files
    root=tmp_path/'candidate';root.mkdir();outside=tmp_path/'outside.txt';outside.write_text('outside')
    if unsafe=='alias.txt':(root/unsafe).symlink_to(outside)
    with pytest.raises(ValueError,match='Unsafe manifest path|Symlink'):verify_manifest_files(root,{unsafe:sha(outside.read_bytes())})

def test_reproduction_rejects_unlisted_file_in_externally_anchored_pack(tmp_path):
    from resilience.pipeline.reproduction import reproduce
    from resilience.pipeline.analysis import engine_digest
    from resilience.pipeline.integrity import adapter_digest
    (tmp_path/'reviewed.txt').write_text('reviewed')
    manifest={'files':{'reviewed.txt':sha((tmp_path/'reviewed.txt').read_bytes())},'engine_code_sha256':engine_digest(),'adapter_code_sha256':adapter_digest(),'run_ids':[]}
    (tmp_path/'manifest.json').write_text(json.dumps(manifest));expected=sha((tmp_path/'manifest.json').read_bytes())
    assert reproduce(tmp_path,expected_manifest_sha256=expected)==[]
    (tmp_path/'unreviewed.txt').write_text('unreviewed')
    with pytest.raises(ValueError,match='file set differs'):reproduce(tmp_path,expected_manifest_sha256=expected)
