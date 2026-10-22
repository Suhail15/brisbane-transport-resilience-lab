"""Synthetic orchestration checks; no recorded inputs or real policy runs."""
from datetime import date, datetime
import json
from types import SimpleNamespace

import pytest

from resilience.contracts import Connection, Stop, SourceRecord, SnapshotMetadata, TimetableSnapshot
from resilience.pipeline.archive import Archive
from resilience.pipeline.analysis import canonical, digest
from resilience.pipeline import morning


@pytest.fixture
def config():
    return json.loads(morning.CONFIG.read_text())


def synthetic(day='2026-10-19'):
    metadata = SnapshotMetadata(snapshot_id='synthetic' + day.replace('-', ''), service_date=date.fromisoformat(day),
        snapshot_at=datetime.fromisoformat(day + 'T07:30:05+10:00'), sources=(SourceRecord(
            record_id='fixture', source_kind='gtfs', received_at=datetime.fromisoformat(day + 'T06:00:00+10:00'),
            sha256='a'*64, source_ref='https://example.invalid/synthetic'),))
    def connection(cid, mode, origin, destination, departure=27010):
        return Connection(connection_id=cid, trip_instance_id=cid, route_id='synthetic', mode=mode,
            sequence=0, from_stop_id=origin, to_stop_id=destination, departure_s=departure, arrival_s=departure+60)
    return TimetableSnapshot(metadata=metadata,
        stops=tuple(Stop(stop_id=s, latitude=-27.5, longitude=153) for s in ('3713','3692','600188','600016','other')),
        connections=(connection('z-bus','bus','3713','other'), connection('a-bus','bus','3692','other'),
            connection('past','bus','3713','other',26900), connection('rail-origin','rail','600188','other'),
            connection('rail-destination','rail','other','600016',27009)))


def test_source_targets_are_order_stable_and_use_existing_rail_or_rule(config):
    snapshot = synthetic()
    first = morning.target_manifest(snapshot, morning.DATES[0], config)
    reversed_input = snapshot.model_copy(update={'connections': tuple(reversed(snapshot.connections))})
    assert morning.target_manifest(reversed_input, morning.DATES[0], config) == first
    assert first['targets']['bus']['connection_id'] == 'a-bus'
    assert first['targets']['rail']['connection_id'] == 'rail-destination'
    assert first['targets']['closed_stop_id'] == '3713'
    assert tuple(first['scenarios']) == morning.SCENARIOS
    assert first['scenarios']['cancellation']['trip_instance_ids'] == ['a-bus']
    assert first['scenarios']['bus_delay']['additional_seconds'] == 1200


def test_fixed_dates_requests_and_missing_od_denominator(config):
    manifests = [morning.target_manifest(synthetic(day), day, config) for day in morning.DATES]
    for manifest in manifests:
        assert len(manifest['requests']) == 100
        assert all(request['od_weight'] is None for request in manifest['requests'])
        assert len({(r['origin_stop_id'],r['destination_stop_id']) for r in manifest['requests']}) == 20
        # Synthetic stops omit most real pilot OD stops; all requests must survive preparation.
        assert any(r['origin_stop_id'] not in {'3713','3692','600188','600016','other'} for r in manifest['requests'])
    assert all(m['requests'] == manifests[0]['requests'] for m in manifests)
    assert [m['date'] for m in manifests] == list(morning.DATES)


def test_unsupported_targets_preserve_nulls_and_halt_after_freezing_all_dates(tmp_path, config, monkeypatch):
    archive = Archive(tmp_path)
    def load(archive, sid):
        snapshot = synthetic(sid)
        return snapshot.model_copy(update={'connections': (), 'stops': ()})
    monkeypatch.setattr(morning, 'load_snapshot', load)
    for day in morning.DATES:
        path=tmp_path/'processed/snapshots'/f"synthetic{day.replace('-', '')}.json"
        path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(canonical(synthetic(day)))
    plan={'decision_snapshots': {day:day for day in morning.DATES}}
    with pytest.raises(morning.UnsupportedTarget):
        morning.prepare_manifests(archive, plan, config)
    for day in morning.DATES:
        evidence=json.loads((tmp_path/'processed/morning-evaluation-v1/targets'/f'{day}.json').read_text())
        assert evidence['status']=='unsupported_target'
        assert all(value is None for value in evidence['targets'].values())
        assert all(value is None for value in evidence['scenarios'].values())
        assert len(evidence['requests'])==100


