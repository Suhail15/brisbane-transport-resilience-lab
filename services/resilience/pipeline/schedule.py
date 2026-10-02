"""Calendar-aware GTFS pilot adapter. Route selection never clips retained trips."""
from __future__ import annotations
import hashlib
import io
import json
import zipfile
from datetime import date
from pathlib import Path
import pandas as pd
from ..contracts import BusPattern, PatternPair, PatternStop

PARENTS = ("place_faista", "place_sbasta", "place_censta", "place_romsta")

def seconds(value):
    h,m,s = map(int,value.split(":")); return h*3600+m*60+s

def read_table(z, name):
    try: return pd.read_csv(z.open(name),dtype=str,keep_default_na=False)
    except KeyError: return pd.DataFrame()

class Schedule:
    def __init__(self, archive, receipt, *, lock_path=Path("configs/pilot.json")):
        self.receipt = receipt
        self.z = zipfile.ZipFile(io.BytesIO(archive.read(receipt)))
        self.stops = read_table(self.z,"stops.txt")
        self.routes = read_table(self.z,"routes.txt")
        self.trips = read_table(self.z,"trips.txt")
        self.calendar = read_table(self.z,"calendar.txt")
        self.exceptions = read_table(self.z,"calendar_dates.txt")
        self.feed_info = read_table(self.z,"feed_info.txt")
        self.cache = archive.root / "processed" / receipt["sha256"]
        self.cache.mkdir(parents=True,exist_ok=True)
        if lock_path.exists():
            self.pilot = json.loads(lock_path.read_text())
        else:
            self.pilot = self.resolve_pilot()
            lock_path.parent.mkdir(parents=True,exist_ok=True)
            lock_path.write_text(json.dumps(self.pilot,indent=2))
        # Select all versions with the locked public line names; GTFS route ids change.
        selected = self.routes[self.routes.route_short_name.isin(self.pilot["route_short_names"]) & self.routes.route_type.isin(["2","3"])]
        self.routes = selected
        self.trips = self.trips[self.trips.route_id.isin(selected.route_id)]
        st_path = self.cache / "stop_times.parquet"
        if not st_path.exists():
            pieces = [chunk[chunk.trip_id.isin(set(self.trips.trip_id))] for chunk in pd.read_csv(self.z.open("stop_times.txt"),dtype=str,keep_default_na=False,chunksize=250000)]
            pd.concat(pieces,ignore_index=True).to_parquet(st_path,index=False)
        self.stop_times = pd.read_parquet(st_path)
        for field in ("arrival_time","departure_time"):
            self.stop_times[field+"_s"] = self.stop_times[field].map(seconds)
        self.stop_times["stop_sequence"] = self.stop_times.stop_sequence.astype(int)
        self.stop_times = self.stop_times.sort_values(["trip_id","stop_sequence"])
    def resolve_pilot(self):
        stops = self.stops
        lat = stops.stop_lat.astype(float); lon=stops.stop_lon.astype(float)
        # Origin corridor only seeds route discovery, never clips route movements.
        bus_seed = set(stops[(lat.between(-27.522,-27.500)) & lon.between(153.013,153.040) & (stops.location_type != "1")].stop_id)
        platform_seed = set(stops[stops.parent_station.isin(PARENTS)].stop_id)
        bus_types = set(self.routes[self.routes.route_type=="3"].route_id)
        rail_types = set(self.routes[self.routes.route_type=="2"].route_id)
        touching_bus, touching_rail = set(), set()
        for chunk in pd.read_csv(self.z.open("stop_times.txt"),dtype=str,keep_default_na=False,chunksize=250000,usecols=["trip_id","stop_id"]):
            touching_bus.update(chunk[chunk.stop_id.isin(bus_seed)].trip_id)
            touching_rail.update(chunk[chunk.stop_id.isin(platform_seed)].trip_id)
        bus_routes = set(self.trips[self.trips.trip_id.isin(touching_bus) & self.trips.route_id.isin(bus_types)].route_id)
        rail_routes = set(self.trips[self.trips.trip_id.isin(touching_rail) & self.trips.route_id.isin(rail_types)].route_id)
        selected = self.routes[self.routes.route_id.isin(bus_routes|rail_routes)]
        return {"version":1,"locked_from_gtfs_sha256":self.receipt["sha256"],"parents":PARENTS,"route_short_names":sorted(set(selected.route_short_name)),"initial_route_ids":sorted(selected.route_id),"bus_seed_stop_ids":sorted(bus_seed),"platform_seed_stop_ids":sorted(platform_seed),"selection_rule":"All bus lines serving origin Fairfield/Annerley rectangle and all rail lines serving four pilot station platforms; preserve complete trips across entire line","max_walk_m":600,"walking_speed_m_s":1.2,"transfer_slack_s":300,"max_transfers":3}
    def active_services(self, day: date):
        stamp = day.strftime("%Y%m%d"); weekday = day.strftime("%A").lower()
        active = set()
        if not self.calendar.empty:
            active = set(self.calendar[(self.calendar.start_date<=stamp)&(self.calendar.end_date>=stamp)&(self.calendar[weekday]=="1")].service_id)
        if not self.exceptions.empty:
            for row in self.exceptions[self.exceptions.date==stamp].itertuples():
                if row.exception_type=="1": active.add(row.service_id)
                elif row.exception_type=="2": active.discard(row.service_id)
        return active
    def dated_trips(self, day):
        return self.trips[self.trips.service_id.isin(self.active_services(day))]
    def patterns(self, day):
        trips = self.dated_trips(day)
        bus_ids = set(self.routes[self.routes.route_type=="3"].route_id)
        metadata = trips.set_index("trip_id").to_dict("index")
        grouped = {}
        for trip_id, group in self.stop_times[self.stop_times.trip_id.isin(set(trips[trips.route_id.isin(bus_ids)].trip_id))].groupby("trip_id",sort=True):
            if len(group)<2: continue
            row=metadata[trip_id]; first=int(group.iloc[0].departure_time_s)
            offsets = tuple((item.stop_id,max(0,int(item.arrival_time_s)-first),int(item.departure_time_s)-first,item.pickup_type!="1",item.drop_off_type!="1") for item in group.itertuples())
            key=(row["route_id"],row.get("direction_id",""),offsets)
            grouped.setdefault(key,[]).append(f"{day.isoformat()}:{trip_id}")
        patterns=[]
        for (route_id,direction,offsets),ids in sorted(grouped.items()):
            pid=hashlib.sha256(repr((route_id,direction,offsets)).encode()).hexdigest()[:20]
            patterns.append(BusPattern(pattern_id=pid,route_id=route_id,direction_id=direction or "unknown",source_trip_instance_ids=tuple(ids),stops=tuple(PatternStop(stop_id=s,arrival_offset_s=a,departure_offset_s=d,pickup_allowed=p,drop_off_allowed=q) for s,a,d,p,q in offsets)))
        pairs=[]; seen=set()
        for out in patterns:
            for inbound in patterns:
                if out.route_id!=inbound.route_id or out.direction_id==inbound.direction_id: continue
                if out.stops[-1].stop_id!=inbound.stops[0].stop_id or inbound.stops[-1].stop_id!=out.stops[0].stop_id: continue
                key=tuple(sorted((out.pattern_id,inbound.pattern_id)))
                if key in seen: continue
                seen.add(key)
                pairs.append(PatternPair(pair_id="pair:"+":".join(key),outbound=out,inbound=inbound))
        return patterns,pairs

