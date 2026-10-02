"""Independent OTP v2.10 schedule comparisons; reports discrepancies, never hides them."""
import argparse
from datetime import datetime,timedelta,time
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services'))
from resilience.pipeline.archive import Archive
from resilience.pipeline.snapshots import load_snapshot
from resilience.settings import settings
from resilience.contracts import JourneyRequest
from resilience.engine import route

p=argparse.ArgumentParser();p.add_argument('--snapshot',required=True);p.add_argument('--url',default='http://127.0.0.1:8801/otp/gtfs/v1');args=p.parse_args()
archive=Archive(settings.data_dir);snapshot=load_snapshot(archive,args.snapshot)
if any(c.provenance!='scheduled' for c in snapshot.connections):raise SystemExit('Independent reference requires schedule-only snapshot')
query='''query($origin:PlanLabeledLocationInput!,$destination:PlanLabeledLocationInput!,$dateTime:PlanDateTimeInput!){planConnection(origin:$origin,destination:$destination,dateTime:$dateTime,first:12,searchWindow:"PT1H",preferences:{street:{walk:{speed:1.2}},transit:{transfer:{slack:"PT5M",maximumTransfers:3},board:{slack:"PT0S"},alight:{slack:"PT0S"},timetable:{excludeRealTimeUpdates:true}}}){routingErrors{code description}edges{node{start end duration numberOfTransfers walkDistance legs{mode distance start{scheduledTime}end{scheduledTime}trip{gtfsId}from{name stop{gtfsId}}to{name stop{gtfsId}}}}}}}'''
# Actual corridor stops, including deliberately inactive Fairfield station.
pairs=[('600006','600018'),('600188','600016'),('600189','600019'),('3713','18'),('3692','600006'),('600052','600018')]
midnight=datetime.combine(snapshot.metadata.service_date,time(),ZoneInfo('Australia/Brisbane'));departure_s=15*3600
results=[]
for index,(origin,destination) in enumerate(pairs):
    request=JourneyRequest(request_id=f'otp:{index}',origin_stop_id=origin,destination_stop_id=destination,departure_s=departure_s)
    csa=route(snapshot,request)
    variables={'origin':{'location':{'stopLocation':{'stopLocationId':'SEQ:'+origin}}},'destination':{'location':{'stopLocation':{'stopLocationId':'SEQ:'+destination}}},'dateTime':{'earliestDeparture':(midnight+timedelta(seconds=departure_s)).isoformat()}}
    response=httpx.post(args.url,json={'query':query,'variables':variables},timeout=60);response.raise_for_status();raw=response.json()
    errors=raw.get('errors',[]);plan=(raw.get('data') or {}).get('planConnection') or {};itineraries=[]
    for edge in plan.get('edges',[]):
        itinerary=edge['node']
        # Apply explicit CSA query constraints to OTP's returned alternatives.
        if itinerary['numberOfTransfers']>3 or any(l['mode']=='WALK' and l['distance']>600 for l in itinerary['legs']):continue
        itinerary['arrival_s']=int((datetime.fromisoformat(itinerary['end'])-midnight).total_seconds());itineraries.append(itinerary)
    earliest=min((i['arrival_s'] for i in itineraries),default=None)
    delta=csa.arrival_s-earliest if csa.arrival_s is not None and earliest is not None else None
    results.append({'request':request.model_dump(mode='json'),'csa':csa.model_dump(mode='json'),'otp_earliest_arrival_s':earliest,'arrival_delta_s':delta,'agreement':not errors and csa.arrival_s==earliest,'otp_errors':errors,'routing_errors':plan.get('routingErrors',[]),'otp_itineraries':itineraries,'raw_response':raw})
report={'reference':'Official OTP 2.10.0 Java25, separate --build --save then --load --serve','snapshot_id':args.snapshot,'snapshot_at':snapshot.metadata.snapshot_at.isoformat(),'source_records':[x.model_dump(mode='json') for x in snapshot.metadata.sources],'query':query,'parameters':{'max_walk_per_leg_m':600,'walk_speed_m_s':1.2,'transfer_slack_s':300,'max_transfers':3,'realtime':False,'search_window_s':3600},'cases':results,'agreement_count':sum(x['agreement'] for x in results),'case_count':len(results),'passed':all(x['agreement'] for x in results),'limitations':['OTP stop-location access/egress behavior and street/path interpretation can differ from conservative CSA stop association','OTP Pareto itinerary filtering may omit earliest arrivals; discrepancies require review, never a silent tolerance pass','Schedule reference validates routing logic only; it does not validate real-time predictions or measured arrivals']}
out=archive.root/'processed'/'otp-comparison.json';out.write_text(json.dumps(report,indent=2));print(json.dumps({'report':str(out),'agreement_count':report['agreement_count'],'case_count':report['case_count'],'passed':report['passed'],'cases':[{'request':x['request'],'csa_arrival_s':x['csa']['arrival_s'],'otp_arrival_s':x['otp_earliest_arrival_s'],'delta_s':x['arrival_delta_s'],'errors':x['otp_errors']} for x in results]},indent=2))
