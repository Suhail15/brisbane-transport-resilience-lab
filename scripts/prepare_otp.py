"""Create an independently routable GTFS subset, retaining full selected trips."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services"))
from resilience.settings import settings
from resilience.pipeline.archive import Archive,utcnow
from resilience.pipeline.schedule import Schedule,read_table

p=argparse.ArgumentParser();p.add_argument("--output",default="data/derived/otp");p.add_argument("--as-of",help="Aware archived cutoff; never replace an earlier timetable with the latest download");args=p.parse_args()
cutoff=datetime.fromisoformat(args.as_of) if args.as_of else utcnow()
if cutoff.utcoffset() is None:raise ValueError('as-of requires timezone')
archive=Archive(settings.data_dir);receipt=archive.latest("GTFS",cutoff)
if receipt is None:raise ValueError('No archived timetable available by cutoff')
schedule=Schedule(archive,receipt)
root=Path(args.output);root.mkdir(parents=True,exist_ok=True)
services=set(schedule.trips.service_id);stopids=set(schedule.stop_times.stop_id)
parents=set(schedule.stops[schedule.stops.stop_id.isin(stopids)].parent_station)-{""};stopids|=parents
shapeids=set(schedule.trips.shape_id)
with zipfile.ZipFile(root/"pilot.gtfs.zip","w",compression=zipfile.ZIP_DEFLATED) as out:
    for name in schedule.z.namelist():
        if name=="stop_times.txt":df=schedule.stop_times.drop(columns=["arrival_time_s","departure_time_s"])
        elif name=="trips.txt":df=schedule.trips
        elif name=="routes.txt":df=schedule.routes
        elif name=="stops.txt":df=schedule.stops[schedule.stops.stop_id.isin(stopids)]
        elif name=="calendar.txt":df=schedule.calendar[schedule.calendar.service_id.isin(services)]
        elif name=="calendar_dates.txt":df=schedule.exceptions[schedule.exceptions.service_id.isin(services)]
        elif name=="shapes.txt":
            import pandas as pd
            df=pd.concat([c[c.shape_id.isin(shapeids)] for c in pd.read_csv(schedule.z.open(name),dtype=str,keep_default_na=False,chunksize=250000)],ignore_index=True)
        elif name in ("transfers.txt","pathways.txt"):
            df=read_table(schedule.z,name)
            df=df[df.from_stop_id.isin(stopids)&df.to_stop_id.isin(stopids)]
        elif name=="frequencies.txt":
            df=read_table(schedule.z,name);df=df[df.trip_id.isin(set(schedule.trips.trip_id))]
        else:out.writestr(name,schedule.z.read(name));continue
        out.writestr(name,df.to_csv(index=False))
# Explicit routing defaults, independent engine, no live updaters/hindsight.
(root/"router-config.json").write_text(json.dumps({"routingDefaults":{"walk":{"speed":1.2},"transferSlack":"PT5M","boardSlack":"PT0S","alightSlack":"PT0S","ignoreRealtimeUpdates":True,"accessEgress":{"maxDuration":"PT500S"},"numItineraries":12}},indent=2))
(root/"build-config.json").write_text(json.dumps({"transit":True,"streetGraph":True,"osm":[{"source":"walking.osm.pbf","timeZone":"Australia/Brisbane"}],"transitFeeds":[{"type":"gtfs","feedId":"SEQ","source":"pilot.gtfs.zip"}]},indent=2))
(root/"otp-config.json").write_text(json.dumps({"otpFeatures":{"GtfsGraphQlApi":True}},indent=2))
manifest={"as_of":cutoff.isoformat(),"source_gtfs_sha256":receipt["sha256"],"source_record_id":receipt["record_id"],"trips":len(schedule.trips),"stop_times":len(schedule.stop_times),"full_trips_preserved":True,"otp_gtfs_sha256":hashlib.sha256((root/"pilot.gtfs.zip").read_bytes()).hexdigest(),"limitations":["OSM graph limited to pilot; outside source trips preserved for transit continuity","Independent comparisons use scheduled CSA baseline, not real-time predictions"]}
(root/"input-manifest.json").write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))