def audit_pilot(archive):
    from .archive import utcnow
    receipt=archive.latest("GTFS",utcnow())
    if not receipt: raise ValueError("No acquired GTFS; run bootstrap or collect")
    schedule=Schedule(archive,receipt)
    day=utcnow().astimezone(__import__("zoneinfo").ZoneInfo("Australia/Brisbane")).date()
    patterns,pairs=schedule.patterns(day)
    report={"gtfs":receipt,"feed_info":schedule.feed_info.to_dict("records"),"pilot":schedule.pilot,"route_count":len(schedule.routes),"routes":schedule.routes.to_dict("records"),"all_feed_trip_count":len(read_table(schedule.z,"trips.txt")),"retained_feed_trip_count":len(schedule.trips),"retained_stop_time_count":len(schedule.stop_times),"service_date":day.isoformat(),"active_trip_count":len(schedule.dated_trips(day)),"bus_patterns":len(patterns),"exact_terminal_pairs":len(pairs),"platforms":schedule.stops[schedule.stops.parent_station.isin(PARENTS)].to_dict("records"),"source_kind":"sourced observation; counts are derived","limitations":["GTFS schedule is not observed vehicle operation","Development recording is afternoon, not a morning collection"]}
    (archive.root/"processed"/"audit.json").write_text(json.dumps(report,indent=2))
    return report
