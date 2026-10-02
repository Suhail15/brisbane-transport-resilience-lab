from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone,date
import gzip
import io
import json
import zipfile
import pandas as pd
import pytest
from google.transit import gtfs_realtime_pb2
from resilience.pipeline.archive import Archive
from resilience.pipeline.coverage import coverage_report,release_gate
from resilience.pipeline.schedule import Schedule,seconds
from resilience.pipeline.snapshots import realtime_updates
from resilience.pipeline.files import atomic_write

def feed(timestamp=1000):
    msg=gtfs_realtime_pb2.FeedMessage();msg.header.gtfs_realtime_version='2.0';msg.header.timestamp=timestamp
    return msg

def test_receipt_cutoff_and_out_of_order_arrival(tmp_path):
    archive=Archive(tmp_path);at=datetime(2026,10,2,tzinfo=timezone.utc)
    old=archive.append('TripUpdates',feed(200).SerializeToString(),at,'https://example.invalid','a'*64)
    late=archive.append('TripUpdates',feed(100).SerializeToString(),at+timedelta(minutes=1),'https://example.invalid','a'*64)
    assert archive.latest('TripUpdates',at,'a'*64)['record_id']==old['record_id']
    assert archive.latest('TripUpdates',at+timedelta(minutes=1),'a'*64)['record_id']==late['record_id']
    assert archive.latest('TripUpdates',at,'b'*64) is None
    assert archive.read(old)==feed(200).SerializeToString()

def test_dedup_and_atomic_content_archive(tmp_path):
    archive=Archive(tmp_path);at=datetime.now(timezone.utc);payload=feed().SerializeToString()
    with ThreadPoolExecutor(max_workers=6) as pool:
        receipts=list(pool.map(lambda _:archive.append('Alerts',payload,at,'https://example.invalid'),range(20)))
    assert len(archive.records())==1
    assert len(list((tmp_path/'raw'/'objects').glob('*.gz')))==1
    assert all(archive.read(r)==payload for r in receipts)
    with pytest.raises(ValueError):atomic_write(tmp_path/'raw'/'immutable',b'a',immutable=True) if False else _collision(tmp_path)

def _collision(root):
    atomic_write(root/'immutable',b'a',immutable=True);atomic_write(root/'immutable',b'b',immutable=True)

def test_malformed_and_differential_quarantine(tmp_path):
    archive=Archive(tmp_path);at=datetime.now(timezone.utc)
    bad=archive.append('Alerts',b'notprotobuf',at,'https://example.invalid')
    msg=feed();msg.header.incrementality=1
    diff=archive.append('TripUpdates',msg.SerializeToString(),at,'https://example.invalid')
    assert bad['status']==diff['status']=='quarantined'
    assert archive.latest('Alerts',at) is None
    assert archive.read(bad)==b'notprotobuf'

def test_missing_entity_timestamp_never_fresh(tmp_path):
    archive=Archive(tmp_path);at=datetime(2026,10,2,4,tzinfo=timezone.utc)
    msg=feed(int(at.timestamp()));entity=msg.entity.add();entity.id='e';entity.trip_update.trip.trip_id='t';entity.trip_update.trip.start_date='20261002'
    receipt=archive.append('TripUpdates',msg.SerializeToString(),at,'https://example.invalid','a'*64)
    updates,diag=realtime_updates(archive,receipt,at,date(2026,10,2),{'t':{'route_id':'r','mode':'bus'}},pd.DataFrame([{'trip_id':'t','stop_sequence':1,'stop_id':'s'}]))
    assert updates=={}
    assert diag['entities'][0]['event_at'] is None
    assert diag['entities'][0]['freshness_basis']=='unknown_entity_timestamp'

def test_calendar_exceptions_override_weekly():
    schedule=object.__new__(Schedule)
    schedule.calendar=pd.DataFrame([{'service_id':'removed','monday':'1','start_date':'20261001','end_date':'20261031'}])
    schedule.exceptions=pd.DataFrame([{'service_id':'removed','date':'20261005','exception_type':'2'},{'service_id':'added','date':'20261005','exception_type':'1'}])
    assert schedule.active_services(date(2026,10,5))=={'added'}
    assert seconds('25:01:00')==90060

def test_development_afternoon_never_complete_morning(tmp_path):
    archive=Archive(tmp_path);at=datetime(2026,10,2,4,tzinfo=timezone.utc)
    for name in ('TripUpdates','VehiclePositions','Alerts'):archive.append(name,feed().SerializeToString(),at,'https://example.invalid',details={'development_capture':True})
    report=coverage_report(archive)
    assert report['complete_weekday_windows']==0
    assert all(len(feed['gaps'])==1 for feed in report['windows'][0]['feeds'].values())
    gate=release_gate(archive);assert not gate['passed'];assert 'five_complete_windows' in gate['blocking']

def test_later_detected_gap_cannot_change_earlier_replay(tmp_path,monkeypatch):
    import resilience.pipeline.archive as module
    archive=Archive(tmp_path);at=datetime(2026,10,2,4,tzinfo=timezone.utc)
    before=archive.known_gaps(at)
    monkeypatch.setattr(module,'utcnow',lambda:at+timedelta(minutes=5))
    archive.gap(at-timedelta(minutes=1),at+timedelta(minutes=4),'all','later detected sleep')
    assert archive.known_gaps(at)==before==[]
    assert len(archive.known_gaps(at+timedelta(minutes=5)))==1
