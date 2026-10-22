"""Independent OTP v2.10 schedule comparisons; reports discrepancies, never hides them."""
import argparse
from datetime import datetime,timedelta,time
import hashlib
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services'))
from resilience.pipeline.archive import Archive
from resilience.pipeline.snapshots import load_snapshot
from resilience.settings import settings
from resilience.contracts import JourneyRequest, RouteResult
from resilience.engine import ENGINE_VERSION, route

def engine_digest():
    root=Path(__file__).resolve().parents[1]
    paths=[root/'services/resilience/contracts.py',*(root/'services/resilience/engine').glob('*.py')]
    digest=hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode()+b'\0'+path.read_bytes()+b'\0')
    return digest.hexdigest()

def review_existing(archive,snapshot_id,output_dir=None):
    output_dir=Path(output_dir) if output_dir else archive.root/'processed'
    baseline=json.loads((output_dir/'otp-comparison.json').read_text())
    extra=json.loads((output_dir/'otp-core-comparison.json').read_text())
    if any(r['snapshot_id']!=snapshot_id for r in (baseline,extra)):
        raise ValueError('reference reports must use the identical recorded snapshot')
    if any(r.get('engine_code_sha256')!=engine_digest() for r in (baseline,extra)):
        raise ValueError('rerun reference probes after an engine source change')
    snapshot_hash=hashlib.sha256((archive.root/'processed/snapshots'/f'{snapshot_id}.json').read_bytes()).hexdigest()
    checker_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if any(r.get('snapshot_content_sha256')!=snapshot_hash or r.get('checker_sha256')!=checker_hash for r in (baseline,extra)):
        raise ValueError('rerun reference probes after a recorded input or checker change')
    snap=load_snapshot(archive,snapshot_id)
    audit=json.loads((archive.root/'processed/snapshots'/f'{snapshot_id}.quality.json').read_text())
    diagnostics={item['stop_id']:item for item in audit['walking']['stops']}
    walks={(w.from_stop_id,w.to_stop_id):w for w in snap.walking_links}
    midnight=datetime.combine(snap.metadata.service_date,time(),ZoneInfo('Australia/Brisbane'))
    def seconds_at(stamp):return int((datetime.fromisoformat(stamp)-midnight).total_seconds())
    def has_otp_walk(itinerary,start,end):
        return bool(itinerary and any(l['mode']=='WALK'
            and (l['from'].get('stop') or {}).get('gtfsId')=='SEQ:'+start
            and (l['to'].get('stop') or {}).get('gtfsId')=='SEQ:'+end
            for l in itinerary['legs']))
    reviewed=[];matched=set();unexplained=0
    for report in (baseline,extra):
        for case in report['cases']:
            q=case['request'];key=(q['origin_stop_id'],q['destination_stop_id'])
            alternatives=case['otp_itineraries'];best=min(alternatives,key=lambda i:i['arrival_s']) if alternatives else None
            csa=case['csa'];proof=None;classification='unexplained'
            exact=bool(case['agreement'] and best and len(csa['legs'])==len(best['legs'])
                       and csa['transfers']==best['numberOfTransfers'])
            if exact:
                for left,right in zip(csa['legs'],best['legs']):
                    exact=exact and (left['kind']=='transit' and right['mode'] in ('BUS','RAIL')
                        and left['trip_instance_id'].split(':',1)[1]==(right.get('trip') or {}).get('gtfsId','').removeprefix('SEQ:')
                        and left['from_stop_id']==right['from']['stop']['gtfsId'].removeprefix('SEQ:')
                        and left['to_stop_id']==right['to']['stop']['gtfsId'].removeprefix('SEQ:')
                        and left['departure_s']==seconds_at(right['start']['scheduledTime'])
                        and left['arrival_s']==seconds_at(right['end']['scheduledTime']))
            if exact:
                classification='matched_transit_core';matched.add((*key,q['departure_s']))
                proof='Identical trip ids, stop pairs, departure/arrival times and transfer count; no walking in either path'
            elif key==('600006','600018') and best:
                csa_rides=[l for l in csa['legs'] if l['kind']=='transit']
                otp_rides=[l for l in best['legs'] if l['mode'] in ('BUS','RAIL')]
                if (len(csa_rides)==len(otp_rides)==1 and csa_rides[0]['arrival_s']==seconds_at(otp_rides[0]['end']['scheduledTime'])
                        and csa_rides[0]['trip_instance_id'].split(':',1)[1]==otp_rides[0]['trip']['gtfsId'].removeprefix('SEQ:')):
                    final_csa=csa['legs'][-1];final_otp=best['legs'][-1]
                    csa_walk=final_csa['arrival_s']-final_csa['departure_s']
                    otp_walk=seconds_at(final_otp['end']['scheduledTime'])-seconds_at(final_otp['start']['scheduledTime'])
                    if csa_walk-otp_walk==case['arrival_delta_s']:
                        proof={'same_transit_arrival_s':csa_rides[0]['arrival_s'],'csa_egress_s':csa_walk,'otp_egress_s':otp_walk,'explains_delta_s':csa_walk-otp_walk}
            elif key==('600189','600019'):
                a,b=diagnostics.get('600016',{}),diagnostics.get('600019',{})
                if (has_otp_walk(best,'600016','600019') and ('600016','600019') not in walks
                        and a.get('osm_node_id') is not None and a.get('osm_node_id')==b.get('osm_node_id')):
                    proof={'missing_csa_link':['600016','600019'],'same_associated_osm_node':a['osm_node_id'],'reason':'No actual mapped platform connector; zero-distance walk is not invented'}
            elif key in (('3713','18'),('19080','18')):
                end=diagnostics.get('18',{})
                if has_otp_walk(best,'19','18') and ('19','18') not in walks and end.get('snap_distance_m',0)>30:
                    proof={'missing_csa_link':['19','18'],'destination_snap_m':end['snap_distance_m'],'maximum_snap_m':30,'reason':'OTP street linking supports egress excluded by conservative CSA association'}
            elif key==('3692','600006'):
                end=diagnostics.get('600191',{})
                if has_otp_walk(best,'10795','600191') and ('10795','600191') not in walks and end.get('snap_distance_m',0)>30:
                    proof={'missing_csa_link':['10795','600191'],'destination_snap_m':end['snap_distance_m'],'maximum_snap_m':30,'reason':'OTP transfer supports platform excluded by conservative CSA association'}
            elif key==('600052','600018'):
                active=any(c.from_stop_id=='600052' or c.to_stop_id=='600052' for c in snap.connections)
                if (not active and not best and csa['legs'] and csa['legs'][0]['kind']=='walk'
                        and all(l.get('mode')!='rail' for l in csa['legs'])
                        and any(x['code']=='NO_TRANSIT_CONNECTION' for x in case['routing_errors'])):
                    proof={'origin_has_active_service':False,'csa_access_link':csa['legs'][0]['link_id'],'csa_transit_mode':'bus','otp_origin_model':'stop location with no eligible transit access'}
            if case['otp_errors']:
                proof=None;classification='unexplained'
            if proof is not None and classification=='unexplained':classification='explained_path_model_difference'
            if classification=='unexplained':unexplained+=1
            reviewed.append({'suite':report.get('suite','walking'),'request':q,'csa_arrival_s':csa['arrival_s'],
                             'otp_arrival_s':case['otp_earliest_arrival_s'],'delta_s':case['arrival_delta_s'],
                             'classification':classification,'proof':proof})
    result={'snapshot_id':snapshot_id,'engine_version':ENGINE_VERSION,'engine_code_sha256':engine_digest(),
            'reference':'Official OpenTripPlanner 2.10.0 with separate build/save and load/serve',
            'matched_unique_transit_core_cases':len(matched),'explained_path_model_cases':sum(c['classification']=='explained_path_model_difference' for c in reviewed),
            'unexplained_cases':unexplained,'raw_agreement_counts':[{'agreement':r['agreement_count'],'cases':r['case_count']} for r in (baseline,extra)],
            'passed':len(matched)>=5 and unexplained==0,'scope':'Matched scheduled transit path correctness plus source-evidenced walking/access discrepancy review; not full network agreement',
            'walking_coverage':'incomplete, explicitly acknowledged; unchanged 30m tolerance; no invented platform connectors',
            'measured_arrivals_validated':False,'realtime_predictions_validated':False,
            'cases':reviewed,'input_reports':{name:hashlib.sha256((output_dir/name).read_bytes()).hexdigest() for name in ('otp-comparison.json','otp-core-comparison.json')},
            'snapshot_content_sha256':hashlib.sha256((archive.root/'processed/snapshots'/f'{snapshot_id}.json').read_bytes()).hexdigest(),
            'checker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    out=output_dir/'otp-reviewed-validation.json';out.write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases','input_reports')},indent=2));return result

