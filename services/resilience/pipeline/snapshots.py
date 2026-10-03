from __future__ import annotations
import hashlib
from functools import lru_cache
import json
from pathlib import Path
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
import duckdb
import pandas as pd
from google.transit import gtfs_realtime_pb2
from ..contracts import Connection, QualityMetadata, SnapshotMetadata, SourceRecord, Stop, TimetableSnapshot
from .schedule import Schedule
from .walking import build_walking
from .files import atomic_write

BRISBANE=ZoneInfo("Australia/Brisbane")

def source_record(receipt):
    return SourceRecord(record_id=receipt["record_id"],source_kind="gtfs" if receipt["feed"]=="GTFS" else "osm" if receipt["feed"]=="OSM" else "gtfs_rt",received_at=datetime.fromisoformat(receipt["received_at"]),event_at=datetime.fromisoformat(receipt["event_at"]) if receipt["event_at"] else None,sha256=receipt["sha256"],source_ref=receipt["source_url"])

def realtime_updates(archive,receipt,as_of,day,trip_meta,stop_times):
    updates={}; diagnostics={"entities":[],"matched":0,"unmatched":0,"stale":0,"quarantined":0}
    if not receipt:return updates,diagnostics
    message=gtfs_realtime_pb2.FeedMessage.FromString(archive.read(receipt))
    sequences={tid:{int(r.stop_sequence):r.stop_id for r in group.itertuples()} for tid,group in stop_times.groupby("trip_id")}
    for entity in message.entity:
        if not entity.HasField("trip_update"):continue
        update=entity.trip_update;trip=update.trip;tid=trip.trip_id
        stamp=update.timestamp
        header_at=datetime.fromtimestamp(message.header.timestamp,timezone.utc).isoformat() if message.header.timestamp else None
        event=datetime.fromtimestamp(stamp,timezone.utc) if stamp else None
        age=(as_of-event).total_seconds() if event else None
        matched=tid in trip_meta and (not trip.start_date or trip.start_date==day.strftime("%Y%m%d")) and (not trip.route_id or trip.route_id==trip_meta.get(tid,{}).get("route_id"))
        info={"entity_id":entity.id,"trip_id":tid,"route_id":trip_meta.get(tid,{}).get("route_id",trip.route_id),"mode":trip_meta.get(tid,{}).get("mode"),"matched":matched,"event_at":event.isoformat() if event else None,"feed_header_at":header_at,"freshness_basis":"entity_timestamp" if event else "unknown_entity_timestamp","age_seconds":age,"receipt_age_seconds":(as_of-datetime.fromisoformat(receipt["received_at"])).total_seconds(),"status":"unmatched"}
        diagnostics["matched" if matched else "unmatched"]+=1
        if not matched:diagnostics["entities"].append(info);continue
        if age is None or age<0 or age>120 or info["receipt_age_seconds"]>120:
            info["status"]="stale";diagnostics["stale"]+=1;diagnostics["entities"].append(info);continue
        valid=True
        for stu in update.stop_time_update:
            if stu.HasField("stop_sequence") and stu.stop_sequence not in sequences[tid]:valid=False
            if stu.stop_id and stu.stop_id not in set(sequences[tid].values()):valid=False
            if stu.HasField("stop_sequence") and stu.stop_id and sequences[tid].get(stu.stop_sequence)!=stu.stop_id:valid=False
        if not valid:
            info["status"]="quarantined";diagnostics["quarantined"]+=1;diagnostics["entities"].append(info);continue
        if trip.schedule_relationship not in (0,3):
            info["status"]="quarantined_unsupported_relationship";diagnostics["quarantined"]+=1;diagnostics["entities"].append(info);continue
        if tid not in updates or updates[tid].timestamp<update.timestamp:updates[tid]=update
        info["status"]="fresh";diagnostics["entities"].append(info)
    rows=pd.DataFrame(diagnostics["entities"])
    diagnostics["by_route_mode"]=(rows.groupby(["route_id","mode","status"],dropna=False).size().reset_index(name="entities").where(pd.notna(rows.groupby(["route_id","mode","status"],dropna=False).size().reset_index(name="entities")),None).to_dict("records") if not rows.empty else [])
    return updates,diagnostics

