"""Monthly ticketing research proxy; never substitutes primary equal-weight requests."""
import io
import hashlib
import json
import zipfile
from datetime import datetime
import pandas as pd
import duckdb
from .archive import utcnow
from .schedule import Schedule

REQUIRED={"OPERATOR","MONTH","ROUTE","DIRECTION","TIME_GROUPING","TICKET_TYPE","ORIGIN_STOP","DESTINATION_STOP","QUANTITY"}

def audit_od(archive):
    path=archive.root/"bootstrap"/"202607-od.zip"
    if not path.exists():return {"status":"missing","used_in_primary_metrics":False}
    manifest=json.loads(path.with_suffix(path.suffix+".source.json").read_text())
    payload=path.read_bytes()
    if manifest.get("sha256") and hashlib.sha256(payload).hexdigest()!=manifest["sha256"]:raise ValueError("Monthly OD bootstrap hash mismatch")
    receipt=archive.append("MONTHLY_OD",payload,datetime.fromisoformat(manifest["received_at"]),manifest["url"],details={"licence":"CC BY 4.0","publisher":"Translink","coverage":"2026-07","kind":"aggregated matched ticketing trips"})
    z=zipfile.ZipFile(io.BytesIO(archive.read(receipt)));name=next(n for n in z.namelist() if n.lower().endswith('.csv'))
    df=pd.read_csv(z.open(name),dtype=str,keep_default_na=False)
    if not REQUIRED<=set(df.columns):raise ValueError("Unexpected OD schema")
    schedule=Schedule(archive,archive.latest("GTFS",utcnow()))
    stops=set(schedule.stops.stop_id);pilot=set(schedule.stop_times.stop_id);routes=set(schedule.routes.route_short_name)
    df['quantity_numeric']=pd.to_numeric(df.QUANTITY,errors='coerce')
    valid=df.quantity_numeric.notna()&(df.quantity_numeric>0)&df.ORIGIN_STOP.isin(stops)&df.DESTINATION_STOP.isin(stops)
    in_pilot=valid&df.ORIGIN_STOP.isin(pilot)&df.DESTINATION_STOP.isin(pilot)&df.ROUTE.isin(routes)
    normalized=df[in_pilot].copy();out=archive.root/'processed'/'monthly_od.parquet';normalized.to_parquet(out,index=False)
    with duckdb.connect(str(archive.root/'runtime'/'analytics.duckdb')) as db:
        db.execute('CREATE OR REPLACE TABLE monthly_od AS SELECT * FROM read_parquet(?)',[str(out)])
        groups=db.execute('SELECT TIME_GROUPING,count(*) AS rows,sum(quantity_numeric) AS matched_ticketing_trip_proxy FROM monthly_od GROUP BY TIME_GROUPING ORDER BY TIME_GROUPING').fetchdf().to_dict('records')
    report={"status":"audited","source":receipt,"rows":len(df),"valid_stop_quantity_rows":int(valid.sum()),"pilot_mapped_rows":int(in_pilot.sum()),"unmapped_or_invalid_rows":int((~valid).sum()),"time_groups":groups,"used_in_primary_metrics":False,"limitations":["Monthly broad time bins, not exact weekday morning demand","Quantity aggregates matched ticketing trips, not calibrated passenger journeys","go card/EMV touch-on to touch-off; paper at issue; only matched scheduled services","Paper destination can be n/a and is excluded from mapped proxy","Time bins reflect touch-on or issue, not ticketing peak/offpeak; Airtrain excluded","July ticketing identifiers joined to October schedule may drift; unmapped ids remain excluded"]}
    (archive.root/'processed'/'od-audit.json').write_text(json.dumps(report,indent=2));return report
