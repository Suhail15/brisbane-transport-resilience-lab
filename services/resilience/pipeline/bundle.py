import hashlib
import json
from pathlib import Path
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo
from .coverage import release_gate
from .network import network
from .snapshots import snapshot_index,load_snapshot
from .display import display_frame,choices
from .files import atomic_write

ZONE=ZoneInfo("Australia/Brisbane")

def export_bundle(archive,output,*,public=False,compact=True):
    gate=release_gate(archive)
    if public and not gate["passed"]:raise ValueError("Public bundle blocked: "+", ".join(gate["blocking"]))
    root=Path(output)
    if root.exists() and any(root.iterdir()):
        # Avoid stale files from an earlier private/full export entering public output.
        if public:raise ValueError("Public export requires a new empty output directory")
    root.mkdir(parents=True,exist_ok=True)
    for folder in ("snapshots","experiments","networks"):(root/folder).mkdir(exist_ok=True)
    snapshots=snapshot_index(archive)
    if public:
        selected=set(json.loads(Path("configs/release-evidence.json").read_text())["public_bundle_service_dates"])
        selected_snapshots=[]
        for item in snapshots:
            at=datetime.fromisoformat(item["snapshot_at"]).astimezone(ZONE)
            if item["service_date"] not in selected or not 6<=at.hour<12:continue
            snapshot=load_snapshot(archive,item["snapshot_id"])
            receipt_ids={r.record_id for r in snapshot.metadata.sources}
            receipts=[r for r in archive.records(as_of=snapshot.metadata.snapshot_at) if r["record_id"] in receipt_ids]
            for receipt in receipts:
                if receipt["feed"] in ("TripUpdates","VehiclePositions","Alerts"):
                    stamp=datetime.fromisoformat(receipt["received_at"]).astimezone(ZONE)
                    if stamp.date()!=at.date() or not 6<=stamp.hour<12 or json.loads(receipt["details"]).get("development_capture",False):raise ValueError("Ineligible public snapshot realtime provenance")
            selected_snapshots.append(item)
        snapshots=selected_snapshots
        if {i["service_date"] for i in snapshots}!=selected:raise ValueError("Missing eligible snapshot for selected public morning")
    compact=compact or public
    for item in snapshots:
        sid=item["snapshot_id"]
        selected_snapshot=load_snapshot(archive,sid)
        gtfs=next(source for source in selected_snapshot.metadata.sources if source.source_kind=="gtfs")
        item["network_url"]=f"networks/{gtfs.sha256}.geojson"
        if not (root/item["network_url"]).exists():atomic_write(root/item["network_url"],json.dumps(network(archive,sid)))
        item["display_url"]=f"snapshots/{sid}.display.json";item["choices_url"]=f"snapshots/{sid}.choices.json"
        atomic_write(root/item["display_url"],json.dumps(display_frame(archive,sid)))
        atomic_write(root/item["choices_url"],json.dumps(choices(archive,sid)))
        if compact:
            # Header is a display DTO, explicitly not an engine timetable.
            atomic_write(root/item["url"],json.dumps({"metadata":load_snapshot(archive,sid).metadata.model_dump(mode="json"),"compact_display_only":True,"display_url":item["display_url"],"choices_url":item["choices_url"]}))
        else:atomic_write(root/item["url"],(archive.root/"processed"/item["url"]).read_bytes())
    catalog={"version":1,"timezone":"Australia/Brisbane","preview_only":not public,"compact":compact,"pilot":json.loads(Path("configs/pilot.json").read_text()),"snapshots":snapshots,"source_summary":{"attribution":"Translink / Department of Transport and Main Roads (CC BY 4.0); OpenStreetMap contributors (ODbL 1.0)","capture_label":"Recorded development afternoon; not a complete morning" if not public else "Three real recorded mornings","hypothetical_outputs":True},"release_gate":gate}
    atomic_write(root/"catalog.json",json.dumps(catalog));atomic_write(root/"network.geojson",json.dumps(network(archive)))
    atomic_write(root/"snapshots"/"index.json",json.dumps({"snapshots":snapshots}))
    eligible_ids={item["snapshot_id"] for item in snapshots};runs=[]
    for path in (archive.root/"processed"/"experiments").glob("*.json"):
        run=json.loads(path.read_text())
        if run["status"]!="completed" or run["snapshot_id"] not in eligible_ids:continue
        runs.append({k:run[k] for k in ("run_id","status","progress","url")})
        atomic_write(root/"experiments"/path.name,json.dumps(run))
    atomic_write(root/"experiments"/"index.json",json.dumps({"runs":runs}))
    manifest={"version":1,"public":public,"compact":compact,"files":{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file() and p.name!="manifest.json"}}
    atomic_write(root/"manifest.json",json.dumps(manifest,indent=2))
    return {"root":str(root),"snapshots":len(snapshots),"completed_runs":len(runs),"public":public,"compact":compact}
