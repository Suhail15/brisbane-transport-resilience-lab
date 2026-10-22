import hashlib
import gzip
import json
from pathlib import Path
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo
from .coverage import release_gate
from .network import network
from .snapshots import snapshot_index,load_snapshot,is_weekday_morning_capture
from .display import display_frame,choices
from .files import atomic_write

ZONE=ZoneInfo("Australia/Brisbane")

def capture_label(snapshots,*,public=False):
    if public:return "Three real recorded mornings"
    if snapshots and all(is_weekday_morning_capture(datetime.fromisoformat(item["snapshot_at"])) for item in snapshots):
        return "Recorded morning inputs; private preview"
    return "Recorded source inputs; private preview"

def export_bundle(archive,output,*,public=False,compact=True,candidate=False,snapshot_ids=None):
    gate=release_gate(archive)
    if candidate and not public:raise ValueError('Public candidate projection requires public=True')
    preparation_gates=('five_complete_windows','three_real_morning_bundles','licences')
    blocked=[name for name in preparation_gates if not gate['gates'][name]] if candidate else gate['blocking']
    if public and blocked:raise ValueError("Public bundle blocked: "+", ".join(blocked))
    root=Path(output)
    if root.exists() and any(root.iterdir()):
        # Avoid stale files from an earlier private/full export entering public output.
        if public:raise ValueError("Public export requires a new empty output directory")
    root.mkdir(parents=True,exist_ok=True)
    for folder in ("snapshots","experiments","networks","run-inputs"):(root/folder).mkdir(exist_ok=True)
    snapshots=snapshot_index(archive)
    requested_ids=None
    if snapshot_ids is not None:
        if isinstance(snapshot_ids,(str,bytes)):raise ValueError("Snapshot ids must be an iterable of ids")
        requested_ids=tuple(snapshot_ids)
        if any(not isinstance(sid,str) or not sid for sid in requested_ids):raise ValueError("Snapshot ids must be non-empty strings")
        if len(requested_ids)!=len(set(requested_ids)):raise ValueError("Duplicate requested snapshot id")
        indexed_ids={item["snapshot_id"] for item in snapshots}
        unknown=set(requested_ids)-indexed_ids
        if unknown:raise ValueError("Unknown snapshot id(s): "+", ".join(sorted(unknown)))
        requested_set=set(requested_ids)
        snapshots=[item for item in snapshots if item["snapshot_id"] in requested_set]
    if public:
        from .evidence import release_evidence
        selected=set(release_evidence()["public_bundle_service_dates"])
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
        if requested_ids is not None:
            survived={item["snapshot_id"] for item in snapshots}
            rejected=set(requested_ids)-survived
            if rejected:raise ValueError("Requested snapshot id(s) failed public morning eligibility: "+", ".join(sorted(rejected)))
        if {i["service_date"] for i in snapshots}!=selected:raise ValueError("Missing eligible snapshot for selected public morning")
    compact=compact or public
    network_json_by_digest={}
    for item in snapshots:
        sid=item["snapshot_id"]
        selected_snapshot=load_snapshot(archive,sid)
        gtfs=next(source for source in selected_snapshot.metadata.sources if source.source_kind=="gtfs")
        item["network_url"]=f"networks/{gtfs.sha256}.geojson"+(".gz" if compact else "")
        if gtfs.sha256 not in network_json_by_digest:
            network_bytes=json.dumps(network(archive,sid),separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")
            network_json_by_digest[gtfs.sha256]=network_bytes
            atomic_write(root/item["network_url"],gzip.compress(network_bytes,mtime=0) if compact else network_bytes)
            if compact and (root/f"networks/{gtfs.sha256}.geojson").exists():(root/f"networks/{gtfs.sha256}.geojson").unlink()
        item["display_url"]=f"snapshots/{sid}.display.json";item["choices_url"]=f"snapshots/{sid}.choices.json"
        atomic_write(root/item["display_url"],json.dumps(display_frame(archive,sid)))
        atomic_write(root/item["choices_url"],json.dumps(choices(archive,sid)))
        if compact:
            # Header is a display DTO, explicitly not an engine timetable.
            atomic_write(root/item["url"],json.dumps({"metadata":load_snapshot(archive,sid).metadata.model_dump(mode="json"),"compact_display_only":True,"display_url":item["display_url"],"choices_url":item["choices_url"]}))
        else:atomic_write(root/item["url"],(archive.root/"processed"/item["url"]).read_bytes())
    catalog={"version":1,"timezone":"Australia/Brisbane","preview_only":not public,"compact":compact,"candidate_preparation_only":candidate,"publication_authorized":public and not candidate and gate["passed"],"pilot":json.loads(Path("configs/pilot.json").read_text()),"snapshots":snapshots,"source_summary":{"attribution":"Translink / Department of Transport and Main Roads (CC BY 4.0); OpenStreetMap contributors (ODbL 1.0)","capture_label":capture_label(snapshots,public=public),"hypothetical_outputs":True},"release_gate":gate}
    if snapshots:catalog["network_url"]=snapshots[-1]["network_url"]
    atomic_write(root/"catalog.json",json.dumps(catalog))
    if not compact:
        from .archive import utcnow
        latest=archive.latest("GTFS",utcnow())
        latest_digest=latest["sha256"] if latest else None
        latest_network=network_json_by_digest.get(latest_digest)
        if latest_network is None:
            latest_network=json.dumps(network(archive),separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")
        atomic_write(root/"network.geojson",latest_network)
    elif (root/"network.geojson").exists():(root/"network.geojson").unlink()
    atomic_write(root/"snapshots"/"index.json",json.dumps({"snapshots":snapshots}))
    eligible_ids={item["snapshot_id"] for item in snapshots};runs=[]
    from .integrity import recorded_runs,verify_run
    for run_id,run in recorded_runs(archive).items():
        final=(archive.root/"processed"/"run-results"/f"{run_id}.json").exists()
        normalized=None
        if final and run['status']=='completed':run,normalized=verify_run(archive,run_id,require_code=False)
        if run["status"]!="completed" or run["snapshot_id"] not in eligible_ids:continue
        legacy=not bool(run.get('metadata'))
        run.update(legacy_unversioned=legacy,reproducible=False)
        if public and legacy:continue
        if not legacy:
            if normalized is None:run,normalized=verify_run(archive,run_id,require_code=False)
            from .integrity import adapter_digest
            from .analysis import engine_digest
            run=dict(run,legacy_unversioned=False,reproducible=normalized['engine_code_sha256']==engine_digest() and normalized.get('adapter_code_sha256')==adapter_digest())
            if public and not run['reproducible']:raise ValueError("Matching run code unavailable")
            input_path=archive.root/"processed"/"run-inputs"/f"{run['run_id']}.input.json"
            metadata_path=input_path.with_name(f"{run['run_id']}.metadata.json")
            run["input_url"]=f"run-inputs/{input_path.name}"
            run["metadata_url"]=f"run-inputs/{metadata_path.name}"
            atomic_write(root/run["input_url"],input_path.read_bytes())
            atomic_write(root/run["metadata_url"],metadata_path.read_bytes())
        from .run_index import summary
        runs.append(summary(run,normalized if not legacy else None,load_snapshot(archive,run['snapshot_id'])))
        atomic_write(root/"experiments"/f"{run_id}.json",json.dumps(run))
    atomic_write(root/"experiments"/"index.json",json.dumps({"version":1,"runs":runs}))
    manifest={"version":1,"public":public,"candidate_preparation_only":candidate,"compact":compact,"files":{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file() and p.name!="manifest.json"}}
    atomic_write(root/"manifest.json",json.dumps(manifest,indent=2))
    return {"root":str(root),"snapshots":len(snapshots),"completed_runs":len(runs),"public":public,"compact":compact}
