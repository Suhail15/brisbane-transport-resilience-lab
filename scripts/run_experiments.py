"""Predefine actual disruption targets, then run the same 100 fixed requests for all policies."""
import argparse
import json
from pathlib import Path
import sys
import time
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services'))
from resilience.pipeline.archive import Archive
from resilience.pipeline.snapshots import load_snapshot
from resilience.pipeline.journey_set import expand
from resilience.pipeline.files import atomic_write
from resilience.settings import settings

p=argparse.ArgumentParser();p.add_argument('--snapshot',required=True);p.add_argument('--url',default='http://127.0.0.1:8000/v1');p.add_argument('--prepare-only',action='store_true');p.add_argument('--scenario',choices=['cancellation','stop_closure','rail_corridor','bus_delay'],default='cancellation');p.add_argument('--budgets',type=int,nargs='+',default=[0,2,4,8]);p.add_argument('--sensitivity',action='store_true');p.add_argument('--max-swaps',type=int,default=16);args=p.parse_args()
archive=Archive(settings.data_dir);snapshot=load_snapshot(archive,args.snapshot);requests=expand(snapshot);start=snapshot.metadata.snapshot_s
future=sorted((c for c in snapshot.connections if c.departure_s>=start),key=lambda c:(c.departure_s,c.connection_id))
bus=next(c for c in future if c.mode=='bus' and c.from_stop_id in {'3713','3692','3802','3803','4878'})
rail=next(c for c in future if c.mode=='rail' and (c.from_stop_id in {'600188','600006','600189'} or c.to_stop_id in {'600016','600018','600019'}))
end=start+7200
examples={'cancellation':{'kind':'trip_cancellation','scenario_id':'development:cancel','start_s':start,'end_s':end,'trip_instance_ids':[bus.trip_instance_id]},'stop_closure':{'kind':'stop_unavailable','scenario_id':'development:stop','start_s':start,'end_s':end,'stop_ids':['3713']},'rail_corridor':{'kind':'corridor_closure','scenario_id':'development:rail','start_s':start,'end_s':end,'segments':[{'from_stop_id':rail.from_stop_id,'to_stop_id':rail.to_stop_id,'bidirectional':True}]},'bus_delay':{'kind':'additional_delay','scenario_id':'development:delay','start_s':start,'end_s':end,'trip_instance_ids':[bus.trip_instance_id],'additional_seconds':1200}}
manifest={'snapshot_id':args.snapshot,'journey_set_version':'pilot-od20-v1','requests':[r.model_dump(mode='json') for r in requests],'examples':examples,'selection':'Earliest retained future corridor bus trip and actual rail adjacent movement by stable departure/id order; targets frozen before policy outputs','classification':'Recorded development afternoon inputs; all disruptions and relief scenarios hypothetical'}
path=archive.root/'processed'/'experiment-inputs'/f'{args.snapshot}.json';atomic_write(path,json.dumps(manifest,sort_keys=True,separators=(',',':')),immutable=True)
print({'prepared':str(path),'requests':len(requests),'scenarios':list(examples)},flush=True)
if args.prepare_only:raise SystemExit(0)
summary=[]
with httpx.Client(timeout=120) as client:
    for delta in ([0,300,600] if args.sensitivity else [0]):
        for budget in args.budgets:
            payload={'snapshot_id':args.snapshot,'requests':manifest['requests'],'scenarios':[examples[args.scenario]],'budget_bus_hours':budget,'journey_set_version':'pilot-od20-v1','bus_running_time_sensitivity_seconds':delta,'max_swap_evaluations':args.max_swaps}
            started=time.perf_counter();response=client.post(args.url+'/experiments',json=payload);response.raise_for_status();rid=response.json()['run_id']
            while True:
                response=client.get(args.url+'/experiments/'+rid);response.raise_for_status();run=response.json()
                if run['status'] in ('completed','failed','cancelled'):
                    row={'run_id':rid,'budget':budget,'sensitivity_seconds':delta,'status':run['status'],'elapsed_seconds':time.perf_counter()-started,'metadata':run.get('metadata'),'metrics':run['result']['plan']['evaluation']['metrics'] if run.get('result') else None,'objective':run['result']['plan']['objective'] if run.get('result') else None,'considered_candidate_ids':run['result']['considered_candidate_ids'] if run.get('result') else [],'infeasible_candidates':run['result']['infeasible_candidates'] if run.get('result') else [],'error':run.get('error')};summary.append(row);print(json.dumps(row),flush=True);break
                time.sleep(.5)
            if run['status']!='completed':raise SystemExit('Run failed; inspect error before repeating')
path=archive.root/'processed'/f'experiment-summary-{args.scenario}-{"sensitivity" if args.sensitivity else "budgets"}.json';atomic_write(path,json.dumps(summary,indent=2));print({'summary':str(path)},flush=True)