def build_snapshot(archive,as_of,*,store=True,include_realtime=True):
    if as_of.utcoffset() is None:raise ValueError("as_of requires timezone")
    as_of=as_of.astimezone(timezone.utc)
    schedule_receipt=archive.latest("GTFS",as_of)
    if not schedule_receipt:raise ValueError("No GTFS received before as_of; current download cannot reconstruct earlier history")
    schedule=Schedule(archive,schedule_receipt)
    day=as_of.astimezone(BRISBANE).date();midnight=datetime.combine(day,time(),BRISBANE)
    def epoch_s(value):return int((datetime.fromtimestamp(value,timezone.utc)-midnight).total_seconds())
    active=schedule.dated_trips(day);meta=active.set_index("trip_id").to_dict("index")
    modes=dict(zip(schedule.routes.route_id,schedule.routes.route_type.map({"2":"rail","3":"bus"})))
    for row in meta.values():row["mode"]=modes[row["route_id"]]
    retained=schedule.stop_times[schedule.stop_times.trip_id.isin(set(active.trip_id))]
    receipts=[schedule_receipt]
    rt={name:(archive.latest(name,as_of,schedule_receipt["sha256"]) if include_realtime else None) for name in ("TripUpdates","VehiclePositions","Alerts")}
    receipts.extend(row for row in rt.values() if row)
    updates,diagnostics=realtime_updates(archive,rt["TripUpdates"],as_of,day,meta,retained)
    connections=[];trip_errors=[];cancelled=[]
    schedule_age=(as_of-datetime.fromisoformat(schedule_receipt["received_at"])).total_seconds()
    warnings=[]
    if schedule_age>=86400:
        warnings.append("GTFS receipt is at least 24 hours old: schedule fallback unverified; RT excluded")
        updates={}
    for tid,group in retained.groupby("trip_id",sort=True):
        upd=updates.get(tid)
        if upd and upd.trip.schedule_relationship==3:cancelled.append(tid);continue
        byseq={};byid={}
        if upd:
            for stu in upd.stop_time_update:
                if stu.HasField("stop_sequence"):byseq[stu.stop_sequence]=stu
                elif stu.stop_id:byid[stu.stop_id]=stu
        previous_delay=int(upd.delay) if upd and upd.HasField("delay") else 0
        events=[]
        try:
            for item in group.itertuples():
                arrival=int(item.arrival_time_s);departure=int(item.departure_time_s)
                pickup=item.pickup_type!="1";dropoff=item.drop_off_type!="1"
                stu=byseq.get(int(item.stop_sequence),byid.get(item.stop_id))
                realtime=False
                if upd:
                    arrival+=previous_delay;departure+=previous_delay;realtime=True
                    if stu:
                        if stu.schedule_relationship==1:pickup=dropoff=False
                        if stu.schedule_relationship==2:
                            arrival=int(item.arrival_time_s);departure=int(item.departure_time_s);previous_delay=0;realtime=False
                        else:
                            if stu.HasField("arrival"):
                                if stu.arrival.HasField("time"):arrival=epoch_s(stu.arrival.time);previous_delay=arrival-int(item.arrival_time_s)
                                elif stu.arrival.HasField("delay"):previous_delay=stu.arrival.delay;arrival=int(item.arrival_time_s)+previous_delay
                                departure=int(item.departure_time_s)+previous_delay
                            if stu.HasField("departure"):
                                if stu.departure.HasField("time"):departure=epoch_s(stu.departure.time);previous_delay=departure-int(item.departure_time_s)
                                elif stu.departure.HasField("delay"):previous_delay=stu.departure.delay;departure=int(item.departure_time_s)+previous_delay
                if arrival<0 or departure<arrival:raise ValueError("invalid predicted event chronology")
                events.append((item.stop_id,arrival,departure,pickup,dropoff,realtime))
            trip_connections=[]
            for i,(a,b) in enumerate(zip(events,events[1:])):
                if b[1]<a[2]:raise ValueError("predicted inter-stop chronology invalid")
                trip_connections.append(Connection(connection_id=f"{day}:{tid}:{i}",trip_instance_id=f"{day}:{tid}",route_id=meta[tid]["route_id"],mode=meta[tid]["mode"],sequence=i,from_stop_id=a[0],to_stop_id=b[0],departure_s=a[2],arrival_s=b[1],pickup_allowed=a[3],drop_off_allowed=b[4],provenance="realtime" if a[5] or b[5] else "scheduled"))
            connections.extend(trip_connections)
        except ValueError as exc:
            # Reject bad entity prediction while preserving complete scheduled trip.
            trip_errors.append({"trip_id":tid,"reason":str(exc),"action":"whole trip scheduled fallback"})
            for i,(a,b) in enumerate(zip(list(group.itertuples()),list(group.itertuples())[1:])):
                connections.append(Connection(connection_id=f"{day}:{tid}:{i}",trip_instance_id=f"{day}:{tid}",route_id=meta[tid]["route_id"],mode=meta[tid]["mode"],sequence=i,from_stop_id=a.stop_id,to_stop_id=b.stop_id,departure_s=int(a.departure_time_s),arrival_s=int(b.arrival_time_s),pickup_allowed=a.pickup_type!="1",drop_off_allowed=b.drop_off_type!="1"))
    stopids=set(schedule.stop_times.stop_id)|set(schedule.pilot["platform_seed_stop_ids"])|set(schedule.pilot["bus_seed_stop_ids"])
    stops=tuple(Stop(stop_id=r.stop_id,name=r.stop_name,latitude=float(r.stop_lat),longitude=float(r.stop_lon)) for r in schedule.stops[schedule.stops.stop_id.isin(stopids)].itertuples())
    links,walking_diag,osm=build_walking(archive,stops,as_of)
    if osm:receipts.append(osm)
    patterns,pairs=schedule.patterns(day)
    pairs=tuple(pair for pair in pairs if all(s.stop_id in stopids for p in (pair.outbound,pair.inbound) for s in p.stops))
    tu=rt["TripUpdates"];age=max(0,int((as_of-datetime.fromisoformat(tu["received_at"])).total_seconds())) if tu else None
    if not tu:status="missing"
    elif age>120 or not updates:status="stale"
    elif diagnostics["stale"] or diagnostics["quarantined"] or trip_errors:status="degraded"
    else:status="fresh"
    warnings.extend(["Predicted feed times are not measured arrivals", "Scheduled fallback applies to unmatched, missing or stale trip entities", "Walking coverage incomplete; unavailable platform paths cannot be inferred", "Development afternoon capture; no complete morning is claimed"])
    quality=QualityMetadata(realtime_status=status,schedule_status="verified" if schedule_age<86400 else "unverified",walking_status="incomplete" if osm else "missing",realtime_age_seconds=age,source_event_age_seconds=int((as_of-datetime.fromisoformat(tu["event_at"])).total_seconds()) if tu and tu["event_at"] else None,warnings=tuple(warnings))
    method_digest=hashlib.sha256(b"pipeline-v2"+b"".join(Path(p).read_bytes() for p in (Path(__file__),Path(__file__).with_name("walking.py"),Path(__file__).with_name("schedule.py"),Path(__file__).parents[1]/"contracts.py",Path("configs/pilot.json")))).hexdigest()
    sid=hashlib.sha256((as_of.isoformat()+"|"+"|".join(sorted(r["record_id"] for r in receipts))+"|pilot-v1|"+str(include_realtime)+"|"+method_digest).encode()).hexdigest()[:24]
    snapshot=TimetableSnapshot(metadata=SnapshotMetadata(snapshot_id=sid,snapshot_at=as_of,service_date=day,sources=tuple(source_record(r) for r in receipts),quality=quality),stops=stops,connections=tuple(connections),walking_links=links,recovery_pairs=pairs)
    out=archive.root/"processed"/"snapshots";out.mkdir(parents=True,exist_ok=True)
    path=out/f"{sid}.json"
    atomic_write(path,snapshot.model_dump_json(),immutable=True)
    diagnostics.update({"snapshot_id":sid,"as_of":as_of.isoformat(),"cancelled_trip_ids":cancelled,"prediction_errors":trip_errors,"walking":walking_diag,"schedule_age_seconds":schedule_age})
    (out/f"{sid}.quality.json").write_text(json.dumps(diagnostics,indent=2))
    # Columnar movement dataset and actual DuckDB analytical views.
    table=pd.DataFrame([c.model_dump() for c in connections]);table.to_parquet(out/f"{sid}.parquet",index=False)
    with duckdb.connect(str(archive.root/"runtime"/"analytics.duckdb")) as db:
        db.execute("CREATE OR REPLACE TABLE connections AS SELECT * FROM read_parquet(?)",[str(out/f"{sid}.parquet")])
        summary=db.execute("SELECT route_id,mode,provenance,count(*) AS connections,count(DISTINCT trip_instance_id) AS trips FROM connections GROUP BY ALL ORDER BY route_id,provenance").fetchdf().to_dict("records")
    (out/f"{sid}.analytics.json").write_text(json.dumps(summary,indent=2))
    if store:
        from ..db import persist_snapshot
        persist_snapshot(snapshot)
    return snapshot

def load_snapshot(archive,snapshot_id):
    if not snapshot_id.isalnum():raise KeyError(snapshot_id)
    path=archive.root/"processed"/"snapshots"/f"{snapshot_id}.json"
    if not path.exists():raise KeyError(snapshot_id)
    return _cached_snapshot(str(path.resolve()))

@lru_cache(maxsize=3)
def _cached_snapshot(path):
    return TimetableSnapshot.model_validate_json(Path(path).read_text())

def snapshot_index(archive):
    root=archive.root/"processed"/"snapshots"
    result=[]
    for path in sorted(root.glob("*.json")):
        if "." in path.stem:continue
        doc=json.loads(path.read_text());m=doc["metadata"]
        result.append({**{k:m[k] for k in ("snapshot_id","snapshot_at","service_date","quality")},"url":f"snapshots/{m['snapshot_id']}.json"})
    return result
