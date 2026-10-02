"""Run a small fixed real-stop development experiment against the local async API."""
import argparse
import json
from pathlib import Path
import time
import httpx
p=argparse.ArgumentParser();p.add_argument('--snapshot',required=True);p.add_argument('--budget',type=int,choices=(0,2,4,8),default=0);p.add_argument('--url',default='http://127.0.0.1:8000/v1');args=p.parse_args()
requests=[{'request_id':f'preview:{i}','origin_stop_id':a,'destination_stop_id':b,'departure_s':54000} for i,(a,b) in enumerate([('3713','18'),('3713','600016'),('3692','18'),('3692','600006'),('600188','600016'),('600006','600018')])]
with httpx.Client(timeout=60) as client:
    response=client.post(args.url+'/journeys',json={'snapshot_id':args.snapshot,'request':requests[0]});response.raise_for_status();baseline=response.json()
    transit=next((leg for leg in baseline['legs'] if leg['kind']=='transit'),None)
    scenarios=[] if transit is None else [{'kind':'additional_delay','scenario_id':'preview:delay','start_s':54000,'end_s':57600,'trip_instance_ids':[transit['trip_instance_id']],'additional_seconds':1200}]
    payload={'snapshot_id':args.snapshot,'requests':requests,'scenarios':scenarios,'budget_bus_hours':args.budget}
    response=client.post(args.url+'/experiments',json=payload);response.raise_for_status();rid=response.json()['run_id']
    print({'run_id':rid,'input':payload},flush=True)
    while True:
        response=client.get(args.url+'/experiments/'+rid);response.raise_for_status();run=response.json()
        if run['status'] in ('completed','failed','cancelled'):
            out=Path('data/processed/preview-run.json');out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(run,indent=2));print(json.dumps({'run_id':rid,'status':run['status'],'error':run.get('error'),'output':str(out)},indent=2));break
        time.sleep(1)
