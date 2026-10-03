"""Measure 100 real end-to-end journey HTTP calls using the fixed OD workload."""
import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services'))
from resilience.pipeline.archive import Archive
from resilience.pipeline.snapshots import load_snapshot
from resilience.pipeline.journey_set import expand
from resilience.pipeline.analysis import digest,engine_digest
from resilience.settings import settings

p=argparse.ArgumentParser();p.add_argument('--snapshot',required=True);p.add_argument('--url',default='http://127.0.0.1:8000/v1');args=p.parse_args()
snapshot=load_snapshot(Archive(settings.data_dir),args.snapshot);requests=expand(snapshot);timings=[];outcomes=[]
with httpx.Client(timeout=30) as client:
    for request in requests:
        started=time.perf_counter();response=client.post(args.url+'/journeys',json={'snapshot_id':args.snapshot,'request':request.model_dump(mode='json')});elapsed=time.perf_counter()-started;response.raise_for_status();result=response.json();timings.append(elapsed);outcomes.append({'request_id':request.request_id,'seconds':elapsed,'reachable':result['reachable'],'duration_s':result['duration_s']})
ordered=sorted(timings);index=(len(ordered)-1)*.95;low=int(index);fraction=index-low;p95=ordered[low]*(1-fraction)+ordered[min(low+1,len(ordered)-1)]*fraction
report={'workload':'100 sequential end-to-end HTTP journey queries, fixed20pairs x5quarterhours; includes server lookup/routing/serialization/network, first query included','snapshot_id':args.snapshot,'request_set_sha256':digest([r.model_dump(mode='json') for r in requests]),'engine_code_sha256':engine_digest(),'count':len(timings),'median_seconds':statistics.median(timings),'p95_seconds':p95,'p95_method':'linear interpolation at rank(N-1)*0.95','max_seconds':max(timings),'total_seconds':sum(timings),'threshold_seconds':2,'passed':p95<2,'hardware':{'platform':platform.platform(),'machine':platform.machine(),'processor':platform.processor(),'logical_cpus':os.cpu_count(),'python':platform.python_version()},'queries':outcomes,'scope':'Journey endpoint only; async recovery optimization has separately reported total computation time and is not claimed below2s'}
out=Path('data/processed/performance/api-100.json');out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='queries'},indent=2))