def test_plan_rejects_reserve_substitution_even_with_better_result(tmp_path, config):
    path=tmp_path/'manifest.json'
    path.write_text(json.dumps({'decision_snapshots': {d:d for d in morning.DATES}, 'results': {'2026-10-22': 'best'}}))
    assert set(morning.read_plan(path,config)['decision_snapshots'])==set(morning.DATES)
    path.write_text(json.dumps({'decision_snapshots': {'2026-10-19':'a','2026-10-20':'b','2026-10-22':'best'}}))
    with pytest.raises(ValueError,match='exactly the three fixed'):
        morning.read_plan(path,config)
    with pytest.raises(ValueError,match='fixed local decision cutoff'):
        morning.target_manifest(synthetic('2026-10-22'),morning.DATES[0],config)


def test_matrix_has_16_nominal_and_two_paired_sensitivity_runs(config):
    manifest=morning.target_manifest(synthetic(),morning.DATES[0],config)
    runs=list(morning.experiment_payloads(manifest,config))
    assert len(runs)==18
    nominal=[(n,p) for n,p in runs if p['bus_running_time_sensitivity_seconds']==0]
    assert len(nominal)==16
    assert {n for n,p in nominal}==set(morning.SCENARIOS)
    assert all(p['max_swap_evaluations']==128 and p['requests']==manifest['requests'] for n,p in runs)
    paired=[p for n,p in runs if p['bus_running_time_sensitivity_seconds']]
    assert [p['bus_running_time_sensitivity_seconds'] for p in paired]==[300,600]
    assert all(p['budget_bus_hours']==2 and p['scenarios']==[manifest['scenarios']['stop_closure']] for p in paired)


def test_freezing_detects_snapshot_or_plan_changes(tmp_path,config,monkeypatch):
    archive=Archive(tmp_path)
    monkeypatch.setattr(morning,'load_snapshot',lambda archive,sid:synthetic(sid))
    for day in morning.DATES:
        path=tmp_path/'processed/snapshots'/f"synthetic{day.replace('-', '')}.json"
        path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(canonical(synthetic(day)))
    plan={'decision_snapshots':{day:day for day in morning.DATES}}
    morning.prepare_manifests(archive,plan,config)
    assert len(morning.prepare_manifests(archive,plan,config))==3
    with pytest.raises(ValueError,match='immutable file collision'):
        morning.prepare_manifests(archive,dict(plan,selection='post-result change'),config)


def test_expected_normalization_matches_api_and_sensitivity_keeps_candidates(tmp_path,config):
    archive=Archive(tmp_path); snapshot=synthetic()
    path=tmp_path/'processed/snapshots'/f'{snapshot.metadata.snapshot_id}.json'
    path.parent.mkdir(parents=True);path.write_bytes(canonical(snapshot))
    manifest=morning.target_manifest(snapshot,morning.DATES[0],config)
    paired=[p for n,p in morning.experiment_payloads(manifest,config,['stop_closure']) if p['budget_bus_hours']==2]
    inputs=[morning.expected_input(archive,p) for p in paired]
    assert [i['assumptions']['bus_running_time_sensitivity_seconds'] for i in inputs]==[0,300,600]
    assert all(i['candidates']==inputs[0]['candidates'] for i in inputs)
    assert all(len(i['requests'])==100 for i in inputs)
    assert inputs[0]['derived_input'] is None
    assert all(i['derived_input']['snapshot_content_sha256'] for i in inputs[1:])


