import json
import pandas as pd
from .archive import utcnow
from .schedule import Schedule,read_table,PARENTS

def network(archive,snapshot_id=None):
    if snapshot_id:
        from .snapshots import load_snapshot
        snapshot=load_snapshot(archive,snapshot_id)
        source=next(s for s in snapshot.metadata.sources if s.source_kind=="gtfs")
        receipt=archive.get(source.record_id)
    else:receipt=archive.latest("GTFS",utcnow())
    cache=archive.root/"processed"/("network-v2-"+receipt["sha256"]+".geojson") if receipt else archive.root/"processed"/"network-missing.geojson"
    if not receipt:return {"type":"FeatureCollection","features":[]}
    marker=cache.with_suffix(".sha256")
    if cache.exists() and marker.exists() and marker.read_text()==receipt["sha256"]:return json.loads(cache.read_text())
    schedule=Schedule(archive,receipt)
    ids=set(schedule.stop_times.stop_id)|set(PARENTS)
    features=[]
    for row in schedule.stops[schedule.stops.stop_id.isin(ids)].itertuples():
        props={"kind":"station" if row.stop_id in PARENTS else "stop","stop_id":row.stop_id,"name":row.stop_name,"parent_station":row.parent_station,"pilot":-27.523<=float(row.stop_lat)<=-27.452 and 153.006<=float(row.stop_lon)<=153.047}
        if row.stop_id in PARENTS:props["platform_ids"]=list(schedule.stops[schedule.stops.parent_station==row.stop_id].stop_id)
        features.append({"type":"Feature","id":row.stop_id,"properties":props,"geometry":{"type":"Point","coordinates":[float(row.stop_lon),float(row.stop_lat)]}})
    shape_routes=schedule.trips[["shape_id","route_id"]].drop_duplicates()
    selected=set(shape_routes.shape_id)
    chunks=[]
    for chunk in pd.read_csv(schedule.z.open("shapes.txt"),dtype=str,keep_default_na=False,chunksize=250000):chunks.append(chunk[chunk.shape_id.isin(selected)])
    shapes=pd.concat(chunks,ignore_index=True);shapes.shape_pt_sequence=shapes.shape_pt_sequence.astype(int)
    shapes=shapes.sort_values(["shape_id","shape_pt_sequence"])
    route_meta=schedule.routes.set_index("route_id").to_dict("index")
    for sid,group in shapes.groupby("shape_id",sort=True):
        for route_id in shape_routes[shape_routes.shape_id==sid].route_id:
            row=route_meta[route_id]
            features.append({"type":"Feature","id":f"shape:{sid}:{route_id}","properties":{"kind":"shape","shape_id":sid,"route_id":route_id,"route_short_name":row["route_short_name"],"name":row["route_long_name"],"mode":"rail" if row["route_type"]=="2" else "bus"},"geometry":{"type":"LineString","coordinates":[[float(r.shape_pt_lon),float(r.shape_pt_lat)] for r in group.itertuples()]}})
    result={"type":"FeatureCollection","features":features,"source":{"gtfs_sha256":receipt["sha256"],"source_record_id":receipt["record_id"],"derivation_version":"network-v2","received_at":receipt["received_at"],"licence":"CC BY 4.0","attribution":"Translink, Department of Transport and Main Roads, Queensland"}}
    cache.write_text(json.dumps(result));marker.write_text(receipt["sha256"])
    return result
