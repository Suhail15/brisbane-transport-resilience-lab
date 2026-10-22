"""Synthetic public-candidate provenance checks; no recorded archive is read."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from resilience.pipeline.analysis import canonical
from resilience.pipeline import coverage,evidence,reproduction


DATES=('2026-10-19','2026-10-20','2026-10-21')


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(canonical(value))


@pytest.fixture
def public_candidate(tmp_path,monkeypatch):
    root=tmp_path/'archive'
    archive=SimpleNamespace(root=root,receipts={},verified={})
    for index,day in enumerate(DATES):
        run_id=f'run{index}'
        snapshot_id=f'snapshot{index}'
        at=f'{day}T07:30:05+10:00'
        static_id='static-gtfs'
        realtime_id=f'realtime-{index}'
        sources=[]
        for source_id,kind,feed,received,development in (
            (static_id,'gtfs','GTFS','2026-10-18T01:00:00+00:00',False),
            (realtime_id,'gtfs_rt','TripUpdates',f'{day}T07:20:00+10:00',False),
        ):
            payload=f'{feed}-{source_id}'.encode()
            object_path=f'raw/objects/{source_id}.bin'
            (root/object_path).parent.mkdir(parents=True,exist_ok=True)
            (root/object_path).write_bytes(payload)
            receipt={'record_id':source_id,'feed':feed,'received_at':received,'sha256':f'{index}{len(source_id):063x}',
                     'gtfs_sha256':'g'*64,'source_url':'https://example.invalid/source','object_path':object_path,
                     'status':'valid','details':json.dumps({'development_capture':development})}
            archive.receipts[source_id]=receipt
            sources.append({'record_id':source_id,'source_kind':kind,'received_at':received,'sha256':receipt['sha256'],
                            'source_ref':receipt['source_url']})
        snapshot={'metadata':{'snapshot_id':snapshot_id,'snapshot_at':at,'service_date':day,'sources':sources},
                  'walking_links':[]}
        inp={'snapshot_id':snapshot_id,'snapshot_at':at,'source_gtfs_sha256':'g'*64,'source_osm_sha256':'o'*64,
             'source_record_ids':[static_id,realtime_id],'derived_input':None}
        run={'run_id':run_id,'status':'completed','snapshot_id':snapshot_id,
             'metadata':{'input_sha256':'i'*64},'result':{'synthetic':True}}
        archive.verified[run_id]=(run,inp)
        write(root/'processed'/'snapshots'/f'{snapshot_id}.json',snapshot)
        write(root/'processed'/'run-results'/f'{run_id}.json',run)
        write(root/'processed'/'run-inputs'/f'{run_id}.input.json',inp)
        write(root/'processed'/'run-inputs'/f'{run_id}.metadata.json',run['metadata'])
    archive.get=lambda record_id:archive.receipts.get(record_id)
    def verified_run(ar,rid):
        if rid not in ar.verified:raise FileNotFoundError(rid)
        return ar.verified[rid]
    monkeypatch.setattr(reproduction,'verify_run',verified_run)
    monkeypatch.setattr(coverage,'release_gate',lambda ar:{'passed':False,'gates':{
        'five_complete_windows':True,'three_real_morning_bundles':True,'licences':True}})
    monkeypatch.setattr(evidence,'release_evidence',lambda:{'public_bundle_service_dates':list(DATES)})
    return archive


def test_public_candidate_preflights_and_packs_three_real_morning_dates(public_candidate,tmp_path):
    out=tmp_path/'candidate'
    result=reproduction.pack(public_candidate,out,['run0','run1','run2'],public_candidate=True)
    manifest=json.loads((out/'manifest.json').read_bytes())
    assert manifest['private_only'] is False
    assert manifest['candidate_preparation_only'] is True
    assert manifest['run_ids']==['run0','run1','run2']
    assert result['files']==len(manifest['files'])
    assert (out/'processed/run-results/run0.json').read_bytes()==(public_candidate.root/'processed/run-results/run0.json').read_bytes()


@pytest.mark.parametrize(('ids','message'),[
    ([], 'non-empty run ids'),
    (['run0','run0'], 'Duplicate public reproduction run id'),
])
def test_public_candidate_rejects_empty_or_duplicate_reviewed_run_ids(public_candidate,tmp_path,ids,message):
    out=tmp_path/'candidate'
    with pytest.raises(ValueError,match=message):
        reproduction.pack(public_candidate,out,ids,public_candidate=True)
    assert not out.exists()


def test_public_candidate_rejects_pending_preparation_gate_before_writing(public_candidate,tmp_path,monkeypatch):
    monkeypatch.setattr(coverage,'release_gate',lambda ar:{'passed':False,'gates':{
        'five_complete_windows':True,'three_real_morning_bundles':True,'licences':False}})
    out=tmp_path/'candidate'
    with pytest.raises(ValueError,match='licences'):
        reproduction.pack(public_candidate,out,['run0','run1','run2'],public_candidate=True)
    assert not out.exists()


@pytest.mark.parametrize(('kind','message'),[
    ('wrong_date','outside a selected weekday morning'),
    ('nonmorning','outside a selected weekday morning'),
    ('weekend','outside a selected weekday morning'),
    ('development_capture','not eligible morning provenance'),
    ('realtime_wrong_date','not eligible morning provenance'),
    ('legacy_run','incomplete or legacy run'),
])
def test_public_candidate_rejects_ineligible_run_or_realtime_provenance(public_candidate,tmp_path,kind,message):
    run,inp=public_candidate.verified['run1']
    snapshot_path=public_candidate.root/'processed'/'snapshots'/'snapshot1.json'
    snapshot=json.loads(snapshot_path.read_bytes())
    if kind=='wrong_date':
        inp['snapshot_at']='2026-10-22T07:30:05+10:00'
        snapshot['metadata']['snapshot_at']=inp['snapshot_at']
        snapshot['metadata']['service_date']='2026-10-22'
    elif kind=='nonmorning':
        inp['snapshot_at']='2026-10-20T12:00:00+10:00'
        snapshot['metadata']['snapshot_at']=inp['snapshot_at']
    elif kind=='weekend':
        inp['snapshot_at']='2026-10-24T08:00:00+10:00'
        snapshot['metadata']['snapshot_at']=inp['snapshot_at']
        snapshot['metadata']['service_date']='2026-10-24'
    elif kind=='development_capture':
        receipt=public_candidate.receipts['realtime-1']
        receipt['details']=json.dumps({'development_capture':True})
    elif kind=='realtime_wrong_date':
        receipt=public_candidate.receipts['realtime-1']
        receipt['received_at']='2026-10-21T07:20:00+10:00'
    else:
        run.pop('metadata')
    write(snapshot_path,snapshot)
    out=tmp_path/'candidate'
    with pytest.raises(ValueError,match=message):
        reproduction.pack(public_candidate,out,['run0','run1','run2'],public_candidate=True)
    assert not out.exists()


def test_public_candidate_requires_each_of_the_three_selected_dates(public_candidate,tmp_path):
    out=tmp_path/'candidate'
    with pytest.raises(ValueError,match='missing a selected service date'):
        reproduction.pack(public_candidate,out,['run0','run1'],public_candidate=True)
    assert not out.exists()


def test_public_candidate_rejects_unknown_run_id_before_writing(public_candidate,tmp_path):
    out=tmp_path/'candidate'
    with pytest.raises(FileNotFoundError):
        reproduction.pack(public_candidate,out,['run0','run1','unknown'],public_candidate=True)
    assert not out.exists()


def test_private_pack_keeps_its_existing_unfiltered_path(public_candidate,tmp_path,monkeypatch):
    run,inp=public_candidate.verified['run0']
    inp['snapshot_at']='2026-10-19T12:00:00+10:00'
    snapshot_path=public_candidate.root/'processed'/'snapshots'/'snapshot0.json'
    snapshot=json.loads(snapshot_path.read_bytes())
    snapshot['metadata']['snapshot_at']=inp['snapshot_at']
    write(snapshot_path,snapshot)
    monkeypatch.setattr(coverage,'release_gate',lambda ar:(_ for _ in ()).throw(AssertionError('private pack called public gate')))
    out=tmp_path/'private'
    reproduction.pack(public_candidate,out,['run0'])
    manifest=json.loads((out/'manifest.json').read_bytes())
    assert manifest['private_only'] is True and manifest['candidate_preparation_only'] is False
