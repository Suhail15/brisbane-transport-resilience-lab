from datetime import datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo
import json
from pathlib import Path

ZONE=ZoneInfo("Australia/Brisbane")

def coverage_report(archive):
    records=archive.records();days=sorted({datetime.fromisoformat(r["received_at"]).astimezone(ZONE).date() for r in records if r["feed"] in ("TripUpdates","VehiclePositions","Alerts")})
    windows=[]
    for day in days:
        if day.weekday()>=5:continue
        start=datetime.combine(day,time(6),ZONE);end=start+timedelta(hours=6)
        feeds={}
        for feed,cadence in (("TripUpdates",30),("VehiclePositions",30),("Alerts",60)):
            valid=[r for r in records if r["feed"]==feed and r["status"]=="valid" and start<=datetime.fromisoformat(r["received_at"])<end and not json.loads(r["details"]).get("development_capture",False)]
            stamps=sorted(datetime.fromisoformat(r["received_at"]) for r in valid)
            limit=cadence+5;gaps=[]
            if not stamps:gaps=[{"start":start.isoformat(),"end":end.isoformat(),"seconds":21600}]
            else:
                boundaries=[start,*stamps,end]
                for a,b in zip(boundaries,boundaries[1:]):
                    if (b-a).total_seconds()>limit:gaps.append({"start":a.isoformat(),"end":b.isoformat(),"seconds":round((b-a).total_seconds(),3)})
            feeds[feed]={"receipts":len(valid),"expected_nominal":21600//cadence,"max_allowed_gap_seconds":limit,"gaps":gaps,"complete":not gaps}
        windows.append({"service_date":day.isoformat(),"start":start.isoformat(),"end":end.isoformat(),"feeds":feeds,"complete":all(f["complete"] for f in feeds.values())})
    with archive.connect() as db:recorded_gaps=[dict(r) for r in db.execute("SELECT * FROM gaps ORDER BY started_at")]
    return {"timezone":"Australia/Brisbane","complete_weekday_windows":sum(w["complete"] for w in windows),"required_windows":5,"windows":windows,"recorded_failures":recorded_gaps,"definition":"Full six-hour receipt coverage for all three valid FULL_DATASET feeds; cadence +5 second maximum gap including window edges; excludes development captures","earliest_planned_complete_week":"2026-10-05 through 2026-10-09; future, not yet collected"}

def release_gate(archive):
    evidence_path=Path("configs/release-evidence.json")
    evidence=json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
    coverage=coverage_report(archive)
    gates={"five_complete_windows":coverage["complete_weekday_windows"]>=5}
    complete_dates={w["service_date"] for w in coverage["windows"] if w["complete"]}
    bundle_dates=set(evidence.get("public_bundle_service_dates",[]))
    gates["three_real_morning_bundles"]=len(bundle_dates)>=3 and bundle_dates<=complete_dates
    for name in ("independent_otp","performance","licences","secrets","ci","static_demo"):
        item=evidence.get(name,{})
        gates[name]=item.get("passed") is True and bool(item.get("evidence_ref"))
    return {"passed":all(gates.values()),"gates":gates,"blocking":[name for name,passed in gates.items() if not passed],"coverage":coverage,"public_release_authorized":False if not all(gates.values()) else True}