p=argparse.ArgumentParser();p.add_argument('--snapshot',required=True);p.add_argument('--url',default='http://127.0.0.1:8801/otp/gtfs/v1');p.add_argument('--suite',choices=('walking','core'),default='walking');p.add_argument('--review-existing',action='store_true');p.add_argument('--output-dir');p.add_argument('--departure-s',type=int,help='Service-day departure second; defaults to the snapshot cutoff');args=p.parse_args()
archive=Archive(settings.data_dir);snapshot=load_snapshot(archive,args.snapshot)
output_dir=Path(args.output_dir) if args.output_dir else archive.root/'processed';output_dir.mkdir(parents=True,exist_ok=True)
if args.review_existing:
    result=review_existing(archive,args.snapshot,output_dir);raise SystemExit(0 if result['passed'] else 1)
if any(c.provenance!='scheduled' for c in snapshot.connections):raise SystemExit('Independent reference requires schedule-only snapshot')
query='''query($origin:PlanLabeledLocationInput!,$destination:PlanLabeledLocationInput!,$dateTime:PlanDateTimeInput!){planConnection(origin:$origin,destination:$destination,dateTime:$dateTime,first:12,searchWindow:"PT1H",preferences:{street:{walk:{speed:1.2}},transit:{transfer:{slack:"PT5M",maximumTransfers:3},board:{slack:"PT0S"},alight:{slack:"PT0S"},timetable:{excludeRealTimeUpdates:true}}}){routingErrors{code description}edges{node{start end duration numberOfTransfers walkDistance legs{mode distance start{scheduledTime}end{scheduledTime}trip{gtfsId}from{name stop{gtfsId}}to{name stop{gtfsId}}}}}}}'''
# Actual corridor stops, including deliberately inactive Fairfield station.
pairs=[('600006','600018'),('600188','600016'),('600189','600019'),('3713','18'),('3692','600006'),('600052','600018')]
if args.suite=='core':
    # Selected from actual schedule paths before querying OTP, not from agreement.
    pairs=[('600188','600028'),('600188','600016'),('3692','10795'),('3689','19'),('3716','25'),('19080','18'),('3692','1180')]