def test_resume_verifies_full_input_id_and_hash():
    expected={'requests': ['synthetic'], 'budget_bus_hours': 2}
    run={'run_id':'fixture','input':expected,'metadata':{'input_sha256':digest(expected)}}
    morning.verify_run(run,expected,'fixture')
    for changed in (dict(run,run_id='different'),dict(run,input={}),dict(run,metadata={'input_sha256':'wrong'})):
        with pytest.raises(ValueError,match='resume input/ID/hash mismatch'):
            morning.verify_run(changed,expected,'fixture')


def test_failed_runs_save_evidence_and_do_not_resubmit(tmp_path,config,monkeypatch):
    archive=Archive(tmp_path)
    manifests={day:morning.target_manifest(synthetic(day),day,config) for day in morning.DATES}
    payload=next(morning.experiment_payloads(manifests[morning.DATES[0]],config,['cancellation']))[1]
    expected={'fixture':'exact'}
    monkeypatch.setattr(morning,'expected_input',lambda archive,p:expected)
    run={'run_id':'failedfixture','status':'failed','input':expected,
         'metadata':{'input_sha256':digest(expected)},'result':None,'error':'fixture failure'}
    posts=[]
    class Client:
        def post(self,url,json):
            posts.append(json); return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'run_id':'failedfixture'})
        def get(self,url):
            return SimpleNamespace(raise_for_status=lambda:None,json=lambda:run)
    with pytest.raises(RuntimeError,match='automatic retries disabled'):
        morning.execute(archive,manifests,config,Client(),'https://example.invalid/v1',dates=[morning.DATES[0]],scenarios=['cancellation'],poll_seconds=0)
    assert posts==[payload]
    with pytest.raises(RuntimeError,match='previous terminal failed'):
        morning.execute(archive,manifests,config,Client(),'https://example.invalid/v1',dates=[morning.DATES[0]],scenarios=['cancellation'],poll_seconds=0)
    assert len(posts)==1
    summary=json.loads((tmp_path/'processed/morning-evaluation-v1/summary.json').read_text())
    assert next(iter(summary.values()))['metrics'] is None


def test_completed_exact_archive_run_is_recovered_then_resumes_offline(tmp_path,config,monkeypatch):
    archive=Archive(tmp_path)
    manifests={day:morning.target_manifest(synthetic(day),day,config) for day in morning.DATES}
    payload=next(morning.experiment_payloads(manifests[morning.DATES[0]],config,['cancellation']))[1]
    monkeypatch.setattr(morning,'experiment_payloads',lambda *args: iter([('cancellation',payload)]))
    expected={'fixture':'exact-completed'}
    monkeypatch.setattr(morning,'expected_input',lambda archive,p:expected)
    result={'plan':{'evaluation':{'metrics':{'request_count':100,'restored_fraction':None}},'objective':None},
            'considered_candidate_ids':[]}
    run={'run_id':'completefixture','status':'completed','input':expected,
         'metadata':{'input_sha256':digest(expected)},'result':result,'error':None}
    path=tmp_path/'processed/experiments/completefixture.json'
    path.parent.mkdir(parents=True);path.write_bytes(canonical(run))
    gets=[]
    class Client:
        def post(self,*args,**kwargs):
            pytest.fail('exact existing run must never be resubmitted')
        def get(self,url):
            gets.append(url)
            return SimpleNamespace(raise_for_status=lambda:None,json=lambda:run)
    summary=morning.execute(archive,manifests,config,Client(),'https://example.invalid/v1',dates=[morning.DATES[0]])
    assert len(gets)==1
    row=next(iter(summary.values()))
    assert row['metrics']['restored_fraction'] is None and row['request_count']==100
    # Immutable completed result can reconstruct the summary without an active API.
    class Offline:
        def get(self,*args,**kwargs):pytest.fail('completed resume must not need HTTP')
        def post(self,*args,**kwargs):pytest.fail('completed resume must not submit')
    assert morning.execute(archive,manifests,config,Offline(),'https://example.invalid/v1',dates=[morning.DATES[0]])==summary
