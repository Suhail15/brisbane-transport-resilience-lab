"""Display-only recorded vehicles, alerts and gaps; never inferred arrivals."""
from datetime import datetime,timezone
import json
from google.transit import gtfs_realtime_pb2
from .snapshots import load_snapshot

def display_frame(archive,snapshot_id):
    snapshot=load_snapshot(archive,snapshot_id);as_of=snapshot.metadata.snapshot_at
    source_ids={s.record_id for s in snapshot.metadata.sources}
    receipts={r["feed"]:r for r in archive.records(as_of=as_of) if r["record_id"] in source_ids}
    trip_ids={c.trip_instance_id.split(":",1)[1]:{"trip_instance_id":c.trip_instance_id,"route_id":c.route_id,"mode":c.mode} for c in snapshot.connections}
    vehicles=[];alerts=[]
    position=receipts.get("VehiclePositions")
    if position:
        msg=gtfs_realtime_pb2.FeedMessage.FromString(archive.read(position))
        for entity in msg.entity:
            if not entity.HasField("vehicle") or not entity.vehicle.HasField("position"):continue
            vehicle=entity.vehicle;trip=vehicle.trip;matched=trip_ids.get(trip.trip_id)
            if matched and trip.start_date and trip.start_date!=snapshot.metadata.service_date.strftime("%Y%m%d"):matched=None
            if matched and trip.route_id and trip.route_id!=matched["route_id"]:matched=None
            event=datetime.fromtimestamp(vehicle.timestamp,timezone.utc) if vehicle.timestamp else None
            header_at=datetime.fromtimestamp(msg.header.timestamp,timezone.utc).isoformat() if msg.header.timestamp else None
            age=(as_of-event).total_seconds() if event else None
            receipt_age=(as_of-datetime.fromisoformat(position["received_at"])).total_seconds()
            lat=vehicle.position.latitude;lon=vehicle.position.longitude
            in_pilot=-27.523<=lat<=-27.452 and 153.006<=lon<=153.047
            if not matched and not in_pilot:continue
            vehicles.append({"entity_id":entity.id,"trip_id":trip.trip_id,"trip_instance_id":matched["trip_instance_id"] if matched else None,"route_id":matched["route_id"] if matched else trip.route_id or None,"mode":matched["mode"] if matched else None,"matched":bool(matched),"event_at":event.isoformat() if event else None,"feed_header_at":header_at,"freshness_basis":"entity_timestamp" if event else "unknown_entity_timestamp","received_at":position["received_at"],"source_event_age_seconds":age,"receipt_age_seconds":receipt_age,"quality":"fresh" if matched and age is not None and 0<=age<=120 and receipt_age<=120 else "unknown" if matched and age is None else "stale" if matched else "unmatched","longitude":lon,"latitude":lat,"bearing":vehicle.position.bearing if vehicle.position.HasField("bearing") else None,"source_record_id":position["record_id"],"feed_sha256":position["sha256"],"gtfs_sha256":position["gtfs_sha256"]})
    alert_receipt=receipts.get("Alerts")
    if alert_receipt:
        msg=gtfs_realtime_pb2.FeedMessage.FromString(archive.read(alert_receipt))
        route_ids={c.route_id for c in snapshot.connections};stop_ids={s.stop_id for s in snapshot.stops}
        for entity in msg.entity:
            if not entity.HasField("alert"):continue
            alert=entity.alert
            cutoff=as_of.timestamp()
            if alert.active_period and not any((not p.start or p.start<=cutoff) and (not p.end or cutoff<p.end) for p in alert.active_period):continue
            selectors=[{"route_id":s.route_id or None,"stop_id":s.stop_id or None,"trip_id":s.trip.trip_id if s.HasField("trip") else None} for s in alert.informed_entity]
            relevant=not selectors or any(s["route_id"] in route_ids or s["stop_id"] in stop_ids or s["trip_id"] in trip_ids or all(v is None for v in s.values()) for s in selectors)
            if not relevant:continue
            def translated(field):return next((t.text for t in field.translation if t.language in ("","en")),field.translation[0].text if field.translation else "")
            alerts.append({"entity_id":entity.id,"header":translated(alert.header_text),"description":translated(alert.description_text),"active_periods":[{"start":p.start or None,"end":p.end or None} for p in alert.active_period],"informed_entities":selectors,"cause":int(alert.cause),"effect":int(alert.effect),"received_at":alert_receipt["received_at"],"source_record_id":alert_receipt["record_id"],"feed_sha256":alert_receipt["sha256"],"gtfs_sha256":alert_receipt["gtfs_sha256"],"receipt_age_seconds":(as_of-datetime.fromisoformat(alert_receipt["received_at"])).total_seconds()})
    gaps=archive.known_gaps(as_of)
    for gap in gaps:
        if gap["ended_at"] and datetime.fromisoformat(gap["ended_at"])>as_of:gap["ended_at"]=as_of.isoformat()
    return {"snapshot_id":snapshot_id,"snapshot_at":as_of.isoformat(),"vehicles":vehicles,"alerts":alerts,"gaps":gaps,"quality":snapshot.metadata.quality.model_dump(mode="json"),"labels":{"positions":"Recorded source vehicle positions; entity timestamps and identifier joins determine quality","predictions":"No vehicle timestamp is treated as measured arrival","scenarios":"Hypothetical disruptions and recovery only"}}

def choices(archive,snapshot_id):
    snapshot=load_snapshot(archive,snapshot_id)
    from collections import Counter,defaultdict
    boardings=Counter(c.from_stop_id for c in snapshot.connections if c.pickup_allowed and c.departure_s>=snapshot.metadata.snapshot_s)
    trips=defaultdict(list);segments=defaultdict(set)
    for c in snapshot.connections:
        trips[c.trip_instance_id].append(c);segments[(c.from_stop_id,c.to_stop_id)].add(c.route_id)
    summaries=[]
    for tid,items in sorted(trips.items()):
        items.sort(key=lambda c:c.sequence);first,last=items[0],items[-1]
        summaries.append({"trip_instance_id":tid,"route_id":first.route_id,"mode":first.mode,"from_stop_id":first.from_stop_id,"to_stop_id":last.to_stop_id,"departure_s":first.departure_s,"arrival_s":last.arrival_s,"stop_ids":[first.from_stop_id,*[c.to_stop_id for c in items]]})
    return {"snapshot_id":snapshot_id,"snapshot_at":snapshot.metadata.snapshot_at.isoformat(),"service_date":snapshot.metadata.service_date.isoformat(),"snapshot_s":snapshot.metadata.snapshot_s,"quality":snapshot.metadata.quality.model_dump(mode="json"),"stops":[{**s.model_dump(),"active_boardings":boardings[s.stop_id]} for s in snapshot.stops],"trips":summaries,"segments":[{"from_stop_id":a,"to_stop_id":b,"route_ids":sorted(routes)} for (a,b),routes in sorted(segments.items())],"recovery_pair_ids":[p.pair_id for p in snapshot.recovery_pairs]}