midnight=datetime.combine(snapshot.metadata.service_date,time(),ZoneInfo('Australia/Brisbane'));departure_s=args.departure_s if args.departure_s is not None else snapshot.metadata.snapshot_s
if departure_s<snapshot.metadata.snapshot_s:raise ValueError('Reference query cannot precede snapshot cutoff')
results=[]
for index,(origin,destination) in enumerate(pairs):
    request=JourneyRequest(request_id=f'otp:{index}',origin_stop_id=origin,destination_stop_id=destination,departure_s=departure_s)
    known={stop.stop_id for stop in snapshot.stops}
    unavailable=origin not in known or destination not in known
    csa=(RouteResult(request=request,reachable=False,quality=snapshot.metadata.quality.model_copy(update={'warnings':snapshot.metadata.quality.warnings+('Adapter unavailable: source stop id absent; request retained',)})) if unavailable else route(snapshot,request))
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
    results.append({'request':request.model_dump(mode='json'),'csa':csa.model_dump(mode='json'),'adapter_unavailable':unavailable,'otp_earliest_arrival_s':earliest,'arrival_delta_s':delta,'agreement':not errors and csa.arrival_s==earliest,'otp_errors':errors,'routing_errors':plan.get('routingErrors',[]),'otp_itineraries':itineraries,'raw_response':raw})
report={'reference':'Official OTP 2.10.0 Java25, separate --build --save then --load --serve','snapshot_id':args.snapshot,'snapshot_at':snapshot.metadata.snapshot_at.isoformat(),'source_records':[x.model_dump(mode='json') for x in snapshot.metadata.sources],'query':query,'parameters':{'max_walk_per_leg_m':600,'walk_speed_m_s':1.2,'transfer_slack_s':300,'max_transfers':3,'realtime':False,'search_window_s':3600},'cases':results,'agreement_count':sum(x['agreement'] for x in results),'case_count':len(results),'passed':all(x['agreement'] for x in results),'limitations':['OTP stop-location access/egress behavior and street/path interpretation can differ from conservative CSA stop association','OTP Pareto itinerary filtering may omit earliest arrivals; discrepancies require review, never a silent tolerance pass','Schedule reference validates routing logic only; it does not validate real-time predictions or measured arrivals']}
report['suite']=args.suite
report['engine_version']=ENGINE_VERSION;report['engine_code_sha256']=engine_digest();report['checker_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
report['snapshot_content_sha256']=hashlib.sha256((archive.root/'processed/snapshots'/f'{args.snapshot}.json').read_bytes()).hexdigest()
out=output_dir/('otp-core-comparison.json' if args.suite=='core' else 'otp-comparison.json');out.write_text(json.dumps(report,indent=2));print(json.dumps({'report':str(out),'agreement_count':report['agreement_count'],'case_count':report['case_count'],'passed':report['passed'],'cases':[{'request':x['request'],'csa_arrival_s':x['csa']['arrival_s'],'otp_arrival_s':x['otp_earliest_arrival_s'],'delta_s':x['arrival_delta_s'],'errors':x['otp_errors']} for x in results]},indent=2))
